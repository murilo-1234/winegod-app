"""Media processing: process_image, process_video, process_pdf, process_voice."""

import base64
import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile

from google import genai
from google.genai import types


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


def _gemini_generate(contents):
    """Chama Gemini generate_content com o modelo padrao."""
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )
    return response.text


# --- Prompts ---

IMAGE_UNIFIED_PROMPT = """You are a wine-image analyst. Classify this image as ONE of:

## Classification rules

"label" — One wine or SKU DOMINATES the scene visually. The label/bottle occupies most of the frame.
  - Use "label" even if there are 2-5 copies of the SAME wine side by side (e.g. supermarket facing).
  - Use "label" if one wine is clearly the main subject and background bottles are blurry or secondary.
  - Do NOT require a single isolated bottle. Visual dominance is the criterion, not bottle count.

"screenshot" — A screen capture or digital interface showing wine information (app, website, price list, search results).

"shelf" — A photo showing MULTIPLE DIFFERENT wines together on a shelf, display, rack, or table where no single wine dominates the frame.

"not_wine" — The image does not contain wine-related content.

## Output schemas (return ONLY valid JSON, no extra text)

If type is "label":
{"type": "label", "name": "full wine name", "producer": "winery or null", "vintage": "year or null", "region": "region or null", "grape": "grape variety or null", "price": "price with currency or null"}

If type is "screenshot":
{"type": "screenshot", "wines": [{"name": "wine name", "producer": "winery or null", "price": "price or null", "rating": "rating or null", "source": "app/site name or null"}]}

If type is "shelf":
{"type": "shelf", "wines": [{"name": "full wine name as read", "producer": "winery or null", "line": "wine line/range or null", "variety": "grape variety or null", "classification": "Reserva/Gran Reserva/etc or null", "style": "red/white/rosé/sparkling or null", "price": "price or null"}], "total_visible": 0}

If type is "not_wine":
{"type": "not_wine", "description": "brief description of what the image shows"}

## Price rules (CRITICAL for Brazilian supermarket labels)
Brazilian shelf price tags often show multiple values:
  - "PRECO R$T 1 L R$146.60" = price per liter — IGNORE this
  - "R$ 189,99" (larger, usually at bottom) = unit price of the bottle — USE THIS
  - Always extract the UNIT PRICE of the bottle (typically 750ml), never the per-liter price
  - If multiple price values are visible for the same wine, pick the one labeled as the bottle/unit price
  - If unsure which price is the unit price, return null rather than guessing
  - Preserve the original currency symbol (R$, $, €, etc.)

## Name cleanup rules
  - Use the FULL wine name as printed on the label, not abbreviated
  - Fix obvious OCR artifacts: if a letter is clearly wrong based on context, correct it
    (e.g. "PONTGRAS" on a Chilean wine shelf is almost certainly "MONTGRAS")
  - Include winery + wine line + variety when visible (e.g. "MontGras Aura Reserva Cabernet Sauvignon")
  - Do NOT invent or guess parts of the name you cannot read — use what is legible
  - Separate winery (producer) from wine name when both are clearly distinct on the label

## Grape variety rules
  - Only report grape varieties you can CLEARLY read on the label
  - If partially obscured or ambiguous, return null rather than guessing
  - Common confusions to avoid: Petit Verdot vs Petit Sirah, Grenache vs Garnacha (same grape, both acceptable), Syrah vs Shiraz (same grape, both acceptable)
  - If you see only 2-3 letters of a grape name, return null

## Shelf and screenshot producer rules
  - For each wine, extract "producer" (winery) separately when clearly visible
  - Keep the FULL wine name in "name" including winery prefix if that is how it reads (e.g. name: "MontGras Reserva Cabernet", producer: "MontGras")
  - Use null for producer if not legible — do NOT guess or infer from the wine name

## Shelf-specific rules
  - "wines" list: include only wines whose names you can confidently read
  - Deduplicate: if the same wine appears multiple times on the shelf, list it only ONCE
  - "total_visible": estimate the number of DISTINCT wine labels/SKUs visible (not total physical bottles). 10 copies of the same wine = 1 SKU. Be conservative — when uncertain, estimate lower.
  - For each wine in the list, extract price if a price tag is clearly associated with it

## Shelf structured fields (for each wine)
  - "name": keep the FULL wine name as printed (winery + line + variety + classification). This is the primary field — always fill it.
  - "line": the wine LINE or RANGE within the producer. Examples: "Aura" in "MontGras Aura Reserva Carmenere", "Family Wines" in "Casa Silva Family Wines Cabernet Sauvignon", "Day One" in "MontGras Day One Carmenere". Use null if not identifiable or if the wine has no distinct line name.
  - "variety": grape variety when clearly readable (e.g. "Carmenere", "Cabernet Sauvignon", "Merlot", "Chardonnay"). Use null if not visible.
  - "classification": quality tier when visible (e.g. "Reserva", "Gran Reserva", "Crianza"). Use null if not visible.
  - "style": overall wine style — use exactly one of: "red", "white", "rosé", "sparkling". Use null if not determinable from the label.
  - Do NOT guess or infer structured fields from context — only extract what you can clearly read.

## General rules
  - Always use null for fields you truly cannot determine
  - Return ONLY valid parseable JSON — no markdown, no commentary, no extra text
  - Do not wrap JSON in code fences"""

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
    """Deduplicate wines by normalized name."""
    seen = {}
    for wine in all_wines:
        name = (wine.get("name") or "").strip().lower()
        if not name:
            continue
        if name not in seen:
            seen[name] = wine
        else:
            existing = seen[name]
            for key in wine:
                if wine[key] and not existing.get(key):
                    existing[key] = wine[key]
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
    """Envia imagem para Gemini Flash. Detecta label, screenshot, shelf ou not_wine."""
    try:
        image_bytes = base64.b64decode(base64_image)

        mime_type = _detect_mime_type(image_bytes)
        print(f"[process_image] bytes={len(image_bytes)}, mime={mime_type}", flush=True)

        raw_text = _gemini_generate([
            IMAGE_UNIFIED_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ])

        print(f"[process_image] gemini_raw={raw_text[:500]}", flush=True)

        result = _parse_gemini_json(raw_text)
        image_type = result.get("type", "not_wine")
        print(f"[process_image] parsed_type={image_type}, result={json.dumps(result, ensure_ascii=False)[:300]}", flush=True)

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
    results = []
    seen_names = set()

    for img_b64 in images:
        results.append(process_image(img_b64))

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

    return {
        "status": "success",
        "image_count": len(images),
        "labels": labels,
        "screenshots": screenshots,
        "shelves": shelves,
        "all_wines": all_wines,
        "errors": errors,
        "description": " | ".join(p for p in parts if p),
    }


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
        try:
            raw = _gemini_generate(PDF_TEXT_PROMPT + chunk)
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
                # Texto curto/medio: caminho rapido com chamada monolitica unica
                try:
                    raw_text = _gemini_generate(PDF_TEXT_PROMPT + truncated_text)
                    result = _parse_gemini_json(raw_text)
                    wines_from_text = result.get("wines", [])
                    if wines_from_text:
                        all_wines.extend(wines_from_text)
                        extraction_method = "native_text"
                        print(
                            f"[process_pdf] native_text: {len(wines_from_text)} wines",
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
