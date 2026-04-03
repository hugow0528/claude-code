"""
Configuration for the Telegram Agentic Bot.
All settings are loaded from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # Telegram
    telegram_token: str = field(default_factory=lambda: os.environ["TELEGRAM_BOT_TOKEN"])

    # Pollinations API
    pollinations_base_url: str = "https://gen.pollinations.ai"
    pollinations_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("POLLINATIONS_API_KEY", "")
    )

    # Default AI model — non-paid models from apidocs.md
    # Options: deepseek, mistral, qwen-coder, glm, minimax, gemini-fast,
    #          nova-fast, kimi, perplexity-fast, claude-fast, openai, openai-fast
    default_model: str = field(
        default_factory=lambda: os.environ.get("DEFAULT_MODEL", "deepseek")
    )

    # Default image model — free image models
    # Options: flux, zimage, klein
    default_image_model: str = field(
        default_factory=lambda: os.environ.get("DEFAULT_IMAGE_MODEL", "flux")
    )

    # Maximum conversation turns to keep in history (per user)
    max_history_turns: int = field(
        default_factory=lambda: int(os.environ.get("MAX_HISTORY_TURNS", "20"))
    )

    # Maximum tool call iterations per agent turn
    max_agent_iterations: int = field(
        default_factory=lambda: int(os.environ.get("MAX_AGENT_ITERATIONS", "8"))
    )

    # Webhook settings (for production deployment)
    webhook_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("WEBHOOK_URL")
    )
    webhook_port: int = field(
        default_factory=lambda: int(os.environ.get("PORT", "8443"))
    )

    # Coding agent model — should be a code-specialised model
    # Options: qwen-coder, deepseek, openai, claude-fast
    coding_model: str = field(
        default_factory=lambda: os.environ.get("CODING_MODEL", "qwen-coder")
    )

    # GitHub integration — required for uploading generated code to GitHub
    # GITHUB_TOKEN: Personal Access Token with 'repo' (or 'public_repo') scope
    # GITHUB_REPO:  Target repository, e.g. "username/my-ai-projects"
    github_token: Optional[str] = field(
        default_factory=lambda: os.environ.get("GITHUB_TOKEN")
    )
    github_repo: Optional[str] = field(
        default_factory=lambda: os.environ.get("GITHUB_REPO")
    )

    # Optional: restrict bot to specific user IDs (comma-separated)
    allowed_user_ids: list[int] = field(default_factory=list)

    def __post_init__(self):
        raw = os.environ.get("ALLOWED_USER_IDS", "")
        if raw.strip():
            self.allowed_user_ids = [int(x.strip()) for x in raw.split(",") if x.strip()]


# Singleton
config = Config()
