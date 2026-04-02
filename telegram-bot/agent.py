"""
Agentic loop — inspired by Claude Code's coordinator / agent patterns.

The agent runs an OpenAI-compatible tool-calling loop:
  1. Send system prompt + conversation history to the model.
  2. If the model returns tool_calls, execute them and append results.
  3. Repeat until the model returns a plain text response (no tool_calls)
     or we hit the max-iteration limit.

Stream-style "thinking" updates are sent to the user via `status_callback`
so the chat feels responsive while the agent works.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Awaitable
from typing import Any

import httpx

from config import config
from tools import TOOLS, dispatch_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — combines patterns from src/constants/prompts.ts and
# src/coordinator/coordinatorMode.ts in the repo.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful, capable AI assistant living inside Telegram.

## Your Capabilities

You have access to the following tools:
- **generate_image** – Create images from text descriptions
- **web_search** – Search the web for current information  
- **text_to_speech** – Convert text to spoken audio
- **get_current_time** – Get the current UTC date and time
- **calculate** – Evaluate mathematical expressions safely

## How to Behave

- Be concise and direct. Telegram messages look best when they are not too long.
- Use tools proactively: if a question needs current info, search; if asked to draw something, generate an image.
- Before reporting done, verify your work. If a tool returns an error, try to handle it gracefully.
- Use Markdown formatting (bold, italic, code blocks) — Telegram renders it.
- Never hallucinate URLs or facts. If unsure, search or say so.
- When you generate an image, the bot will send it automatically — just tell the user what you created.
- When you generate audio, the bot will send it as a voice message — just confirm what was spoken.

## Style Rules (from the codebase that runs me)
- Complete tasks fully — don't gold-plate, but don't leave things half-done.
- Report outcomes faithfully. If something failed, say so clearly.
- Don't add disclaimers after successful completions — just state what was done.
"""


# ---------------------------------------------------------------------------
# Simple in-memory conversation history store
# ---------------------------------------------------------------------------

class ConversationHistory:
    """Per-user message history with automatic trimming.

    `max_user_turns` is the number of user-assistant turn *pairs* to retain.
    Internally we allow up to `max_user_turns * 4` raw messages to account
    for tool call / tool result messages that sit between turns.
    """

    def __init__(self, max_user_turns: int = 20):
        self._max_user_turns = max_user_turns
        self._store: dict[int, list[dict]] = {}

    def get(self, user_id: int) -> list[dict]:
        return list(self._store.get(user_id, []))

    def append(self, user_id: int, message: dict) -> None:
        history = self._store.setdefault(user_id, [])
        history.append(message)
        # Each turn = user msg + assistant msg + tool calls/results (~4 messages)
        max_messages = self._max_user_turns * 4
        if len(history) > max_messages:
            self._store[user_id] = history[-max_messages:]

    def clear(self, user_id: int) -> None:
        self._store.pop(user_id, None)

    def set_model(self, user_id: int, model: str) -> None:
        self._store.setdefault(user_id, [])
        # Store model preference as metadata (not sent to API)
        if not hasattr(self, "_models"):
            self._models: dict[int, str] = {}
        self._models[user_id] = model

    def get_model(self, user_id: int) -> str:
        if not hasattr(self, "_models"):
            self._models = {}
        return self._models.get(user_id, config.default_model)


history = ConversationHistory(max_user_turns=config.max_history_turns)


# ---------------------------------------------------------------------------
# Core agent function
# ---------------------------------------------------------------------------

StatusCallback = Callable[[str], Awaitable[None]]


async def run_agent(
    user_id: int,
    user_message: str,
    status_callback: StatusCallback | None = None,
) -> "AgentResult":
    """
    Run the agentic loop for a single user turn.

    Returns an AgentResult containing:
    - text: final assistant text response
    - images: list of image URLs generated during the turn
    - audio: list of audio byte strings generated during the turn
    - model_used: the model that was used
    """
    model = history.get_model(user_id)

    # Build messages
    messages: list[dict] = history.get(user_id)
    messages.append({"role": "user", "content": user_message})

    # Track side-effects
    generated_images: list[str] = []
    generated_audio: list[bytes] = []

    iterations = 0
    final_text = ""

    while iterations < config.max_agent_iterations:
        iterations += 1

        if status_callback and iterations > 1:
            await status_callback(f"🤔 Thinking… (step {iterations})")

        response_msg = await _call_model(model, messages)

        tool_calls = response_msg.get("tool_calls") or []

        if not tool_calls:
            # Final text response
            final_text = response_msg.get("content") or ""
            # Append assistant message to history
            history.append(user_id, {"role": "user", "content": user_message})
            history.append(user_id, {"role": "assistant", "content": final_text})
            break

        # Append assistant's tool-call message
        messages.append({"role": "assistant", **response_msg})

        # Execute all tool calls (sequentially for simplicity)
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_args = tc["function"].get("arguments", "{}")
            tool_call_id = tc.get("id", f"call_{tool_name}_{iterations}")

            if status_callback:
                await status_callback(f"🔧 Using tool: `{tool_name}`…")

            result_json = await dispatch_tool(tool_name, tool_args)
            result_dict: dict = json.loads(result_json)

            # Collect side-effects
            if tool_name == "generate_image" and "image_url" in result_dict:
                generated_images.append(result_dict["image_url"])

            if tool_name == "text_to_speech" and "_audio_bytes" in result_dict:
                generated_audio.append(result_dict.pop("_audio_bytes"))
                # Clean up non-serialisable key that was already extracted
                result_dict.pop("_audio_bytes_length", None)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result_dict, ensure_ascii=False, default=str),
                }
            )
    else:
        # Max iterations reached
        final_text = (
            "⚠️ I reached the maximum number of steps for this task. "
            "Here is what I have so far — please ask me to continue if needed."
        )
        history.append(user_id, {"role": "user", "content": user_message})
        history.append(user_id, {"role": "assistant", "content": final_text})

    return AgentResult(
        text=final_text,
        images=generated_images,
        audio=generated_audio,
        model_used=model,
        iterations=iterations,
    )


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

async def _call_model(model: str, messages: list[dict]) -> dict[str, Any]:
    """
    Call the Pollinations OpenAI-compatible API and return the assistant message dict.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "TelegramAgentBot/1.0",
    }
    if config.pollinations_api_key:
        headers["Authorization"] = f"Bearer {config.pollinations_api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *messages,
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "seed": -1,
    }

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{config.pollinations_base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            logger.error("API error %d: %s", resp.status_code, resp.text[:500])
            return {
                "content": (
                    f"⚠️ The AI model returned an error (HTTP {resp.status_code}). "
                    "Please try again or switch models with /model."
                )
            }

        data = resp.json()
        return data["choices"][0]["message"]

    except httpx.TimeoutException:
        return {"content": "⚠️ The request timed out. Please try again."}
    except Exception as exc:
        logger.exception("Unexpected error calling model")
        return {"content": f"⚠️ An unexpected error occurred: {exc}"}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class AgentResult:
    def __init__(
        self,
        text: str,
        images: list[str],
        audio: list[bytes],
        model_used: str,
        iterations: int,
    ):
        self.text = text
        self.images = images
        self.audio = audio
        self.model_used = model_used
        self.iterations = iterations
