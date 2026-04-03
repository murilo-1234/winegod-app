import anthropic
from config import Config
from prompts.baco_system import BACO_SYSTEM_PROMPT
from tools.schemas import TOOLS
from tools.executor import execute_tool

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
TEMPERATURE = 0.7
MAX_TOOL_ROUNDS = 5

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def get_baco_response(message, session_id, history=None):
    """Envia mensagem para Claude e retorna resposta completa do Baco.
    Processa tool_use em loop ate obter resposta de texto."""
    if history is None:
        history = []

    messages = _build_messages(history, message)

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=BACO_SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        # Se a resposta e apenas texto, retornar
        if response.stop_reason == "end_turn":
            text = _extract_text(response)
            return text, response.model

        # Se tem tool_use, executar tools e continuar o loop
        if response.stop_reason == "tool_use":
            # Adicionar a resposta do assistant (com tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Executar cada tool e montar tool_result
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            # Qualquer outro stop_reason, extrair texto e retornar
            text = _extract_text(response)
            return text, response.model

    # Se atingiu o limite de rounds, extrair o que tiver
    text = _extract_text(response)
    return text, response.model


def stream_baco_response(message, session_id, history=None):
    """Envia mensagem para Claude e retorna generator com chunks do Baco (SSE).
    Primeiro resolve todas as tools (sem streaming), depois faz streaming da resposta final."""
    if history is None:
        history = []

    messages = _build_messages(history, message)
    used_tools = False

    # Fase 1: Resolver tools em loop (sem streaming)
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=BACO_SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        if response.stop_reason != "tool_use":
            if not used_tools:
                # Nenhuma tool usada — refazer como streaming
                break
            # Tools foram usadas, esta response ja e o texto final
            for block in response.content:
                if hasattr(block, 'text'):
                    yield block.text
            return

        used_tools = True
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    # Fase 2: Streaming (primeira chamada sem tools, ou apos MAX_TOOL_ROUNDS)
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=BACO_SYSTEM_PROMPT,
        messages=messages,
        tools=TOOLS,
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


def _extract_text(response):
    """Extrai texto da resposta do Claude (ignora tool_use blocks)."""
    parts = []
    for block in response.content:
        if hasattr(block, 'text'):
            parts.append(block.text)
    return "".join(parts) if parts else ""
