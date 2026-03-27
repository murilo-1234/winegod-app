"""Stubs de media: process_image, process_video, process_pdf, process_voice."""


def process_image(base64_image):
    """STUB — OCR de rotulo/cardapio ainda nao implementado."""
    return {
        "message": (
            "O reconhecimento de imagens (OCR) ainda esta sendo preparado. "
            "Por enquanto, descreva o vinho que voce viu no rotulo e eu busco pra voce!"
        ),
        "status": "not_implemented",
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
