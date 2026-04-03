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

import ast
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
    {
        "type": "function",
        "function": {
            "name": "write_code_project",
            "description": (
                "Generate a complete, working software project and upload it to GitHub. "
                "Use this when the user asks to: write/create/build/code a program, app, "
                "script, API, website, bot, tool, or any software project. "
                "The agent will generate ALL files needed (code, dependencies, README) "
                "and commit them to GitHub as a single atomic upload. "
                "Returns the GitHub URL where the code can be viewed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Full description of the software project to build. "
                            "Include: what it should do, the language/framework if specified, "
                            "any specific features or requirements."
                        ),
                    },
                },
                "required": ["task"],
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


_ALLOWED_CALC_NAMES: dict[str, Any] = {
    name: getattr(math, name)
    for name in (
        "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "log", "log2", "log10", "exp", "pow", "floor", "ceil", "factorial",
        "gcd", "pi", "e", "tau", "inf",
    )
}
_ALLOWED_CALC_NAMES.update({"abs": abs, "round": round, "min": min, "max": max})

# Operators allowed in the AST-based evaluator
_BINOP_MAP = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
    ast.FloorDiv: lambda a, b: a // b,
}
_UNARYOP_MAP = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
}


def _eval_node(node: ast.AST) -> float | int:
    """Recursively evaluate a safe subset of Python AST nodes."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_CALC_NAMES:
            raise ValueError(f"Name '{node.id}' is not allowed")
        return _ALLOWED_CALC_NAMES[node.id]
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BINOP_MAP:
            raise ValueError(f"Binary operator {op_type.__name__} is not allowed")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _BINOP_MAP[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARYOP_MAP:
            raise ValueError(f"Unary operator {op_type.__name__} is not allowed")
        return _UNARYOP_MAP[op_type](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only named function calls are allowed")
        func_name = node.func.id
        if func_name not in _ALLOWED_CALC_NAMES:
            raise ValueError(f"Function '{func_name}' is not allowed")
        func = _ALLOWED_CALC_NAMES[func_name]
        args = [_eval_node(arg) for arg in node.args]
        return func(*args)
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def tool_calculate(expression: str) -> dict[str, Any]:
    """Safely evaluate a math expression using AST parsing (no eval)."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree)
        return {"result": result, "expression": expression}
    except Exception as exc:
        return {"error": str(exc), "expression": expression}


# ---------------------------------------------------------------------------
# Dispatcher — called by the agent loop
# ---------------------------------------------------------------------------

async def tool_write_code_project(task: str) -> dict[str, Any]:
    """
    Full coding agent pipeline:
      1. Generate a complete project via the coding agent (AI call)
      2. Upload to GitHub if configured, otherwise return files inline

    Called by the agentic loop via dispatch_tool().
    The bot.py /code command calls the coding_agent and github_upload modules
    directly for better UX (status updates), but this function lets the
    general agentic loop trigger coding too.
    """
    # Import here to avoid circular imports at module load time
    from coding_agent import run_coding_agent
    from github_upload import upload_project_to_github

    coding_result = await run_coding_agent(task)
    if not coding_result.ok:
        return {"error": coding_result.error}

    files_for_upload = [
        {"path": f.path, "content": f.content}
        for f in coding_result.files
    ]

    if config.github_token and config.github_repo:
        upload_result = await upload_project_to_github(
            project_name=coding_result.project_name,
            files=files_for_upload,
            description=coding_result.description,
        )
        if "error" in upload_result:
            # GitHub upload failed — return code summary without URL
            return {
                "project_name": coding_result.project_name,
                "description": coding_result.description,
                "tech_stack": coding_result.tech_stack,
                "files_count": len(coding_result.files),
                "file_list": [f.path for f in coding_result.files],
                "run_instructions": coding_result.run_instructions,
                "github_upload_error": upload_result["error"],
            }
        return {
            "project_name": coding_result.project_name,
            "description": coding_result.description,
            "tech_stack": coding_result.tech_stack,
            "files_count": len(coding_result.files),
            "file_list": [f.path for f in coding_result.files],
            "run_instructions": coding_result.run_instructions,
            "github_url": upload_result["github_url"],
            "commit_sha": upload_result.get("commit_sha", ""),
        }
    else:
        # No GitHub configured — return project info so the agent can describe it
        return {
            "project_name": coding_result.project_name,
            "description": coding_result.description,
            "tech_stack": coding_result.tech_stack,
            "files_count": len(coding_result.files),
            "file_list": [f.path for f in coding_result.files],
            "run_instructions": coding_result.run_instructions,
            "note": (
                "GitHub upload is not configured (GITHUB_TOKEN / GITHUB_REPO missing). "
                "The code was generated but not uploaded. "
                "Tell the user to configure GitHub or use the /code command to receive files directly."
            ),
        }


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
    elif name == "write_code_project":
        result = await tool_write_code_project(**args)
    else:
        result = {"error": f"Unknown tool: {name}"}

    # audio_bytes is not JSON-serialisable; replace with a placeholder
    if "audio_bytes" in result and isinstance(result.get("audio_bytes"), bytes):
        audio_data = result.pop("audio_bytes")
        result["_audio_bytes_length"] = len(audio_data)
        result["_audio_bytes"] = audio_data  # kept for caller inspection

    return json.dumps(result, ensure_ascii=False, default=str)
