"""
LLM-backed visual concept extraction (with translation to English search terms).

Backends:
    - "openai":    any OpenAI-compatible endpoint (OpenAI, Ollama, DeepSeek, Qwen...)
                   via function calling, with a plain-JSON fallback for servers
                   that do not support tools.
    - "anthropic": Claude via the official `anthropic` SDK using structured
                   outputs (JSON schema).
"""

import json
import re

from loguru import logger

from .auth_manager import LLMSettings

SYSTEM_PROMPT = """You convert video narration scripts into stock-footage search terms.
For every numbered scene, return:
- subjects: 1-3 concrete visual nouns (who/what is on screen)
- actions: 0-2 visible actions, as English -ing verbs
- descriptors: 0-2 adjectives for environment, lighting or mood
- query: a 3-6 word ENGLISH stock-video search query describing what the camera
  would literally show. Translate non-English scripts (e.g. Vietnamese) to English.
  Prefer concrete, filmable nouns over abstract ideas
  ("An engineer working late at night coding" -> "developer typing code laptop night").
Return every scene index exactly once."""

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "subjects": {"type": "array", "items": {"type": "string"}},
                    "actions": {"type": "array", "items": {"type": "string"}},
                    "descriptors": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string"},
                },
                "required": ["index", "subjects", "actions", "descriptors", "query"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}


def _user_prompt(sentences: list[str]) -> str:
    lines = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, start=1))
    return f"Scenes:\n{lines}"


def _parse_json_payload(text: str) -> list[dict]:
    """Extract the scenes list from a JSON (possibly fenced) text response."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("LLM response contains no JSON")
    data = json.loads(text[start:])
    if isinstance(data, dict):
        data = data.get("scenes", [])
    if not isinstance(data, list):
        raise ValueError("LLM JSON has no 'scenes' list")
    return data


def _extract_openai(settings: LLMSettings, sentences: list[str]) -> list[dict]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key or "none", base_url=settings.base_url or None)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(sentences)},
    ]
    tool = {
        "type": "function",
        "function": {
            "name": "emit_scenes",
            "description": "Return the visual search concepts for each scene.",
            "parameters": SCENE_SCHEMA,
        },
    }
    try:
        resp = client.chat.completions.create(
            model=settings.model,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "emit_scenes"}},
            temperature=0.2,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            return json.loads(msg.tool_calls[0].function.arguments).get("scenes", [])
        if msg.content:
            return _parse_json_payload(msg.content)
    except Exception as e:
        logger.info(f"Function calling unavailable ({e}); retrying with plain JSON prompt")

    resp = client.chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT
             + '\nRespond ONLY with JSON: {"scenes": [{"index", "subjects", "actions", '
               '"descriptors", "query"}]}'},
            messages[1],
        ],
        temperature=0.2,
    )
    return _parse_json_payload(resp.choices[0].message.content or "")


def _extract_anthropic(settings: LLMSettings, sentences: list[str]) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.api_key) if settings.api_key \
        else anthropic.Anthropic()
    response = client.messages.create(
        model=settings.model or "claude-opus-5-5",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCENE_SCHEMA},
        },
        messages=[{"role": "user", "content": _user_prompt(sentences)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined the extraction request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude response truncated (max_tokens); split the script")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _parse_json_payload(text)


def extract_scenes(settings: LLMSettings, sentences: list[str]) -> list[dict]:
    """Return a list of scene dicts: index, subjects, actions, descriptors, query."""
    if settings.backend == "anthropic":
        return _extract_anthropic(settings, sentences)
    return _extract_openai(settings, sentences)
