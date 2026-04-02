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
from config import config
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
        "/say `<text>` — Convert text to speech\n\n"
        "💡 *Tips*\n"
        "• Just chat naturally — I'll use tools when needed\n"
        "• Ask me to draw, search, calculate, or speak anything\n"
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
