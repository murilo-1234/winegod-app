import json

import anthropic
from openai import OpenAI

from config import Config
from prompts.baco_system import BACO_SYSTEM_PROMPT
from tools.schemas import TOOLS, TOOLS_PHOTO_MODE
from tools.executor import execute_tool

MODEL = Config.BACO_MODEL
PROVIDER = Config.BACO_PROVIDER
MAX_TOKENS = 2048
TEMPERATURE = 0.7
MAX_TOOL_ROUNDS = 5

_anthropic_client = None
_qwen_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        if not Config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY ausente")
        _anthropic_client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_qwen_client():
    global _qwen_client
    if _qwen_client is None:
        if not Config.DASHSCOPE_API_KEY:
            raise RuntimeError("DASHSCOPE_API_KEY ausente")
        _qwen_client = OpenAI(
            api_key=Config.DASHSCOPE_API_KEY,
            base_url=Config.DASHSCOPE_BASE_URL,
        )
    return _qwen_client


def get_baco_response(message, session_id, history=None, photo_mode=False, trace=None):
    """Envia mensagem para o provedor configurado e retorna resposta completa do Baco."""
    if PROVIDER == "anthropic":
        return _get_baco_response_anthropic(message, session_id, history, photo_mode, trace)
    if PROVIDER == "qwen":
        return _get_baco_response_openai_compatible(
            message, session_id, history, photo_mode, trace
        )
    raise RuntimeError(f"BACO_PROVIDER invalido: {PROVIDER}")


def stream_baco_response(message, session_id, history=None, photo_mode=False, trace=None):
    """Envia mensagem ao provedor configurado e retorna generator SSE com chunks do Baco."""
    if PROVIDER == "anthropic":
        yield from _stream_baco_response_anthropic(
            message, session_id, history, photo_mode, trace
        )
        return
    if PROVIDER == "qwen":
        yield from _stream_baco_response_openai_compatible(
            message, session_id, history, photo_mode, trace
        )
        return
    raise RuntimeError(f"BACO_PROVIDER invalido: {PROVIDER}")


def _get_baco_response_anthropic(message, session_id, history=None, photo_mode=False, trace=None):
    """Envia mensagem para Anthropic e processa tool_use em loop."""
    if history is None:
        history = []

    client = _get_anthropic_client()
    messages = _build_anthropic_messages(history, message)
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

        has_tool_use = any(b.type == "tool_use" for b in response.content)

        if response.stop_reason == "end_turn" and not has_tool_use:
            text = _extract_anthropic_text(response)
            return text, response.model

        if has_tool_use:
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
            text = _extract_anthropic_text(response)
            return text, response.model

    text = _extract_anthropic_text(response)
    return text, response.model


def _stream_baco_response_anthropic(message, session_id, history=None, photo_mode=False, trace=None):
    """Streaming Anthropic: resolve tools sem streaming, depois transmite resposta final."""
    if history is None:
        history = []

    client = _get_anthropic_client()
    messages = _build_anthropic_messages(history, message)
    tools = TOOLS_PHOTO_MODE if photo_mode else TOOLS
    used_tools = False

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

        has_tool_use = any(b.type == "tool_use" for b in response.content)

        if not has_tool_use:
            if not used_tools:
                break
            for block in response.content:
                if hasattr(block, "text"):
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


def _get_baco_response_openai_compatible(
    message, session_id, history=None, photo_mode=False, trace=None
):
    """Envia mensagem para Qwen/DashScope via API OpenAI-compatible."""
    if history is None:
        history = []

    client = _get_qwen_client()
    messages = _build_openai_messages(history, message)
    tools = _anthropic_tools_to_openai(TOOLS_PHOTO_MODE if photo_mode else TOOLS)

    for _ in range(MAX_TOOL_ROUNDS):
        if trace:
            trace.add_claude_round()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        choice = response.choices[0]
        msg = choice.message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            return msg.content or "", getattr(response, "model", MODEL)

        messages.append(_openai_assistant_tool_call_message(msg))
        for call in tool_calls:
            tool_name = call.function.name
            if trace:
                trace.add_tool(tool_name)
            tool_input = _parse_tool_arguments(call.function.arguments)
            result = execute_tool(tool_name, tool_input)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    return "", MODEL


def _stream_baco_response_openai_compatible(
    message, session_id, history=None, photo_mode=False, trace=None
):
    """Streaming Qwen: resolve tools sem streaming, depois transmite resposta final."""
    if history is None:
        history = []

    client = _get_qwen_client()
    messages = _build_openai_messages(history, message)
    tools = _anthropic_tools_to_openai(TOOLS_PHOTO_MODE if photo_mode else TOOLS)

    for _ in range(MAX_TOOL_ROUNDS):
        if trace:
            trace.add_claude_round()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []
        if not tool_calls:
            if msg.content:
                yield msg.content
            return

        messages.append(_openai_assistant_tool_call_message(msg))
        for call in tool_calls:
            tool_name = call.function.name
            if trace:
                trace.add_tool(tool_name)
            tool_input = _parse_tool_arguments(call.function.arguments)
            result = execute_tool(tool_name, tool_input)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    if trace:
        trace.add_claude_round()
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def _build_anthropic_messages(history, current_message):
    """Monta lista de mensagens para Anthropic."""
    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": current_message})
    return messages


def _build_openai_messages(history, current_message):
    """Monta lista de mensagens OpenAI-compatible."""
    messages = [{"role": "system", "content": BACO_SYSTEM_PROMPT}]
    for msg in history[-10:]:
        role = msg["role"]
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": current_message})
    return messages


def _anthropic_tools_to_openai(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            },
        }
        for tool in tools
    ]


def _openai_assistant_tool_call_message(msg):
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": call.type,
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
            for call in (msg.tool_calls or [])
        ],
    }


def _parse_tool_arguments(raw):
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return args if isinstance(args, dict) else {}


def _extract_anthropic_text(response):
    """Extrai texto da resposta Anthropic (ignora tool_use blocks)."""
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts) if parts else ""
