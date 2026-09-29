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

SYSTEM_PROMPT = """You are a film researcher who picks stock footage for a narrated video.
Read the WHOLE script first, then describe for every numbered scene what the camera
should literally show. Scenes share context: if the place, time of day or weather is
established earlier and not changed, carry it forward. Resolve pronouns to who they
refer to.

For each scene return (all values in ENGLISH, translate non-English scripts):
- subjects: 1-3 concrete, filmable nouns on screen (people described by type/age
  when relevant, e.g. "elderly vietnamese farmer", "young woman")
- actions: 0-2 visible actions as -ing verbs
- setting: 1-2 places (e.g. "office", "rice field", "city street")
- time_of_day: one of night, evening, sunset, sunrise, morning, day, or ""
- weather: one of rain, storm, snow, fog, wind, sunny, cloudy, or ""
- season: one of winter, spring, summer, autumn, or ""
- mood: 0-2 words (e.g. tense, calm, happy, lonely)
- visual_description: one sentence describing the ideal shot
- queries: 3-5 stock-video search queries of 2-5 words, ordered from most specific
  to most general. Stock sites match short tag-like queries best. Keep the key
  subject in most queries and put context (time/weather/place) in some. For abstract
  sentences ("success takes time") use a concrete visual metaphor.
  Example for "An engineer working late at night coding":
  ["programmer coding at night", "developer typing laptop dark office",
   "coding screen night", "person typing laptop"]
- avoid: 0-3 things that would contradict the scene (e.g. "daylight", "snow")
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
                    "setting": {"type": "array", "items": {"type": "string"}},
                    "time_of_day": {"type": "string"},
                    "weather": {"type": "string"},
                    "season": {"type": "string"},
                    "mood": {"type": "array", "items": {"type": "string"}},
                    "visual_description": {"type": "string"},
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "avoid": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "subjects", "actions", "setting", "time_of_day",
                             "weather", "season", "mood", "visual_description",
                             "queries", "avoid"],
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


def _parse_json_payload(text: str, key: str = "scenes") -> list[dict]:
    """Extract the list under `key` from a JSON (possibly fenced) text response."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("LLM response contains no JSON")
    data = json.loads(text[start:])
    if isinstance(data, dict):
        data = data.get(key, [])
    if not isinstance(data, list):
        raise ValueError(f"LLM JSON has no '{key}' list")
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
             + "\nRespond ONLY with JSON of the form "
               + json.dumps({"scenes": [{k: "..." for k in
                                         SCENE_SCHEMA["properties"]["scenes"]["items"]
                                         ["properties"]}]})},
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
