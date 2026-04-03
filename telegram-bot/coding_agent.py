"""
Coding Agent — generates complete, working software projects.

Inspired by Claude Code's "Doing Tasks" system prompt philosophy
(src/constants/prompts.ts) and the DEFAULT_AGENT_PROMPT directive.

The agent:
  1. Receives a task description from the user
  2. Calls a code-specialised AI model (qwen-coder by default)
  3. Returns a structured result: project name, description, and ALL files

The AI is instructed to produce only valid JSON — no prose, no markdown fences.
The JSON is parsed and returned as a CodingResult for the caller to process.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any

import httpx

from config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProjectFile:
    path: str
    content: str


@dataclass
class CodingResult:
    project_name: str
    description: str
    tech_stack: list[str]
    files: list[ProjectFile]
    run_instructions: str
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.files)


StatusCallback = Callable[[str], Awaitable[None]]

# ---------------------------------------------------------------------------
# Coding agent system prompt
# Heavily inspired by Claude Code's src/constants/prompts.ts "Doing Tasks" section
# and the DEFAULT_AGENT_PROMPT.
# ---------------------------------------------------------------------------

CODING_SYSTEM_PROMPT = """You are an expert software engineer acting as a coding agent. \
Your job is to generate complete, working software projects from a task description.

## Core Principles

**Complete the task fully.** Don't leave code half-done, don't add TODO placeholders \
without implementing them, don't stop short of a working solution. \
When you complete a task, respond with ALL the code needed — the caller relies on you \
delivering a runnable project.

**Scope to the request.** Don't add features, refactor patterns, or "improve" \
things beyond what was asked. Build exactly what was requested — no more, no less. \
A simple CLI tool doesn't need a plugin system. A REST API doesn't need a full \
microservices architecture unless asked.

**Write real, runnable code.** Every import must exist. Every function must be \
implemented. Every variable must be defined before use. \
Mentally trace through the execution path before outputting. \
Never use placeholder text like "# TODO: implement this" unless it is a genuine \
user-facing extension point.

**Don't fabricate.** Never invent library names, API endpoints, or configuration keys. \
If you're unsure whether something exists, use what you know to be real and widely-used. \
Prefer standard-library solutions over invented third-party packages.

**Include everything needed to run.** Dependencies file, main entry point, \
configuration example. A project must be runnable with minimal setup steps.

## File Creation Rules

- Always include a README.md: what it does, prerequisites, installation, usage
- Always include the dependency file for the language:
    Python → requirements.txt
    Node.js → package.json
    Go → go.mod
    Rust → Cargo.toml
    Ruby → Gemfile
    Java/Kotlin → pom.xml or build.gradle
- Create the minimum number of files that makes the project work cleanly
- Don't create test files unless the user explicitly asked for tests
- Use conventional project structure for the technology stack

## Code Style Rules (from Claude Code)

- Write idiomatic code for the language and framework
- Comments only when the WHY is non-obvious — well-named code explains WHAT
- Clear, descriptive names for functions, variables, and classes
- Handle errors appropriately for the application type
- No dead code, no commented-out code blocks
- No defensive logging or error handling for scenarios that literally cannot happen

## Output Format

You MUST respond ONLY with a valid JSON object.
Do NOT wrap it in markdown code fences.
Do NOT add any explanation before or after the JSON.

Required schema:
{
  "project_name": "kebab-case-name",
  "description": "One sentence: what this project does",
  "tech_stack": ["Primary Language", "Framework", "Key libraries"],
  "files": [
    {
      "path": "path/relative/to/project/root.ext",
      "content": "complete, untruncated file content"
    }
  ],
  "run_instructions": "Concrete commands to install and run (e.g. pip install -r requirements.txt && python app.py)"
}

Constraints:
- project_name: lowercase, hyphens only (no underscores, no spaces), 2–5 words
- files[].path: relative to project root, forward slashes, no leading slash
- files[].content: complete and untruncated — NEVER use "..." or "# rest of implementation"
- run_instructions: concrete commands, not vague prose
- Every file listed must be complete and ready to use without modification"""


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


async def run_coding_agent(
    task: str,
    status_callback: StatusCallback | None = None,
) -> CodingResult:
    """
    Generate a complete software project for the given task description.

    Returns a CodingResult. Check `.ok` before using `.files`.
    """
    model = config.coding_model

    if status_callback:
        await status_callback(f"⚙️ Generating project with `{model}`…")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": CODING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate a complete, working software project for this task:\n\n{task}\n\n"
                    "Remember: respond ONLY with the JSON object, no markdown fences, "
                    "no explanation — just the JSON."
                ),
            },
        ],
        "temperature": 0.3,   # lower = more deterministic, better for code
        "seed": 42,
        "response_format": {"type": "json_object"},
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "TelegramAgentBot/1.0",
    }
    if config.pollinations_api_key:
        headers["Authorization"] = f"Bearer {config.pollinations_api_key}"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{config.pollinations_base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            return CodingResult(
                project_name="",
                description="",
                tech_stack=[],
                files=[],
                run_instructions="",
                error=f"Model returned HTTP {resp.status_code}: {resp.text[:300]}",
            )

        raw_content: str = resp.json()["choices"][0]["message"]["content"]
        return _parse_coding_response(raw_content)

    except httpx.TimeoutException:
        return CodingResult(
            project_name="",
            description="",
            tech_stack=[],
            files=[],
            run_instructions="",
            error="Request timed out. The project may be too large — try a simpler request.",
        )
    except Exception as exc:
        logger.exception("Unexpected error in coding agent")
        return CodingResult(
            project_name="",
            description="",
            tech_stack=[],
            files=[],
            run_instructions="",
            error=f"Unexpected error: {exc}",
        )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_coding_response(raw: str) -> CodingResult:
    """
    Parse the model's JSON response into a CodingResult.

    Handles edge cases:
    - JSON wrapped in markdown code fences
    - Extra prose before/after the JSON object
    """
    # Strip markdown code fences if the model ignored instructions
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Extract the first top-level JSON object if there's prose around it
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    try:
        data: dict = json.loads(text)
    except json.JSONDecodeError as exc:
        return CodingResult(
            project_name="",
            description="",
            tech_stack=[],
            files=[],
            run_instructions="",
            error=f"Model returned invalid JSON: {exc}. Raw (first 200 chars): {raw[:200]}",
        )

    # Validate and normalise required fields
    project_name = _slugify(data.get("project_name", "generated-project"))
    description = str(data.get("description", "AI-generated project"))
    tech_stack = data.get("tech_stack", [])
    if not isinstance(tech_stack, list):
        tech_stack = []
    run_instructions = str(data.get("run_instructions", ""))

    raw_files = data.get("files", [])
    if not isinstance(raw_files, list) or not raw_files:
        return CodingResult(
            project_name=project_name,
            description=description,
            tech_stack=tech_stack,
            files=[],
            run_instructions=run_instructions,
            error="Model did not return any files. Try rephrasing your request.",
        )

    files: list[ProjectFile] = []
    for f in raw_files:
        if not isinstance(f, dict):
            continue
        path = str(f.get("path", "")).lstrip("/")
        content = str(f.get("content", ""))
        if path and content:
            files.append(ProjectFile(path=path, content=content))

    if not files:
        return CodingResult(
            project_name=project_name,
            description=description,
            tech_stack=tech_stack,
            files=[],
            run_instructions=run_instructions,
            error="All files had empty paths or content.",
        )

    return CodingResult(
        project_name=project_name,
        description=description,
        tech_stack=tech_stack,
        files=files,
        run_instructions=run_instructions,
    )


def _slugify(name: str) -> str:
    """Convert any string to a safe kebab-case project name."""
    name = name.lower().strip()
    name = re.sub(r"[\s_]+", "-", name)      # spaces and underscores → hyphens first
    name = re.sub(r"[^a-z0-9-]", "", name)  # strip remaining special chars
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "generated-project"
