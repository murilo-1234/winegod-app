"""Stubs de media: process_image, process_video, process_pdf, process_voice."""

import base64
import json
import os

import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def process_image(base64_image):
    """Envia imagem para Gemini Flash e extrai info do rotulo de vinho."""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")

        image_bytes = base64.b64decode(base64_image)

        prompt = """Analyze this wine label/bottle image. Extract:
        - Wine name (full name as on label)
        - Producer/Winery
        - Vintage year (if visible)
        - Region (if visible)
        - Grape variety (if visible)

        Return ONLY a JSON object with these fields:
        {"name": "...", "producer": "...", "vintage": "...", "region": "...", "grape": "..."}

        If you cannot identify a field, use null.
        If this is NOT a wine image, return {"error": "not_wine"}"""

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(text)

        if "error" in result:
            return {
                "message": "Nao consegui identificar um vinho nessa imagem. Tente outra foto!",
                "status": "not_wine",
            }

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
            "ocr_result": result,
            "search_text": search_text,
            "description": f"Rotulo identificado: {search_text}",
        }
    except Exception as e:
        return {
            "message": f"Erro ao processar imagem: {str(e)}. Descreva o vinho que voce viu!",
            "status": "error",
        }


def process_video(base64_video):
    """STUB — processamento de video ainda nao implementado."""
    return {
        "message": (
            "O processamento de video ainda esta sendo preparado. "
            "Por enquanto, me diga o nome do vinho que aparece no video!"
        ),
        "status": "not_implemented",
    }


def process_pdf(base64_pdf):
    """STUB — processamento de PDF ainda nao implementado."""
    return {
        "message": (
            "A leitura de PDFs (cartas de vinho, catalogos) ainda esta sendo preparada. "
            "Por enquanto, me diga os vinhos da carta que te interessam!"
        ),
        "status": "not_implemented",
    }


def process_voice(audio_text):
    """Voz ja vem transcrita do frontend — repassa como busca."""
    if not audio_text or not audio_text.strip():
        return {"message": "Nao consegui entender o audio. Pode repetir?"}
    return {"transcribed_text": audio_text.strip(), "action": "search"}
