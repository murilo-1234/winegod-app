import anthropic
from config import Config
from prompts.baco_system import BACO_SYSTEM_PROMPT
from tools.schemas import TOOLS, TOOLS_PHOTO_MODE
from tools.executor import execute_tool

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048
TEMPERATURE = 0.7
MAX_TOOL_ROUNDS = 5

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def get_baco_response(message, session_id, history=None, photo_mode=False, trace=None):
    """Envia mensagem para Claude e retorna resposta completa do Baco.
    Processa tool_use em loop ate obter resposta de texto."""
    if history is None:
        history = []

    messages = _build_messages(history, message)
    tools = TOOLS_PHOTO_MODE if photo_mode else TOOLS

    for _ in range(MAX_TOOL_ROUNDS):
        if trace:
            trace.add_claude_round()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=BACO_SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason == "end_turn":
            text = _extract_text(response)
            return text, response.model

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if trace:
                        trace.add_tool(block.name)
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            text = _extract_text(response)
            return text, response.model

    text = _extract_text(response)
    return text, response.model


def stream_baco_response(message, session_id, history=None, photo_mode=False, trace=None):
    """Envia mensagem para Claude e retorna generator com chunks do Baco (SSE).
    Primeiro resolve todas as tools (sem streaming), depois faz streaming da resposta final."""
    if history is None:
        history = []

    messages = _build_messages(history, message)
    tools = TOOLS_PHOTO_MODE if photo_mode else TOOLS
    used_tools = False

    # Fase 1: Resolver tools em loop (sem streaming)
    for _ in range(MAX_TOOL_ROUNDS):
        if trace:
            trace.add_claude_round()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=BACO_SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason != "tool_use":
            if not used_tools:
                break
            for block in response.content:
                if hasattr(block, 'text'):
                    yield block.text
            return

        used_tools = True
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if trace:
                    trace.add_tool(block.name)
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    # Fase 2: Streaming (sem tools — forca resposta completa sem tool_use interrompido)
    if trace:
        trace.add_claude_round()
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


def _extract_text(response):
    """Extrai texto da resposta do Claude (ignora tool_use blocks)."""
    parts = []
    for block in response.content:
        if hasattr(block, 'text'):
            parts.append(block.text)
    return "".join(parts) if parts else ""
