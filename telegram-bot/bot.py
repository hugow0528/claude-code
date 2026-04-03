"""
Main Telegram Bot — entry point.

Supports both polling (local dev) and webhook (production/Railway).

Commands
--------
/start          – Welcome message
/help           – Show all commands and capabilities
/clear          – Clear conversation history
/model [name]   – Show or switch the AI model
/image <prompt> – Generate an image directly (shortcut)
/imagine <prompt>– Alias for /image
/say <text>     – Convert text to speech (shortcut)
/models         – List all available non-paid models

Any other message triggers the agentic loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from typing import Any

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent import history, run_agent
from coding_agent import run_coding_agent
from config import config
from github_upload import upload_project_to_github
from tools import (
    tool_generate_image,
    tool_text_to_speech,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Non-paid text models — sourced from apidocs.md
# ---------------------------------------------------------------------------

FREE_MODELS: dict[str, str] = {
    "deepseek": "DeepSeek V3.2 — Efficient Reasoning & Agentic AI [tools]",
    "mistral": "Mistral Small 3.2 24B — Efficient & Cost-Effective [tools]",
    "qwen-coder": "Qwen3 Coder 30B — Great for Code [tools]",
    "glm": "Z.ai GLM-5 744B MoE — Long Context Reasoning [tools]",
    "minimax": "MiniMax M2.5 — Coding, Agentic & Multi-Language [tools]",
    "gemini-fast": "Gemini 2.5 Flash Lite — Ultra Fast [tools, search]",
    "nova-fast": "Amazon Nova Micro — Ultra Fast & Cheap [tools]",
    "kimi": "Moonshot Kimi K2.5 — Flagship Agentic [tools, reasoning]",
    "openai": "GPT-5 Mini — Fast & Balanced [tools]",
    "openai-fast": "GPT-5 Nano — Ultra Fast [tools]",
    "claude-fast": "Claude Haiku 4.5 — Fast & Intelligent [tools]",
    "perplexity-fast": "Perplexity Sonar — Web Search [search]",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_allowed(user_id: int) -> bool:
    if not config.allowed_user_ids:
        return True
    return user_id in config.allowed_user_ids


async def _send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )


def _escape_md(text: str) -> str:
    """Escape characters that have special meaning in MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


async def _safe_reply(update: Update, text: str, **kwargs) -> None:
    """Send a message, falling back to plain text if Markdown parsing fails."""
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except Exception:
        await update.message.reply_text(text, **kwargs)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorised to use this bot.")
        return

    model = history.get_model(update.effective_user.id)
    text = (
        "👋 *Welcome to the Agentic AI Bot!*\n\n"
        "I'm powered by [Pollinations AI](https://pollinations.ai) and can:\n\n"
        "🖼 *Generate images* — just ask or use /image\n"
        "🔍 *Search the web* — for current information\n"
        "🔊 *Speak text aloud* — use /say or ask me to read something\n"
        "🧮 *Do calculations* — just type a maths problem\n"
        "💻 *Write & deploy code* — use /code to generate a project & upload to GitHub\n"
        "💬 *Chat naturally* — with memory across this conversation\n\n"
        f"Current model: `{model}`\n"
        "Use /help to see all commands.\n"
        "Use /model to switch AI models."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *Commands*\n\n"
        "/start — Welcome message\n"
        "/help — This help message\n"
        "/clear — Clear conversation history\n"
        "/model `[name]` — Show or switch AI model\n"
        "/models — List all available models\n"
        "/image `<prompt>` — Generate an image\n"
        "/imagine `<prompt>` — Same as /image\n"
        "/say `<text>` — Convert text to speech\n"
        "/code `<description>` — Generate a project & upload to GitHub\n\n"
        "💡 *Tips*\n"
        "• Just chat naturally — I'll use tools when needed\n"
        "• Ask me to draw, search, calculate, or speak anything\n"
        "• Ask me to *write/build/create* code — I'll use the coding agent\n"
        "• I remember context within your conversation\n"
        "• Use /clear to start a fresh conversation\n\n"
        "🤖 *Powered by* [Pollinations AI](https://pollinations.ai)"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    history.clear(update.effective_user.id)
    await update.message.reply_text(
        "🗑 Conversation history cleared. Starting fresh!"
    )


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = history.get_model(update.effective_user.id)
    lines = ["🤖 *Available models (non-paid)*\n"]
    for name, desc in FREE_MODELS.items():
        marker = "✅ " if name == current else "  "
        lines.append(f"{marker}`{name}` — {desc}")
    lines.append("\nUse `/model <name>` to switch.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return

    args = context.args
    user_id = update.effective_user.id

    if not args:
        # Show current model with inline keyboard to switch
        current = history.get_model(user_id)
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"model:{name}")]
            for name in list(FREE_MODELS.keys())[:6]  # show top 6
        ]
        keyboard.append(
            [InlineKeyboardButton("See all /models", callback_data="model:list")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Current model: `{current}`\n\nChoose a model:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
        return

    model_name = args[0].lower()
    if model_name not in FREE_MODELS:
        await update.message.reply_text(
            f"❌ Unknown model `{model_name}`. Use /models to see available options.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    history.set_model(user_id, model_name)
    desc = FREE_MODELS[model_name]
    await update.message.reply_text(
        f"✅ Switched to `{model_name}`\n_{desc}_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def callback_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard model selection."""
    query = update.callback_query
    await query.answer()

    data: str = query.data
    if data == "model:list":
        await query.edit_message_text(
            "Use /models to see all available models.",
        )
        return

    model_name = data.removeprefix("model:")
    if model_name not in FREE_MODELS:
        await query.edit_message_text(f"❌ Unknown model: {model_name}")
        return

    history.set_model(update.effective_user.id, model_name)
    desc = FREE_MODELS[model_name]
    await query.edit_message_text(
        f"✅ Switched to `{model_name}`\n_{desc}_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Direct image generation shortcut."""
    if not _is_allowed(update.effective_user.id):
        return

    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text(
            "🖼 Usage: `/image <description>`\n\nExample: `/image a sunset over Tokyo`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO
    )
    status_msg = await update.message.reply_text("🎨 Generating image…")

    result = await tool_generate_image(prompt)
    await status_msg.delete()

    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return

    await update.message.reply_photo(
        photo=result["image_url"],
        caption=f"🖼 _{prompt}_\nModel: `{result['model']}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Direct TTS shortcut."""
    if not _is_allowed(update.effective_user.id):
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "🔊 Usage: `/say <text>`\n\nExample: `/say Hello from your AI assistant!`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE
    )
    status_msg = await update.message.reply_text("🔊 Generating audio…")

    result = await tool_text_to_speech(text)
    await status_msg.delete()

    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return

    audio_bytes: bytes = result["_audio_bytes"]
    await update.message.reply_voice(
        voice=InputFile(BytesIO(audio_bytes), filename="speech.mp3"),
        caption=f"🔊 _{text[:100]}{'…' if len(text) > 100 else ''}_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Coding agent — generates a complete software project and uploads to GitHub.

    Usage: /code <description of what to build>

    Workflow:
      1. Run the coding agent (AI generates all project files)
      2a. If GITHUB_TOKEN + GITHUB_REPO configured: upload to GitHub, return URL
      2b. Otherwise: send each generated file as a Telegram document attachment
    """
    if not _is_allowed(update.effective_user.id):
        return

    task = " ".join(context.args) if context.args else ""
    if not task:
        github_status = (
            "✅ GitHub upload configured"
            if (config.github_token and config.github_repo)
            else "⚠️ GitHub not configured (files will be sent here)"
        )
        await update.message.reply_text(
            "💻 *Coding Agent*\n\n"
            "Usage: `/code <description of what to build>`\n\n"
            "*Examples:*\n"
            "• `/code a Python Flask REST API for a todo list with SQLite`\n"
            "• `/code a Node.js CLI tool that converts CSV to JSON`\n"
            "• `/code a Telegram bot in Python that tells jokes`\n"
            "• `/code a Go HTTP server that serves static files`\n\n"
            f"GitHub: {github_status}\n\n"
            f"Coding model: `{config.coding_model}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    status_msg = await update.message.reply_text("🤖 Analyzing your request…")

    async def update_status(text: str) -> None:
        try:
            await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

    # Step 1: Generate the project
    await update_status(f"⚙️ Generating project with `{config.coding_model}`…\n_(this may take 30–60 seconds)_")
    coding_result = await run_coding_agent(task, status_callback=update_status)

    if not coding_result.ok:
        await status_msg.delete()
        await update.message.reply_text(
            f"❌ *Code generation failed*\n\n{coding_result.error}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    files_summary = "\n".join(
        f"• `{f.path}`" for f in coding_result.files
    )
    tech = ", ".join(coding_result.tech_stack) if coding_result.tech_stack else "N/A"

    # Step 2a: Upload to GitHub if configured
    if config.github_token and config.github_repo:
        await update_status(
            f"📁 *{coding_result.project_name}* — {len(coding_result.files)} files generated\n"
            f"📤 Uploading to GitHub…"
        )

        files_for_upload = [
            {"path": f.path, "content": f.content}
            for f in coding_result.files
        ]
        upload_result = await upload_project_to_github(
            project_name=coding_result.project_name,
            files=files_for_upload,
            description=coding_result.description,
        )
        await status_msg.delete()

        if "error" in upload_result:
            await update.message.reply_text(
                f"⚠️ *Project generated but GitHub upload failed*\n\n"
                f"Error: {upload_result['error']}\n\n"
                f"Sending files directly instead…",
                parse_mode=ParseMode.MARKDOWN,
            )
            await _send_files_as_documents(update, context, coding_result)
        else:
            github_url = upload_result["github_url"]
            commit_sha = upload_result.get("commit_sha", "")
            await update.message.reply_text(
                f"✅ *{coding_result.project_name}*\n\n"
                f"_{coding_result.description}_\n\n"
                f"🛠 Tech: {tech}\n"
                f"📁 Files ({len(coding_result.files)}):\n{files_summary}\n\n"
                f"🔗 [View on GitHub]({github_url})"
                + (f"\n📌 Commit: `{commit_sha}`" if commit_sha else ""),
                parse_mode=ParseMode.MARKDOWN,
            )
            if coding_result.run_instructions:
                await update.message.reply_text(
                    f"▶️ *How to run:*\n```\n{coding_result.run_instructions}\n```",
                    parse_mode=ParseMode.MARKDOWN,
                )
    else:
        # Step 2b: No GitHub — send files as Telegram documents
        await update_status(
            f"📁 *{coding_result.project_name}* — {len(coding_result.files)} files generated\n"
            f"📎 Preparing files to send…"
        )
        await status_msg.delete()

        await update.message.reply_text(
            f"✅ *{coding_result.project_name}*\n\n"
            f"_{coding_result.description}_\n\n"
            f"🛠 Tech: {tech}\n"
            f"📁 Files ({len(coding_result.files)}):\n{files_summary}\n\n"
            f"💡 _Configure GITHUB\\_TOKEN + GITHUB\\_REPO to auto-upload to GitHub_",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_files_as_documents(update, context, coding_result)

        if coding_result.run_instructions:
            await update.message.reply_text(
                f"▶️ *How to run:*\n```\n{coding_result.run_instructions}\n```",
                parse_mode=ParseMode.MARKDOWN,
            )


async def _send_files_as_documents(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    coding_result: Any,
) -> None:
    """Send each generated file as a Telegram document attachment."""
    for project_file in coding_result.files:
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT
            )
            file_bytes = project_file.content.encode("utf-8")
            # Use just the filename part for the document name
            filename = project_file.path.split("/")[-1]
            await update.message.reply_document(
                document=InputFile(BytesIO(file_bytes), filename=filename),
                caption=f"`{project_file.path}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.warning("Failed to send file %s: %s", project_file.path, exc)


# ---------------------------------------------------------------------------
# Main message handler — agentic loop
# ---------------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorised to use this bot.")
        return

    user_message = update.message.text or ""
    if not user_message.strip():
        return

    user_id = update.effective_user.id

    # Send initial typing indicator
    await _send_typing(update, context)

    # We send a "thinking" status message that we update as the agent works
    status_msg = await update.message.reply_text("🤖 Thinking…")

    async def status_callback(text: str) -> None:
        try:
            await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

    result = await run_agent(user_id, user_message, status_callback=status_callback)

    # Delete the status message
    try:
        await status_msg.delete()
    except Exception:
        pass

    # Send generated images first
    for img_url in result.images:
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO
            )
            await update.message.reply_photo(
                photo=img_url,
                caption="🖼 Generated image",
            )
        except Exception as exc:
            logger.warning("Failed to send image %s: %s", img_url, exc)

    # Send generated audio
    for audio_bytes in result.audio:
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VOICE
            )
            await update.message.reply_voice(
                voice=InputFile(BytesIO(audio_bytes), filename="speech.mp3"),
            )
        except Exception as exc:
            logger.warning("Failed to send audio: %s", exc)

    # Send final text response
    if result.text:
        await _safe_reply(update, result.text)


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------


def build_app() -> Application:
    app = Application.builder().token(config.telegram_token).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("models", cmd_models))
    app.add_handler(CommandHandler("image", cmd_image))
    app.add_handler(CommandHandler("imagine", cmd_image))  # alias
    app.add_handler(CommandHandler("say", cmd_say))
    app.add_handler(CommandHandler("code", cmd_code))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(callback_model, pattern=r"^model:"))

    # All text messages
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    return app


async def set_bot_commands(app: Application) -> None:
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Show all commands"),
        BotCommand("clear", "Clear conversation history"),
        BotCommand("model", "Show or switch AI model"),
        BotCommand("models", "List available models"),
        BotCommand("image", "Generate an image"),
        BotCommand("imagine", "Generate an image (alias)"),
        BotCommand("say", "Convert text to speech"),
        BotCommand("code", "Generate a project & upload to GitHub"),
    ]
    await app.bot.set_my_commands(commands)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = build_app()

    async def post_init(application: Application) -> None:
        await set_bot_commands(application)

    app.post_init = post_init

    if config.webhook_url:
        # Production: webhook mode
        logger.info("Starting in webhook mode on port %d", config.webhook_port)
        app.run_webhook(
            listen="0.0.0.0",
            port=config.webhook_port,
            webhook_url=config.webhook_url,
            url_path=config.telegram_token,
        )
    else:
        # Development: polling mode
        logger.info("Starting in polling mode")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
