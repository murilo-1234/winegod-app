import anthropic
from config import Config
from prompts.baco_system import BACO_SYSTEM_PROMPT

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
TEMPERATURE = 0.7

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def get_baco_response(message, session_id, history=None):
    """Envia mensagem para Claude e retorna resposta completa do Baco."""
    if history is None:
        history = []

    messages = _build_messages(history, message)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=BACO_SYSTEM_PROMPT,
        messages=messages,
    )

    return response.content[0].text, response.model


def stream_baco_response(message, session_id, history=None):
    """Envia mensagem para Claude e retorna generator com chunks do Baco (SSE)."""
    if history is None:
        history = []

    messages = _build_messages(history, message)

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=BACO_SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def _build_messages(history, current_message):
    """Monta lista de mensagens para a API (historico + mensagem atual)."""
    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": current_message})
    return messages
