"""Media processing: process_image, process_video, process_pdf, process_voice."""

import base64
import json
import os
import shutil
import subprocess
import tempfile

import google.generativeai as genai

# Garantir ffmpeg no PATH via imageio-ffmpeg (pacote Python com binario embutido)
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except ImportError:
    pass

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

GEMINI_MODEL = "gemini-2.0-flash"

# --- Prompts ---

IMAGE_UNIFIED_PROMPT = """Analyze this image and determine what it contains. Classify as ONE of:
- "label": a wine bottle label or close-up of a single wine bottle
- "screenshot": a screenshot or screen capture showing wine info (app, website, list)
- "shelf": a photo of a wine shelf, display, or multiple bottles together
- "not_wine": the image does not contain wine-related content

Return ONLY a JSON object. The "type" field is always required.

If type is "label":
{"type": "label", "name": "full wine name", "producer": "winery or null", "vintage": "year or null", "region": "region or null", "grape": "grape or null"}

If type is "screenshot":
{"type": "screenshot", "wines": [{"name": "wine name", "price": "price or null", "rating": "rating or null", "source": "app/site name or null"}]}

If type is "shelf":
{"type": "shelf", "wines": [{"name": "wine name", "price": "price or null"}], "total_visible": 0}
(total_visible = estimated total bottles visible, even if you can't read all labels)

If type is "not_wine":
{"type": "not_wine", "description": "brief description of what the image shows"}

Rules:
- For label: extract as much detail as possible from the label
- For screenshot: list ALL wines visible with prices/ratings when shown
- For shelf: list wines whose labels you can read; estimate total_visible count
- Always use null for fields you cannot determine
- Return ONLY valid JSON, no extra text"""

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
Identify ALL wines mentioned with as much detail as possible:
- Wine name
- Producer/Winery
- Vintage year
- Region
- Grape variety
- Price

Return ONLY a JSON object:
{"wines": [{"name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "...", "price": "..."}]}

If you cannot identify a field, use null.

Text:
"""

PDF_IMAGE_PROMPT = """Analyze this page image from a PDF document (wine list, catalog, or menu).
Identify ALL wines visible with as much detail as possible:
- Wine name
- Producer/Winery
- Vintage year
- Region
- Grape variety
- Price

Return ONLY a JSON object:
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
            # Merge: fill nulls from later occurrences
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

def process_image(base64_image):
    """Envia imagem para Gemini Flash. Detecta label, screenshot, shelf ou not_wine."""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        image_bytes = base64.b64decode(base64_image)

        response = model.generate_content([
            IMAGE_UNIFIED_PROMPT,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        result = _parse_gemini_json(response.text)
        image_type = result.get("type", "not_wine")

        if image_type == "label":
            return _handle_label(result)
        elif image_type == "screenshot":
            return _handle_screenshot(result)
        elif image_type == "shelf":
            return _handle_shelf(result)
        else:
            desc = result.get("description", "conteudo nao relacionado a vinho")
            return {
                "message": f"Nao consegui identificar um vinho nessa imagem ({desc}). Tente outra foto!",
                "status": "not_wine",
                "image_type": "not_wine",
            }
    except Exception as e:
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

    return {
        "status": "success",
        "image_type": "label",
        "ocr_result": result,
        "search_text": search_text,
        "description": f"Rotulo identificado: {search_text}",
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
            "description": f"Prateleira com ~{total} garrafas, nenhuma legivel.",
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
        "description": f"Prateleira com ~{total} garrafas, {len(wines)} identificadas: " + "; ".join(descriptions),
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
    # Check ffmpeg availability
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
        # Decode and validate size (50 MB max)
        video_bytes = base64.b64decode(base64_video)
        if len(video_bytes) > 50 * 1024 * 1024:
            return {
                "message": "O video e muito grande (maximo 50 MB). Tente um video mais curto!",
                "status": "error_too_large",
            }

        # Save to temp file
        tmpdir = tempfile.mkdtemp(prefix="winegod_video_")
        video_path = os.path.join(tmpdir, "input_video")
        with open(video_path, "wb") as f:
            f.write(video_bytes)

        # Validate duration (max 30s)
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
            # If we can't determine duration, proceed anyway (best effort)
            duration = 30

        # Extract 1 frame per second (max 30)
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

        # Collect frame files
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

        # Send each frame to Gemini
        model = genai.GenerativeModel(GEMINI_MODEL)
        all_wines = []

        for frame_path in frame_files:
            try:
                frame_bytes = _resize_frame_bytes(frame_path, max_side=1024)
                response = model.generate_content([
                    VIDEO_FRAME_PROMPT,
                    {"mime_type": "image/jpeg", "data": frame_bytes}
                ])
                result = _parse_gemini_json(response.text)
                wines = result.get("wines", [])
                all_wines.extend(wines)
            except Exception:
                # Skip frames that fail
                continue

        # Deduplicate
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


def process_pdf(base64_pdf):
    """Processa PDF: extrai texto com pdfplumber, fallback OCR visual com pypdfium2 + Gemini."""
    tmpdir = None
    try:
        import pdfplumber

        # Decode and validate size (20 MB max)
        pdf_bytes = base64.b64decode(base64_pdf)
        if len(pdf_bytes) > 20 * 1024 * 1024:
            return {
                "message": "O PDF e muito grande (maximo 20 MB). Tente um arquivo menor!",
                "status": "error_too_large",
            }

        # Save to temp file
        tmpdir = tempfile.mkdtemp(prefix="winegod_pdf_")
        pdf_path = os.path.join(tmpdir, "input.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Extract text with pdfplumber (max 20 pages)
        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            page_count = min(len(pdf.pages), 20)
            for page in pdf.pages[:page_count]:
                page_text = page.extract_text() or ""
                text_pages.append(page_text)

        full_text = "\n\n".join(text_pages).strip()

        model = genai.GenerativeModel(GEMINI_MODEL)
        all_wines = []

        # If text is sufficient (more than 100 chars), use text-based analysis
        if len(full_text) > 100:
            try:
                # Truncate to avoid token limits (roughly 30k chars)
                truncated = full_text[:30000]
                response = model.generate_content(PDF_TEXT_PROMPT + truncated)
                result = _parse_gemini_json(response.text)
                all_wines.extend(result.get("wines", []))
            except Exception:
                # If text analysis fails, fall through to image OCR
                all_wines = []

        # If text was poor or text analysis found nothing, try image OCR
        if not all_wines:
            try:
                import pypdfium2 as pdfium
                from PIL import Image
                import io

                doc = pdfium.PdfDocument(pdf_path)
                ocr_page_count = min(len(doc), 20)

                for i in range(ocr_page_count):
                    try:
                        page = doc[i]
                        # Render at 150 DPI for good OCR quality
                        bitmap = page.render(scale=150 / 72)
                        pil_image = bitmap.to_pil()

                        # Resize if needed
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

                        response = model.generate_content([
                            PDF_IMAGE_PROMPT,
                            {"mime_type": "image/jpeg", "data": img_bytes}
                        ])
                        result = _parse_gemini_json(response.text)
                        all_wines.extend(result.get("wines", []))
                    except Exception:
                        continue

                doc.close()
            except ImportError:
                # pypdfium2 not available — only text-based analysis was possible
                pass

        # Deduplicate
        unique_wines = _deduplicate_wines(all_wines)

        if not unique_wines:
            return {
                "message": (
                    "Li o PDF mas nao consegui identificar vinhos. "
                    "Se for uma carta de vinhos, tente enviar uma foto mais nitida "
                    "ou me diga os vinhos que te interessam!"
                ),
                "status": "no_wines_found",
            }

        description = _wines_to_description(unique_wines, "PDF")

        return {
            "status": "success",
            "wines": unique_wines,
            "wine_count": len(unique_wines),
            "description": description,
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
