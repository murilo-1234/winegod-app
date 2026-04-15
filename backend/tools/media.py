"""Media processing: process_image, process_video, process_pdf, process_voice."""

import base64
import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import time

from google import genai
from google.genai import types
from services.tracing import log_memory


# Acima deste tamanho de texto, pular chamada monolitica e ir direto para chunked
# paralelo. Threshold escolhido empiricamente: textos <=15000 chars completam
# de forma confiavel em uma chamada (Elephante 9k, Hendricks 9k, ALINA 2k).
# Acima disso a chamada monolitica fica perto do limite de 300s e/ou retorna
# JSON malformado (Posada 30k, Cambio 24k).
_LONG_TEXT_THRESHOLD = 15000


# Garantir ffmpeg no PATH via imageio-ffmpeg (pacote Python com binario embutido)
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except ImportError:
    pass


# --- Lazy Gemini client ---

_gemini_client = None

GEMINI_MODEL = "gemini-2.5-flash"


def _get_gemini_client():
    """Retorna cliente Gemini, criado sob demanda."""
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY nao configurada")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _gemini_generate(contents, thinking=True):
    """Chama Gemini generate_content com o modelo padrao."""
    client = _get_gemini_client()
    config = None
    if not thinking:
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )
    return response.text


def gemini_text_generate(prompt_text, thinking=False):
    """Wrapper publico para Gemini texto puro."""
    return _gemini_generate(prompt_text, thinking=thinking)


class ThinkingLeakError(RuntimeError):
    """Raised when a Gemini enrichment call emits thoughts despite thinking_budget=0."""


def gemini_enrichment_generate(prompt_text, model):
    """Gemini call with strict `thinking=0` guarantees for the v3 enrichment.

    Returns dict with `text`, `model`, `prompt_tokens`, `output_tokens`,
    `thought_tokens`, `latency_ms`. Raises `ThinkingLeakError` if the response
    metadata reports non-zero `thoughts_token_count` so the caller fails loudly
    instead of silently paying for thinking in production.
    """
    client = _get_gemini_client()
    config_kwargs = {
        "thinking_config": types.ThinkingConfig(thinking_budget=0),
    }
    try:
        # Only newer SDKs expose include_thoughts on ThinkingConfig; set it when
        # available to make the contract belt-and-suspenders.
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=0, include_thoughts=False
        )
    except TypeError:
        pass

    config = types.GenerateContentConfig(**config_kwargs)

    t0 = time.time()
    response = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )
    latency_ms = round((time.time() - t0) * 1000)

    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    thought_tokens = getattr(usage, "thoughts_token_count", 0) or 0

    if thought_tokens:
        raise ThinkingLeakError(
            f"Gemini {model} returned thoughts_token_count={thought_tokens} "
            "despite thinking_budget=0"
        )

    return {
        "text": response.text or "",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thought_tokens": thought_tokens,
        "latency_ms": latency_ms,
    }


# --- Lazy Qwen client (DashScope, OpenAI-compatible) ---

_qwen_client = None

QWEN_MODEL = "qwen3-vl-flash"


def _get_qwen_client():
    """Retorna cliente Qwen/DashScope, criado sob demanda."""
    global _qwen_client
    if _qwen_client is None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return None
        from openai import OpenAI
        base_url = os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        _qwen_client = OpenAI(api_key=api_key, base_url=base_url)
    return _qwen_client


def _qwen_generate(image_bytes, mime_type, prompt):
    """Chama Qwen VL via DashScope. Retorna texto ou None se falhar."""
    client = _get_qwen_client()
    if client is None:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{b64}"
    try:
        resp = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ]}],
            temperature=0.0,
            extra_body={"vl_high_resolution_images": True},
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[qwen] error: {type(e).__name__}: {e}", flush=True)
        return None


QWEN_TEXT_MODEL = "qwen-turbo"


def _qwen_text_generate(prompt_text):
    """Chama Qwen-turbo (texto puro, sem visao). Retorna texto ou None se falhar."""
    client = _get_qwen_client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=QWEN_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[qwen_text] error: {type(e).__name__}: {e}", flush=True)
        return None


def qwen_text_generate(prompt_text):
    """Wrapper publico de _qwen_text_generate para uso por outros modulos."""
    return _qwen_text_generate(prompt_text)


def _preprocess_image_for_dense_shelf(image_bytes):
    """Preprocessing pra prateleiras densas: CLAHE + upscale 1.5x + sharpen + contrast."""
    t0 = time.time()
    log_memory("dense_shelf_preproc:start", input_bytes=len(image_bytes))
    import io
    from PIL import Image, ImageEnhance, ImageFilter
    try:
        import cv2
        import numpy as np
        img = Image.open(io.BytesIO(image_bytes))
        arr = np.array(img)
        lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        img = Image.fromarray(result)
    except ImportError:
        img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    img = img.resize((int(w * 1.5), int(h * 1.5)), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=3, percent=150, threshold=2))
    img = ImageEnhance.Contrast(img).enhance(1.15)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    out = buf.getvalue()
    log_memory(
        "dense_shelf_preproc:end",
        ms=round((time.time() - t0) * 1000),
        input_bytes=len(image_bytes),
        output_bytes=len(out),
        ratio=round(len(out) / max(len(image_bytes), 1), 2),
    )
    return out


# --- Prompts ---

IMAGE_UNIFIED_PROMPT = """Voce e um analista de imagens de vinho. Classifique esta imagem como UMA das opcoes:

## Regras de classificacao

"label" — Um vinho ou SKU DOMINA a cena visualmente. O rotulo/garrafa ocupa a maior parte do quadro.
  - Use "label" mesmo que haja 2-5 copias do MESMO vinho lado a lado (ex: facing de supermercado).
  - Use "label" se um vinho e claramente o assunto principal e garrafas ao fundo estao desfocadas.
  - NAO exija garrafa unica isolada. Dominancia visual e o criterio, nao quantidade de garrafas.

"screenshot" — Captura de tela ou interface digital com informacoes de vinho (app, site, lista de precos, resultados de busca).

"shelf" — Foto mostrando MULTIPLOS vinhos DIFERENTES juntos em prateleira, display, rack ou mesa, sem que um unico vinho domine o quadro.

"not_wine" — A imagem nao contem conteudo relacionado a vinho.

## Schemas de saida (retorne SOMENTE JSON valido, sem texto extra)

Se tipo "label":
{"type": "label", "name": "nome completo do vinho", "producer": "vinicola ou null", "vintage": "ano ou null", "region": "regiao ou null", "grape": "uva ou null", "price": "preco com moeda ou null"}

Se tipo "screenshot":
{"type": "screenshot", "wines": [{"name": "nome do vinho", "producer": "vinicola ou null", "price": "preco ou null", "rating": "nota ou null", "source": "app/site ou null"}]}

Se tipo "shelf":
{"type": "shelf", "wines": [{"name": "nome completo do vinho como lido", "producer": "vinicola ou null", "line": "linha do vinho ou null", "variety": "uva ou null", "classification": "Reserva/Gran Reserva/etc ou null", "style": "red/white/rosé/sparkling ou null", "price": "preco ou null"}], "total_visible": 0}

Se tipo "not_wine":
{"type": "not_wine", "description": "descricao breve do que a imagem mostra"}

## Regras de preco
Etiquetas de prateleira podem mostrar multiplos valores (preco por litro, por caixa, unitario).
  - Sempre extraia o PRECO UNITARIO da garrafa (tipicamente 750ml), nunca o preco por litro
  - Se houver multiplos precos visiveis para o mesmo vinho, escolha o rotulado como preco da garrafa/unitario
  - Se nao tiver certeza de qual preco e o unitario, retorne null em vez de adivinhar
  - Preserve o simbolo da moeda original (R$, $, €, £, ¥, etc.)

## Regras de limpeza de nome
  - Use o nome COMPLETO do vinho como impresso no ROTULO DA GARRAFA, nao abreviado
  - Remova prefixos de etiqueta de prateleira que NAO fazem parte do nome do vinho (ex: "VINHO TTO", "VINHO TINTO", "V. TTO", "750ML")
  - Corrija artefatos obvios de OCR: se uma letra esta claramente errada pelo contexto, corrija (ex: "PONTGRAS" em prateleira chilena e quase certamente "MONTGRAS")
  - Inclua vinicola + linha + variedade quando visiveis (ex: "MontGras Aura Reserva Cabernet Sauvignon")
  - NAO invente ou adivinhe partes do nome que nao consegue ler — use o que e legivel
  - Separe vinicola (producer) do nome do vinho quando ambos sao claramente distintos no rotulo

## Regras de variedade de uva
  - So reporte variedades que voce consegue LER CLARAMENTE no rotulo
  - Se parcialmente obstruida ou ambigua, retorne null em vez de adivinhar
  - Se voce ve apenas 2-3 letras de um nome de uva, retorne null

## Regras de produtor para shelf e screenshot
  - Para cada vinho, extraia "producer" (vinicola) separadamente quando claramente visivel
  - Mantenha o nome COMPLETO do vinho em "name" incluindo prefixo da vinicola se e assim que aparece (ex: name: "MontGras Reserva Cabernet", producer: "MontGras")
  - Use null para producer se nao legivel — NAO adivinhe a partir do nome do vinho

## Regras especificas de shelf
  - "wines": inclua apenas vinhos cujos nomes voce consegue ler com confianca
  - Deduplicar: se o mesmo vinho aparece varias vezes na prateleira, liste apenas UMA vez
  - "total_visible": estime o numero de rotulos/SKUs DISTINTOS visiveis (nao total de garrafas fisicas). 10 copias do mesmo vinho = 1 SKU. Seja conservador — na duvida, estime pra baixo.
  - Para cada vinho na lista, extraia preco se uma etiqueta de preco esta claramente associada a ele

## Campos estruturados de shelf (para cada vinho)
  - "name": mantenha o nome COMPLETO do vinho como impresso (vinicola + linha + variedade + classificacao). Este e o campo principal — sempre preencha.
  - "line": a LINHA ou FAIXA do vinho dentro do produtor. Exemplos: "Aura" em "MontGras Aura Reserva Carmenere". Use null se nao identificavel.
  - "variety": variedade de uva quando claramente legivel. Use null se nao visivel.
  - "classification": nivel de qualidade quando visivel (ex: "Reserva", "Gran Reserva", "Crianza"). Use null se nao visivel.
  - "style": estilo geral — use exatamente um de: "red", "white", "rosé", "sparkling". Use null se nao determinavel.
  - NAO adivinhe ou infira campos estruturados a partir do contexto — extraia apenas o que voce consegue ler claramente.

## Processo obrigatorio (interno — retorne apenas o JSON final)
1. Conte quantos rotulos DIFERENTES de vinho estao visiveis (SKUs distintos, nao garrafas)
2. Varra da ESQUERDA pra DIREITA, de CIMA pra BAIXO
3. Para cada vinho, encontre a etiqueta de preco mais proxima
4. Confira que a quantidade de vinhos na lista bate com a contagem do passo 1
5. Se nao bater, varra novamente

## Regras gerais
  - Sempre use null para campos que realmente nao consegue determinar
  - Retorne SOMENTE JSON valido parseavel — sem markdown, sem comentario, sem texto extra
  - Nao envolva o JSON em code fences
  - Se NAO consegue ler claramente o nome de um vinho, OMITA. Nunca invente."""

VIDEO_FRAME_PROMPT = """Analyze this image frame from a video. Look for wine labels, wine bottles,
wine lists, or any text related to wine. Extract ALL wines you can identify:
- Wine name (full name as on label)
- Producer/Winery
- Vintage year (if visible)
- Region (if visible)
- Price (if visible)

Return ONLY a JSON object:
{"wines": [{"name": "...", "producer": "...", "vintage": "...", "region": "...", "price": "..."}]}

If you cannot identify a field, use null.
If there are NO wines visible, return {"wines": []}"""

PDF_TEXT_PROMPT = """Analyze the following text extracted from a PDF document (wine list, catalog, or menu).

## Your task
1. Identify ALL wines mentioned.
2. Ignore decorative text: section headers ("Nossa Selecao", "Destaques"), descriptions,
   marketing copy, legal text, restaurant info — these are NOT wines.
3. For each wine, extract only what is clearly stated — do NOT guess or infer.

## Price rules
- Only associate a price with a wine when the price clearly belongs to that specific item.
- In tabular layouts, match price to the wine on the same row or directly adjacent.
- If a price could belong to multiple wines or is ambiguous, return null for price.
- Preserve currency symbol (R$, $, €, etc.).

## Output
Return ONLY a JSON object (no markdown, no commentary):
{"wines": [{"name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "...", "price": "..."}]}

If you cannot identify a field, use null.
If there are NO wines in the text, return {"wines": []}.

Text:
"""

PDF_IMAGE_PROMPT = """Analyze this page image from a PDF document (wine list, catalog, or menu).

## Your task
1. Identify ALL wines visible on this page.
2. Ignore decorative elements: headers, logos, background images, marketing text.
3. For each wine, extract only what you can clearly read — do NOT guess.

## Price rules
- Only associate a price with a wine when the price is clearly next to or aligned with that wine.
- If a price is ambiguous (could belong to multiple items), return null for price.
- Preserve currency symbol (R$, $, €, etc.).

## Output
Return ONLY a JSON object (no markdown, no commentary):
{"wines": [{"name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "...", "price": "..."}]}

If you cannot identify a field, use null.
If there are NO wines visible, return {"wines": []}"""


# --- Helpers ---

def _parse_gemini_json(text):
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _deduplicate_wines(all_wines):
    """Deduplicate wines by (normalized name, normalized producer).

    Chave inclui produtor porque em cartas de vinho nomes genericos como
    'Brut Reserve', 'Brunello', 'Chardonnay' aparecem para multiplos produtores
    distintos. Chavear so por nome colapsava esses como 1 unico vinho e
    derrubava ate 38% de uma carta real (Elephante: 184 -> 113). Vinhos com
    produtor ausente em ambos ainda colapsam (compat com merge de info parcial).
    """
    seen = {}
    for wine in all_wines:
        name = (wine.get("name") or "").strip().lower()
        if not name:
            continue
        producer = (wine.get("producer") or "").strip().lower()
        key = (name, producer)
        if key not in seen:
            seen[key] = wine
        else:
            existing = seen[key]
            for k in wine:
                if wine[k] and not existing.get(k):
                    existing[k] = wine[k]
    return list(seen.values())


def _wines_to_description(wines, source_label):
    """Convert a list of wine dicts to a human-friendly description for chat context."""
    if not wines:
        return None

    lines = [f"Vinhos identificados no {source_label}:"]
    for i, w in enumerate(wines, 1):
        parts = []
        if w.get("name"):
            parts.append(w["name"])
        if w.get("producer"):
            parts.append(w["producer"])
        if w.get("vintage"):
            parts.append(str(w["vintage"]))
        if w.get("region"):
            parts.append(w["region"])
        if w.get("grape"):
            parts.append(w["grape"])
        if w.get("price"):
            parts.append(f"Preco: {w['price']}")
        lines.append(f"  {i}. {' — '.join(parts)}")

    return "\n".join(lines)


def _resize_frame_bytes(frame_path, max_side=1024):
    """Resize a frame image to max_side on the longest edge, return bytes."""
    from PIL import Image
    import io

    with Image.open(frame_path) as img:
        w, h = img.size
        if w > max_side or h > max_side:
            if w > h:
                new_w = max_side
                new_h = int(h * max_side / w)
            else:
                new_h = max_side
                new_w = int(w * max_side / h)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


# --- Public functions ---

def _detect_mime_type(image_bytes):
    """Detecta mime type real da imagem pelos magic bytes."""
    if image_bytes[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    if image_bytes[4:12] == b'ftypheic' or image_bytes[4:12] == b'ftypmif1':
        return "image/heic"
    if image_bytes[:4] == b'GIF8':
        return "image/gif"
    return "image/jpeg"


def process_image(base64_image):
    """Pipeline de 3 camadas: Qwen flash (barato) -> Qwen+preprocessing -> Gemini (fallback)."""
    try:
        t0_total = time.time()
        image_bytes = base64.b64decode(base64_image)
        mime_type = _detect_mime_type(image_bytes)
        print(f"[process_image] bytes={len(image_bytes)}, mime={mime_type}", flush=True)
        log_memory("process_image:start", bytes=len(image_bytes), mime=mime_type)

        result = None
        layer_used = "unknown"

        # --- CAMADA 1: Qwen flash (barato, rapido) ---
        t0_qwen = time.time()
        raw_text = _qwen_generate(image_bytes, mime_type, IMAGE_UNIFIED_PROMPT)
        qwen_ms = round((time.time() - t0_qwen) * 1000)
        log_memory(
            "process_image:qwen_flash",
            ms=qwen_ms,
            raw_chars=len(raw_text or ""),
        )
        if raw_text:
            try:
                result = _parse_gemini_json(raw_text)
                layer_used = "qwen_flash"
                print(f"[process_image] qwen_flash OK: type={result.get('type')}", flush=True)
                log_memory(
                    "process_image:qwen_flash:parsed",
                    image_type=result.get("type"),
                    wines=len(result.get("wines", [])) if isinstance(result.get("wines"), list) else 0,
                )

                # Se shelf com 4+ vinhos, tentar camada 2 (preprocessing)
                if (result.get("type") == "shelf"
                        and len(result.get("wines", [])) >= 4):
                    print("[process_image] shelf 4+ wines, trying layer 2 (preproc)", flush=True)
                    log_memory(
                        "process_image:preproc:trigger",
                        wines=len(result.get("wines", [])),
                    )
                    try:
                        t0_preproc = time.time()
                        enhanced_bytes = _preprocess_image_for_dense_shelf(image_bytes)
                        preproc_ms = round((time.time() - t0_preproc) * 1000)
                        log_memory(
                            "process_image:preproc:bytes_ready",
                            ms=preproc_ms,
                            enhanced_bytes=len(enhanced_bytes),
                        )
                        t0_qwen2 = time.time()
                        raw2 = _qwen_generate(enhanced_bytes, "image/jpeg", IMAGE_UNIFIED_PROMPT)
                        qwen2_ms = round((time.time() - t0_qwen2) * 1000)
                        log_memory(
                            "process_image:qwen_flash_preproc",
                            ms=qwen2_ms,
                            raw_chars=len(raw2 or ""),
                        )
                        if raw2:
                            result2 = _parse_gemini_json(raw2)
                            wines2 = result2.get("wines", [])
                            log_memory(
                                "process_image:qwen_flash_preproc:parsed",
                                wines=len(wines2),
                                total_visible=result2.get("total_visible"),
                            )
                            if len(wines2) > len(result.get("wines", [])):
                                result = result2
                                layer_used = "qwen_flash_preproc"
                                print(f"[process_image] preproc improved: {len(wines2)} wines", flush=True)
                    except Exception as e2:
                        print(f"[process_image] preproc error: {e2}", flush=True)
                        log_memory("process_image:preproc:error", error=type(e2).__name__)

            except (json.JSONDecodeError, ValueError):
                print(f"[process_image] qwen parse failed, falling back", flush=True)
                log_memory("process_image:qwen_flash:parse_fail")
                result = None

        # --- CAMADA 3: Fallback Gemini (quando Qwen nao disponivel ou falhou) ---
        if result is None:
            print("[process_image] falling back to Gemini", flush=True)
            log_memory("process_image:gemini_fallback:start")
            t0_gemini = time.time()
            raw_text = _gemini_generate([
                IMAGE_UNIFIED_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ])
            gemini_ms = round((time.time() - t0_gemini) * 1000)
            result = _parse_gemini_json(raw_text)
            layer_used = "gemini_fallback"
            log_memory(
                "process_image:gemini_fallback:end",
                ms=gemini_ms,
                raw_chars=len(raw_text or ""),
                image_type=result.get("type"),
            )

        image_type = result.get("type", "not_wine")
        print(f"[process_image] layer={layer_used}, type={image_type}, "
              f"result={json.dumps(result, ensure_ascii=False)[:300]}", flush=True)
        log_memory(
            "process_image:end",
            total_ms=round((time.time() - t0_total) * 1000),
            layer=layer_used,
            image_type=image_type,
        )

        if image_type == "label":
            return _handle_label(result)
        elif image_type == "screenshot":
            return _handle_screenshot(result)
        elif image_type == "shelf":
            return _handle_shelf(result)
        else:
            desc = result.get("description", "conteudo nao relacionado a vinho")
            print(f"[process_image] not_wine: {desc}", flush=True)
            return {
                "message": f"Nao consegui identificar um vinho nessa imagem ({desc}). Tente outra foto!",
                "status": "not_wine",
                "image_type": "not_wine",
            }
    except Exception as e:
        print(f"[process_image] EXCEPTION: {type(e).__name__}: {e}", flush=True)
        log_memory("process_image:exception", error=type(e).__name__)
        return {
            "message": f"Erro ao processar imagem: {str(e)}. Descreva o vinho que voce viu!",
            "status": "error",
            "image_type": "error",
        }


def _handle_label(result):
    """Processa resultado tipo label."""
    parts = [result.get("name", "")]
    if result.get("producer"):
        parts.append(result["producer"])
    if result.get("vintage"):
        parts.append(str(result["vintage"]))
    if result.get("region"):
        parts.append(result["region"])
    search_text = " ".join(p for p in parts if p)

    desc_parts = [f"Rotulo identificado: {search_text}"]
    if result.get("price"):
        desc_parts.append(f"Preco na foto: {result['price']}")

    return {
        "status": "success",
        "image_type": "label",
        "ocr_result": result,
        "search_text": search_text,
        "description": " | ".join(desc_parts),
    }


def _handle_screenshot(result):
    """Processa resultado tipo screenshot."""
    wines = result.get("wines", [])
    if not wines:
        return {
            "status": "success",
            "image_type": "screenshot",
            "wines": [],
            "description": "Screenshot detectado mas nenhum vinho identificado.",
        }

    descriptions = []
    for w in wines:
        parts = [w.get("name", "?")]
        if w.get("price"):
            parts.append(f"preco: {w['price']}")
        if w.get("rating"):
            parts.append(f"nota: {w['rating']}")
        if w.get("source"):
            parts.append(f"fonte: {w['source']}")
        descriptions.append(" | ".join(parts))

    return {
        "status": "success",
        "image_type": "screenshot",
        "wines": wines,
        "description": f"Screenshot com {len(wines)} vinho(s): " + "; ".join(descriptions),
    }


def _handle_shelf(result):
    """Processa resultado tipo shelf/prateleira."""
    wines = result.get("wines", [])
    total = result.get("total_visible", len(wines))

    if not wines:
        return {
            "status": "success",
            "image_type": "shelf",
            "wines": [],
            "total_visible": total,
            "description": "Prateleira fotografada, nenhum rotulo legivel.",
        }

    descriptions = []
    for w in wines:
        parts = [w.get("name", "?")]
        if w.get("price"):
            parts.append(f"preco: {w['price']}")
        descriptions.append(" | ".join(parts))

    return {
        "status": "success",
        "image_type": "shelf",
        "wines": wines,
        "total_visible": total,
        "description": f"Prateleira com {len(wines)} vinho(s) identificado(s): " + "; ".join(descriptions),
    }


def process_images_batch(images):
    """Processa array de imagens. Deduplica vinhos repetidos. Retorna resultados consolidados."""
    t0 = time.time()
    log_memory("process_images_batch:start", count=len(images))
    results = []
    seen_names = set()

    for idx, img_b64 in enumerate(images, start=1):
        log_memory("process_images_batch:item_start", index=idx)
        item_result = process_image(img_b64)
        results.append(item_result)
        log_memory(
            "process_images_batch:item_end",
            index=idx,
            image_type=item_result.get("image_type"),
            status=item_result.get("status"),
        )

    labels = []
    all_wines = []
    screenshots = []
    shelves = []
    errors = []

    for r in results:
        img_type = r.get("image_type", "error")

        if img_type == "label":
            name = r.get("ocr_result", {}).get("name", "")
            name_key = name.lower().strip() if name else ""
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                labels.append(r)
            elif not name_key:
                labels.append(r)

        elif img_type == "screenshot":
            for w in r.get("wines", []):
                name_key = (w.get("name") or "").lower().strip()
                if name_key and name_key not in seen_names:
                    seen_names.add(name_key)
                    all_wines.append(w)
            screenshots.append(r)

        elif img_type == "shelf":
            for w in r.get("wines", []):
                name_key = (w.get("name") or "").lower().strip()
                if name_key and name_key not in seen_names:
                    seen_names.add(name_key)
                    all_wines.append(w)
            shelves.append(r)

        else:
            errors.append(r)

    parts = []
    for l in labels:
        parts.append(l.get("description", ""))
    for s in screenshots:
        parts.append(s.get("description", ""))
    for s in shelves:
        parts.append(s.get("description", ""))
    if errors:
        parts.append(f"{len(errors)} imagem(ns) sem vinho identificado")

    output = {
        "status": "success",
        "image_count": len(images),
        "labels": labels,
        "screenshots": screenshots,
        "shelves": shelves,
        "all_wines": all_wines,
        "errors": errors,
        "description": " | ".join(p for p in parts if p),
    }
    log_memory(
        "process_images_batch:end",
        total_ms=round((time.time() - t0) * 1000),
        labels=len(labels),
        screenshots=len(screenshots),
        shelves=len(shelves),
        all_wines=len(all_wines),
        errors=len(errors),
    )
    return output


def process_video(base64_video):
    """Processa video: extrai frames com ffmpeg, envia cada frame ao Gemini, consolida vinhos."""
    if not shutil.which("ffmpeg"):
        return {
            "message": (
                "O processamento de video requer ffmpeg instalado no servidor. "
                "Este componente ainda nao esta disponivel neste ambiente. "
                "Por enquanto, me diga o nome do vinho que aparece no video!"
            ),
            "status": "error_ffmpeg_missing",
        }

    tmpdir = None
    video_path = None
    try:
        video_bytes = base64.b64decode(base64_video)
        if len(video_bytes) > 50 * 1024 * 1024:
            return {
                "message": "O video e muito grande (maximo 50 MB). Tente um video mais curto!",
                "status": "error_too_large",
            }

        tmpdir = tempfile.mkdtemp(prefix="winegod_video_")
        video_path = os.path.join(tmpdir, "input_video")
        with open(video_path, "wb") as f:
            f.write(video_bytes)

        try:
            probe_result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            duration = float(probe_result.stdout.strip())
            if duration > 30:
                return {
                    "message": "O video e muito longo (maximo 30 segundos). Tente um video mais curto!",
                    "status": "error_too_long",
                }
        except (ValueError, subprocess.TimeoutExpired):
            duration = 30

        frames_dir = os.path.join(tmpdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", "fps=1",
                "-frames:v", "30",
                os.path.join(frames_dir, "frame_%03d.jpg"),
            ],
            capture_output=True, timeout=60,
        )

        frame_files = sorted([
            os.path.join(frames_dir, f)
            for f in os.listdir(frames_dir)
            if f.endswith(".jpg")
        ])

        if not frame_files:
            return {
                "message": "Nao consegui extrair frames do video. Tente outro formato (mp4, mov, webm)!",
                "status": "error_no_frames",
            }

        all_wines = []

        for frame_path in frame_files:
            try:
                frame_bytes = _resize_frame_bytes(frame_path, max_side=1024)
                raw_text = _gemini_generate([
                    VIDEO_FRAME_PROMPT,
                    types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg"),
                ])
                result = _parse_gemini_json(raw_text)
                wines = result.get("wines", [])
                all_wines.extend(wines)
            except Exception:
                continue

        unique_wines = _deduplicate_wines(all_wines)

        if not unique_wines:
            return {
                "message": (
                    "Assisti ao video mas nao consegui identificar vinhos. "
                    "Tente filmar o rotulo mais de perto ou me diga o nome do vinho!"
                ),
                "status": "no_wines_found",
            }

        description = _wines_to_description(unique_wines, "video")

        return {
            "status": "success",
            "wines": unique_wines,
            "wine_count": len(unique_wines),
            "frames_analyzed": len(frame_files),
            "description": description,
        }

    except Exception as e:
        return {
            "message": f"Erro ao processar video: {str(e)}. Descreva o vinho que aparece no video!",
            "status": "error",
        }
    finally:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


# Keywords que indicam conteudo sobre vinho (precisa >= 2 matches)
_WINE_KEYWORDS = {
    "vinho", "vinhos", "wine", "wines", "vino", "vini",
    "tinto", "branco", "rosé", "espumante", "sparkling",
    "reserva", "gran reserva", "crianza",
    "cabernet", "merlot", "chardonnay", "sauvignon", "pinot",
    "syrah", "shiraz", "malbec", "tempranillo", "carmenere",
    "tannat", "touriga", "sangiovese", "nebbiolo", "grenache",
    "safra", "vintage", "colheita",
    "chateau", "château", "domaine", "bodega", "cantina",
    "carta de vinhos", "wine list", "wine menu",
    "sommelier",
}


def _text_looks_wine_related(text, min_matches=2):
    """Checa se texto extraido contem keywords de vinho suficientes.

    Amostra inicio, meio e fim do texto para nao perder catalogos
    com prefacio/capa longa antes dos vinhos.
    """
    n = len(text)
    chunk = 2000
    # Inicio + meio + fim (sem duplicar se texto for curto)
    parts = [text[:chunk]]
    if n > chunk * 2:
        mid = n // 2
        parts.append(text[mid - chunk // 2 : mid + chunk // 2])
    if n > chunk:
        parts.append(text[-chunk:])
    sample = " ".join(parts).lower()
    matches = sum(1 for kw in _WINE_KEYWORDS if kw in sample)
    return matches >= min_matches


def _split_text_into_chunks(text, chunk_size=8000):
    """Divide texto em chunks de aproximadamente chunk_size chars.

    Respeita limites de paragrafo (dupla newline). Se um paragrafo isolado
    exceder chunk_size, divide por linha simples. Nao garante tamanho exato
    — prioridade e preservar estrutura legivel para o Gemini.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current = []
    current_size = 0

    for paragraph in text.split("\n\n"):
        p_size = len(paragraph) + 2  # +2 para o separador \n\n

        if p_size > chunk_size:
            # Paragrafo gigante: flush current e divide por linha
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_size = 0

            sub_lines = []
            sub_size = 0
            for line in paragraph.split("\n"):
                line_size = len(line) + 1
                if sub_size + line_size > chunk_size and sub_lines:
                    chunks.append("\n".join(sub_lines))
                    sub_lines = [line]
                    sub_size = line_size
                else:
                    sub_lines.append(line)
                    sub_size += line_size
            if sub_lines:
                chunks.append("\n".join(sub_lines))
        elif current_size + p_size > chunk_size and current:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_size = p_size
        else:
            current.append(paragraph)
            current_size += p_size

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _extract_wines_native_chunked(text, chunk_size=8000, max_workers=4):
    """Extrai vinhos dividindo texto em chunks e chamando Gemini em PARALELO.

    Usa ThreadPoolExecutor com limite fixo de max_workers (default 4) para que o
    tempo total seja ~max(chunk_time) em vez de sum(chunk_time). Chunks que falham
    sao descartados silenciosamente; chunks que sucedem contribuem com seus
    vinhos. Caller e responsavel por deduplicar.

    Usado tanto como caminho direto para texto MUITO longo wine-related (pulando
    chamada monolitica cara) quanto como recovery quando a chamada monolitica de
    texto medio falha.
    """
    chunks = _split_text_into_chunks(text, chunk_size)
    if not chunks:
        return []

    def _process_chunk(args):
        idx, chunk = args
        prompt_text = PDF_TEXT_PROMPT + chunk
        try:
            # Tenta Qwen-turbo (mais barato), fallback Gemini
            raw = _qwen_text_generate(prompt_text)
            if raw is None:
                raw = _gemini_generate(prompt_text, thinking=False)
            result = _parse_gemini_json(raw)
            return idx, result.get("wines", []), None
        except Exception as e:
            return idx, [], e

    workers = min(max_workers, len(chunks))
    all_wines = []
    success_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for idx, wines, err in executor.map(
            _process_chunk, list(enumerate(chunks))
        ):
            if err is None:
                all_wines.extend(wines)
                success_count += 1
                print(
                    f"[chunked] chunk {idx+1}/{len(chunks)}: {len(wines)} wines",
                    flush=True,
                )
            else:
                print(
                    f"[chunked] chunk {idx+1}/{len(chunks)} failed: {type(err).__name__}",
                    flush=True,
                )

    print(
        f"[chunked] total: {len(all_wines)} wines from {success_count}/{len(chunks)} chunks "
        f"(parallel x{workers})",
        flush=True,
    )
    return all_wines


def process_pdf(base64_pdf):
    """Processa PDF: extrai texto com pdfplumber, fallback OCR visual com pypdfium2 + Gemini."""
    tmpdir = None
    try:
        import pdfplumber

        pdf_bytes = base64.b64decode(base64_pdf)
        if len(pdf_bytes) > 20 * 1024 * 1024:
            return {
                "message": "O PDF e muito grande (maximo 20 MB). Tente um arquivo menor!",
                "status": "error_too_large",
            }

        tmpdir = tempfile.mkdtemp(prefix="winegod_pdf_")
        pdf_path = os.path.join(tmpdir, "input.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            page_count = min(len(pdf.pages), 20)
            for page in pdf.pages[:page_count]:
                page_text = page.extract_text() or ""
                text_pages.append(page_text)

        full_text = "\n\n".join(text_pages).strip()

        all_wines = []
        extraction_method = "none"
        was_truncated = False
        native_text_failed = False

        # Branch 1: texto nativo extraido com pdfplumber
        if len(full_text) > 100:
            was_truncated = len(full_text) > 30000
            truncated_text = full_text[:30000]

            # P3A.2: para texto MUITO longo wine-related, pular chamada monolitica
            # cara (que tipicamente leva 150-260s e/ou retorna JSON malformado em
            # PDFs com 100+ vinhos) e ir DIRETO para chunked paralelo. Isso evita
            # gastar metade do orcamento de 300s antes do recovery comecar.
            if (
                len(full_text) > _LONG_TEXT_THRESHOLD
                and _text_looks_wine_related(full_text)
            ):
                print(
                    f"[process_pdf] long wine text ({len(full_text)} chars) — "
                    f"direct parallel chunked (skip monolithic)",
                    flush=True,
                )
                try:
                    wines_from_text = _extract_wines_native_chunked(truncated_text)
                    if wines_from_text:
                        all_wines.extend(wines_from_text)
                        extraction_method = "native_text_chunked"
                        print(
                            f"[process_pdf] native_text_chunked (direct): "
                            f"{len(wines_from_text)} wines",
                            flush=True,
                        )
                except Exception as e:
                    print(f"[process_pdf] direct chunked error: {e}", flush=True)
            else:
                # Texto curto/medio: caminho rapido — Qwen-turbo primeiro, fallback Gemini
                try:
                    prompt_text = PDF_TEXT_PROMPT + truncated_text
                    raw_text = _qwen_text_generate(prompt_text)
                    provider = "qwen_turbo"
                    if raw_text is None:
                        raw_text = _gemini_generate(prompt_text, thinking=False)
                        provider = "gemini"
                    result = _parse_gemini_json(raw_text)
                    wines_from_text = result.get("wines", [])
                    if wines_from_text:
                        all_wines.extend(wines_from_text)
                        extraction_method = "native_text"
                        print(
                            f"[process_pdf] native_text ({provider}): {len(wines_from_text)} wines",
                            flush=True,
                        )
                except Exception as e:
                    native_text_failed = True
                    print(f"[process_pdf] native_text error: {e}", flush=True)

        # Branch 1.5: recovery nativo paralelo — so se a monolitica de texto medio
        # raise E texto parece ser wine-related. Evita cair no visual_fallback lento
        # para PDFs cujo unico problema foi JSON malformado do Gemini.
        if not all_wines and native_text_failed and _text_looks_wine_related(full_text):
            print("[process_pdf] trying parallel chunked recovery", flush=True)
            try:
                chunked_wines = _extract_wines_native_chunked(full_text[:30000])
                if chunked_wines:
                    all_wines.extend(chunked_wines)
                    extraction_method = "native_text_chunked"
                    print(
                        f"[process_pdf] native_text_chunked (recovery): "
                        f"{len(chunked_wines)} wines",
                        flush=True,
                    )
            except Exception as e:
                print(f"[process_pdf] chunked recovery error: {e}", flush=True)

        # Branch 2: fallback visual — so se nao achou vinhos E faz sentido tentar
        if not all_wines:
            text_is_substantial = len(full_text) > 100
            text_is_wine = _text_looks_wine_related(full_text) if text_is_substantial else False

            # Fallback se: texto curto/ausente (PDF escaneado) OU texto parece ser sobre vinho
            should_fallback = not text_is_substantial or text_is_wine
            print(
                f"[process_pdf] fallback: text_len={len(full_text)}, "
                f"wine_related={text_is_wine if text_is_substantial else 'N/A'}, "
                f"will_try={should_fallback}", flush=True,
            )

            if should_fallback:
                try:
                    import pypdfium2 as pdfium
                    from PIL import Image
                    import io

                    doc = pdfium.PdfDocument(pdf_path)
                    ocr_page_count = min(len(doc), 20)

                    for i in range(ocr_page_count):
                        try:
                            page = doc[i]
                            bitmap = page.render(scale=150 / 72)
                            pil_image = bitmap.to_pil()

                            w, h = pil_image.size
                            max_side = 1024
                            if w > max_side or h > max_side:
                                if w > h:
                                    new_w = max_side
                                    new_h = int(h * max_side / w)
                                else:
                                    new_h = max_side
                                    new_w = int(w * max_side / h)
                                pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)

                            buf = io.BytesIO()
                            pil_image.save(buf, format="JPEG", quality=85)
                            img_bytes = buf.getvalue()

                            # Tenta Qwen-flash (mais barato), fallback Gemini
                            raw_text = _qwen_generate(img_bytes, "image/jpeg", PDF_IMAGE_PROMPT)
                            if raw_text is None:
                                raw_text = _gemini_generate([
                                    PDF_IMAGE_PROMPT,
                                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                                ])
                            result = _parse_gemini_json(raw_text)
                            all_wines.extend(result.get("wines", []))
                        except Exception:
                            continue

                    doc.close()

                    if all_wines:
                        extraction_method = "visual_fallback"
                        print(f"[process_pdf] visual_fallback: {len(all_wines)} wines", flush=True)
                except ImportError:
                    print("[process_pdf] pypdfium2 not available, skipping visual", flush=True)
            else:
                extraction_method = "native_text_no_wine"
                print("[process_pdf] skipped visual: text not wine-related", flush=True)

        unique_wines = _deduplicate_wines(all_wines)

        if not unique_wines:
            if extraction_method == "native_text_no_wine":
                msg = (
                    "Li o PDF mas o conteudo nao parece ser uma carta ou catalogo de vinhos. "
                    "Envie um PDF com lista de vinhos ou me diga os vinhos que te interessam!"
                )
            else:
                msg = (
                    "Li o PDF mas nao consegui identificar vinhos. "
                    "Se for uma carta de vinhos, tente um PDF com texto selecionavel "
                    "ou me diga os vinhos que te interessam!"
                )
            return {
                "message": msg,
                "status": "no_wines_found",
                "extraction_method": extraction_method,
            }

        description = _wines_to_description(unique_wines, "PDF")

        return {
            "status": "success",
            "wines": unique_wines,
            "wine_count": len(unique_wines),
            "description": description,
            "extraction_method": extraction_method,
            "was_truncated": was_truncated,
            "pages_processed": page_count,
        }

    except Exception as e:
        return {
            "message": f"Erro ao processar PDF: {str(e)}. Descreva os vinhos da carta!",
            "status": "error",
        }
    finally:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


def process_voice(audio_text):
    """Voz ja vem transcrita do frontend — repassa como busca."""
    if not audio_text or not audio_text.strip():
        return {"message": "Nao consegui entender o audio. Pode repetir?"}
    return {"transcribed_text": audio_text.strip(), "action": "search"}


def extract_wines_from_text(text):
    """Extrai vinhos de texto puro (carta colada, transcricao, etc).

    Usa Qwen-turbo com PDF_TEXT_PROMPT (validado).
    Para texto muito longo (>_LONG_TEXT_THRESHOLD), usa chunked paralelo.
    Retorna dict compativel com process_pdf:
        {"wines": [...], "wine_count": N, "status": "success"|"no_wines"|"too_short"|"error"}
    """
    if not text or len(text.strip()) < 20:
        return {"wines": [], "wine_count": 0, "status": "too_short"}

    try:
        clean = text.strip()

        # Texto longo wine-related: chunked paralelo (mesma logica de process_pdf)
        if len(clean) > _LONG_TEXT_THRESHOLD and _text_looks_wine_related(clean):
            wines = _extract_wines_native_chunked(clean[:30000])
            if wines:
                unique = _deduplicate_wines(wines)
                return {"wines": unique, "wine_count": len(unique), "status": "success"}
            return {"wines": [], "wine_count": 0, "status": "no_wines"}

        # Texto curto/medio: monolitico (Qwen primeiro, fallback Gemini)
        prompt = PDF_TEXT_PROMPT + clean
        raw = _qwen_text_generate(prompt)
        if raw is None:
            raw = _gemini_generate(prompt, thinking=False)

        result = _parse_gemini_json(raw)
        wines = result.get("wines", [])

        if not wines:
            return {"wines": [], "wine_count": 0, "status": "no_wines"}

        unique = _deduplicate_wines(wines)
        return {"wines": unique, "wine_count": len(unique), "status": "success"}
    except Exception as e:
        print(f"[extract_wines_from_text] error: {type(e).__name__}: {e}", flush=True)
        return {"wines": [], "wine_count": 0, "status": "error"}
