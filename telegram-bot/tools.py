"""
Tool definitions and implementations for the agentic bot.

Each tool is registered with a JSON Schema so the AI model can call it
via the OpenAI-compatible function-calling API served by Pollinations.

Available tools
---------------
- generate_image   : text-to-image via Pollinations /image/{prompt}
- web_search       : web search using a search-capable model
- text_to_speech   : TTS via Pollinations /audio/{text}
- get_current_time : return the current UTC datetime (no API call)
- calculate        : safe numeric expression evaluator
"""

from __future__ import annotations

import json
import math
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

from config import config

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generate an image from a text prompt using Pollinations AI. "
                "Returns a public URL of the generated image. "
                "Use this whenever the user asks to create, draw, or visualize something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the image to generate.",
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "Image model to use. Options: flux (default, fast & high-quality), "
                            "zimage (fast with upscaling), klein (fast editing). "
                            "Omit to use the default."
                        ),
                        "enum": ["flux", "zimage", "klein"],
                    },
                    "width": {
                        "type": "integer",
                        "description": "Image width in pixels (default 1024).",
                    },
                    "height": {
                        "type": "integer",
                        "description": "Image height in pixels (default 1024).",
                    },
                    "enhance": {
                        "type": "boolean",
                        "description": "Enhance the prompt with AI (default false).",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. "
                "Use this for: recent news, facts you are unsure about, "
                "current events, prices, weather, and any time-sensitive queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Approximate number of results to return (1-10, default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "text_to_speech",
            "description": (
                "Convert text to speech audio and send as a voice message. "
                "Use when the user asks to 'say', 'read aloud', or 'speak' something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to convert to speech (max ~500 chars for best quality).",
                    },
                    "voice": {
                        "type": "string",
                        "description": (
                            "Voice to use. Options: alloy, echo, fable, onyx, nova, shimmer, "
                            "ash, coral, sage, rachel, sarah, emily. Default: nova."
                        ),
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Return the current UTC date and time. Use for time/date questions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression safely. "
                "Supports: +, -, *, /, **, %, sqrt, sin, cos, tan, log, abs, round, pi, e. "
                "Use this instead of doing math in your head."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate, e.g. '2 ** 10' or 'sqrt(144)'.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _pollinations_headers() -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": "TelegramAgentBot/1.0"}
    if config.pollinations_api_key:
        headers["Authorization"] = f"Bearer {config.pollinations_api_key}"
    return headers


async def tool_generate_image(
    prompt: str,
    model: str | None = None,
    width: int = 1024,
    height: int = 1024,
    enhance: bool = False,
) -> dict[str, Any]:
    """Generate an image and return its public URL."""
    image_model = model or config.default_image_model
    encoded = urllib.parse.quote(prompt, safe="")
    params: dict[str, Any] = {
        "model": image_model,
        "width": width,
        "height": height,
        "enhance": str(enhance).lower(),
        "nologo": "true",
        "seed": -1,  # random each time
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{config.pollinations_base_url}/image/{encoded}?{qs}"

    # Verify the URL resolves (HEAD request) — Pollinations serves images directly
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.head(url, headers=_pollinations_headers())
        if resp.status_code >= 400:
            return {"error": f"Image generation failed (HTTP {resp.status_code})"}

    return {"image_url": url, "prompt": prompt, "model": image_model}


async def tool_web_search(query: str, num_results: int = 5) -> dict[str, Any]:
    """
    Use a search-enabled Pollinations model to search the web.
    We use 'gemini-search' (free, has Google Search grounding).
    """
    search_prompt = (
        f"Search the web and answer this query concisely with key facts and sources: {query}\n"
        f"Return up to {num_results} relevant points with source URLs where available."
    )
    payload = {
        "model": "gemini-search",
        "messages": [{"role": "user", "content": search_prompt}],
        "temperature": 0.3,
        "seed": -1,
    }
    headers = {**_pollinations_headers(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            f"{config.pollinations_base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
    if resp.status_code != 200:
        return {"error": f"Search failed (HTTP {resp.status_code}): {resp.text[:200]}"}
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return {"results": content, "query": query}


async def tool_text_to_speech(text: str, voice: str = "nova") -> dict[str, Any]:
    """Convert text to speech, return the audio bytes."""
    encoded = urllib.parse.quote(text[:500], safe="")
    url = f"{config.pollinations_base_url}/audio/{encoded}?voice={voice}&model=elevenlabs"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url, headers=_pollinations_headers())
    if resp.status_code != 200:
        return {"error": f"TTS failed (HTTP {resp.status_code})"}
    return {"audio_bytes": resp.content, "voice": voice, "text": text}


def tool_get_current_time() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "utc_time": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "iso": now.isoformat(),
    }


def tool_calculate(expression: str) -> dict[str, Any]:
    """Safely evaluate a math expression."""
    allowed_names = {
        k: v
        for k, v in math.__dict__.items()
        if not k.startswith("_")
    }
    allowed_names.update({"abs": abs, "round": round})
    try:
        # Only allow names from math + literals; no builtins beyond what we list
        result = eval(  # noqa: S307
            expression,
            {"__builtins__": {}},
            allowed_names,
        )
        return {"result": result, "expression": expression}
    except Exception as exc:
        return {"error": str(exc), "expression": expression}


# ---------------------------------------------------------------------------
# Dispatcher — called by the agent loop
# ---------------------------------------------------------------------------

async def dispatch_tool(name: str, arguments: str | dict) -> str:
    """
    Execute a tool by name and return its result as a JSON string.

    Returns a dict with either a result payload or {"error": "..."}.
    The return value is always JSON-serialisable.
    """
    if isinstance(arguments, str):
        try:
            args: dict = json.loads(arguments)
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments: {arguments}"})
    else:
        args = arguments

    if name == "generate_image":
        result = await tool_generate_image(**args)
    elif name == "web_search":
        result = await tool_web_search(**args)
    elif name == "text_to_speech":
        result = await tool_text_to_speech(**args)
    elif name == "get_current_time":
        result = tool_get_current_time()
    elif name == "calculate":
        result = tool_calculate(**args)
    else:
        result = {"error": f"Unknown tool: {name}"}

    # audio_bytes is not JSON-serialisable; replace with a placeholder
    if "audio_bytes" in result and isinstance(result.get("audio_bytes"), bytes):
        audio_data = result.pop("audio_bytes")
        result["_audio_bytes_length"] = len(audio_data)
        result["_audio_bytes"] = audio_data  # kept for caller inspection

    return json.dumps(result, ensure_ascii=False, default=str)
