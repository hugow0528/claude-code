# Telegram Agentic AI Bot — Deployment Guide

## Table of Contents

1. [What This Bot Does](#what-this-bot-does)
2. [Prerequisites](#prerequisites)
3. [Step 1 — Create Your Telegram Bot](#step-1--create-your-telegram-bot)
4. [Step 2 — Get a Pollinations API Key (optional)](#step-2--get-a-pollinations-api-key-optional)
5. [Running Locally (Development)](#running-locally-development)
6. [Deploy on Railway (Recommended)](#deploy-on-railway-recommended)
7. [Deploy with Docker (Self-Hosted)](#deploy-with-docker-self-hosted)
8. [Deploy on Render (Free Tier)](#deploy-on-render-free-tier)
9. [Deploy on Fly.io](#deploy-on-flyio)
10. [Configuration Reference](#configuration-reference)
11. [Using the Bot](#using-the-bot)
12. [Available AI Models](#available-ai-models)
13. [Troubleshooting](#troubleshooting)

---

## What This Bot Does

This is a **fully agentic Telegram bot** powered by [Pollinations AI](https://pollinations.ai) — a free, OpenAI-compatible AI API. It can:

- 💬 **Chat** with context memory (remembers your conversation)
- 🔍 **Search the web** automatically when needed
- 🖼 **Generate images** from text descriptions
- 🔊 **Speak text aloud** via text-to-speech
- 🧮 **Calculate** mathematical expressions
- 🤔 **Plan and reason** with multi-step tool use

The bot uses an **agentic loop** — if answering your question requires multiple steps (e.g., search → summarise → generate image), it handles that automatically.

**No paid API keys required.** Pollinations AI provides free access to many powerful models including DeepSeek, Mistral, Qwen, and more.

---

## Prerequisites

- A [Telegram](https://telegram.org) account
- Python 3.11+ (for local development)
- Git (to clone the repository)
- A Railway / Render / Fly.io / VPS account (for deployment)

---

## Step 1 — Create Your Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Start a chat and send `/newbot`
3. Follow the prompts:
   - Choose a **name** (e.g., "My AI Assistant")
   - Choose a **username** — must end in `bot` (e.g., `myaiassistant_bot`)
4. BotFather will reply with your **bot token** — it looks like:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
5. **Save this token** — you will need it shortly.

> **Tip:** You can also set a profile picture and description for your bot via BotFather using `/setuserpic` and `/setdescription`.

---

## Step 2 — Get a Pollinations API Key (optional)

The bot works **without** an API key, but a free key gives you higher rate limits.

1. Visit [https://enter.pollinations.ai](https://enter.pollinations.ai)
2. Sign in with GitHub or Google
3. Copy your `sk_...` API key
4. Add it to your `.env` file as `POLLINATIONS_API_KEY`

---

## Running Locally (Development)

This is the quickest way to test the bot before deploying.

### 1. Clone and enter the directory

```bash
git clone <this-repo-url>
cd telegram-bot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` in any text editor and set at minimum:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
```

### 4. Run the bot

```bash
python bot.py
```

You should see:
```
2024-01-01 12:00:00 [INFO] telegram.ext.Application: Application started
```

### 5. Test it

Open Telegram, find your bot by username, and send `/start`.

> **Note:** In local mode the bot uses **polling** (no public URL needed). This is perfect for development but not ideal for production since it keeps a connection open continuously.

---

## Deploy on Railway (Recommended)

[Railway](https://railway.com) is the easiest way to deploy this bot. It has a free tier and supports Docker natively.

### Step-by-Step

#### 1. Push your code to GitHub

If you haven't already, push the `telegram-bot/` folder to a GitHub repository.

```bash
# From the repo root
git add telegram-bot/
git commit -m "Add Telegram agentic bot"
git push
```

#### 2. Create a new Railway project

1. Go to [railway.app](https://railway.app) and log in (sign up with GitHub)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. When prompted for the **Root Directory**, enter: `telegram-bot`

#### 3. Set environment variables

In Railway, go to your service → **Variables** tab → click **"Add Variable"** for each:

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `POLLINATIONS_API_KEY` | Your Pollinations key (optional) |
| `DEFAULT_MODEL` | `deepseek` (or any model from the list below) |
| `WEBHOOK_URL` | Leave **empty** for now (see step 4) |

#### 4. Get your Railway URL and set the webhook

After the first deploy:

1. Go to **Settings** → **Domains** → click **"Generate Domain"**
2. You'll get a URL like `https://your-app.up.railway.app`
3. Now go back to **Variables** and add:
   ```
   WEBHOOK_URL=https://your-app.up.railway.app/<YOUR_BOT_TOKEN>
   ```
   Replace `<YOUR_BOT_TOKEN>` with your actual bot token (the full string).

4. Railway will **automatically redeploy** with the new variable. The bot will now use webhooks instead of polling.

#### 5. Verify deployment

- Check the **Logs** tab in Railway for `Application started`
- Send `/start` to your bot on Telegram

> **Railway Free Tier Notes:**
> - Free tier includes $5 of usage per month
> - The bot is very lightweight — typically costs < $1/month
> - Railway keeps your app running 24/7 (unlike Render's free tier)

---

## Deploy with Docker (Self-Hosted)

If you have a VPS (DigitalOcean, Linode, Hetzner, etc.) with Docker installed:

### 1. Upload the `telegram-bot/` directory to your server

```bash
scp -r telegram-bot/ user@your-server-ip:/opt/telegram-bot/
```

### 2. SSH into your server

```bash
ssh user@your-server-ip
cd /opt/telegram-bot
```

### 3. Create and configure `.env`

```bash
cp .env.example .env
nano .env   # Edit with your values
```

For webhook mode with a VPS, you need a domain pointing to your server. Set:
```env
WEBHOOK_URL=https://yourdomain.com/<YOUR_BOT_TOKEN>
PORT=8443
```

You'll also need to set up a reverse proxy (Nginx or Caddy) to handle HTTPS and forward to port 8443.

### 4. (Optional) Nginx reverse proxy config

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    # SSL certificates from Let's Encrypt (certbot)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 5. Start with Docker Compose

```bash
docker compose up -d
```

### 6. View logs

```bash
docker compose logs -f
```

### 7. Update the bot

```bash
git pull
docker compose up -d --build
```

---

## Deploy on Render (Free Tier)

[Render](https://render.com) has a **completely free** Web Service tier.

> ⚠️ **Limitation:** Render's free tier spins down after 15 minutes of inactivity. For a bot, this means ~30-second cold start delay on first message after idle. This is acceptable for personal use.

### Steps

1. Go to [render.com](https://render.com) and create an account
2. Click **"New"** → **"Web Service"**
3. Connect your GitHub repo
4. Configure:
   - **Root Directory:** `telegram-bot`
   - **Runtime:** Docker
   - **Instance Type:** Free
5. Add environment variables (same as Railway above)
6. Click **"Create Web Service"**
7. After deploy, get your Render URL (e.g., `https://your-app.onrender.com`)
8. Set `WEBHOOK_URL=https://your-app.onrender.com/<YOUR_BOT_TOKEN>`

---

## Deploy on Fly.io

[Fly.io](https://fly.io) offers a generous free tier and global edge deployment.

### 1. Install the Fly CLI

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 2. From the `telegram-bot/` directory, launch the app

```bash
cd telegram-bot
fly launch --name my-telegram-bot --no-deploy
```

When prompted, choose a region close to your users.

### 3. Set secrets (environment variables)

```bash
fly secrets set TELEGRAM_BOT_TOKEN="your_token_here"
fly secrets set POLLINATIONS_API_KEY="your_key_here"
fly secrets set DEFAULT_MODEL="deepseek"
```

### 4. Deploy

```bash
fly deploy
```

### 5. Get your URL and set webhook

```bash
fly info   # Shows your app URL, e.g. https://my-telegram-bot.fly.dev
fly secrets set WEBHOOK_URL="https://my-telegram-bot.fly.dev/<YOUR_BOT_TOKEN>"
fly deploy
```

---

## Configuration Reference

All settings are in `.env` (or set as environment variables on your platform):

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | **required** | Bot token from BotFather |
| `POLLINATIONS_API_KEY` | _(empty)_ | Pollinations API key for higher rate limits |
| `DEFAULT_MODEL` | `deepseek` | Default AI text model |
| `DEFAULT_IMAGE_MODEL` | `flux` | Default image generation model |
| `MAX_HISTORY_TURNS` | `20` | Conversation turns to keep per user |
| `MAX_AGENT_ITERATIONS` | `8` | Max tool-use steps per response |
| `WEBHOOK_URL` | _(empty)_ | Full webhook URL (enables webhook mode) |
| `PORT` | `8443` | Port for webhook listener |
| `ALLOWED_USER_IDS` | _(empty)_ | Comma-separated Telegram user IDs to whitelist |

### How to find your Telegram user ID

Send a message to [@userinfobot](https://t.me/userinfobot) on Telegram. It will reply with your numeric user ID.

---

## Using the Bot

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message, shows current model |
| `/help` | Full help with all commands |
| `/clear` | Clear your conversation history |
| `/model` | Show current model (with button to switch) |
| `/model deepseek` | Switch to a specific model |
| `/models` | List all available models |
| `/image a cat in space` | Generate an image directly |
| `/imagine a sunset over Tokyo` | Same as `/image` |
| `/say Hello world` | Convert text to speech |

### Just Chat!

You don't need to use commands for most things. Just send messages naturally:

- *"What's the weather like in Paris today?"* → searches the web
- *"Draw me a futuristic city at night"* → generates an image
- *"What is 15% of 847?"* → calculates
- *"Read this text aloud: Welcome to my bot!"* → generates speech
- *"Explain how blockchain works"* → answers from knowledge

### Multi-step Agentic Behaviour

The bot can chain multiple tools in one response:

> User: *"Search for the latest news about AI, then make an image summarising it"*

The bot will:
1. 🔍 Search the web for AI news
2. 🤔 Read and summarise the results  
3. 🖼 Generate an image based on the summary
4. 💬 Send both the image and a text summary

---

## Available AI Models

All models below are **non-paid** (free to use via Pollinations):

| Model ID | Description | Best For |
|----------|-------------|----------|
| `deepseek` | DeepSeek V3.2 | General tasks, coding, agentic reasoning |
| `mistral` | Mistral Small 3.2 24B | Fast, efficient general use |
| `qwen-coder` | Qwen3 Coder 30B | Code generation and explanation |
| `glm` | Z.ai GLM-5 744B MoE | Long context, complex reasoning |
| `minimax` | MiniMax M2.5 | Multi-language, agentic tasks |
| `gemini-fast` | Gemini 2.5 Flash Lite | Fast with Google Search grounding |
| `nova-fast` | Amazon Nova Micro | Ultra fast, cheap |
| `kimi` | Moonshot Kimi K2.5 | Agentic, vision, reasoning |
| `openai` | GPT-5 Mini | Balanced performance |
| `openai-fast` | GPT-5 Nano | Fastest responses |
| `claude-fast` | Claude Haiku 4.5 | Intelligent, fast |
| `perplexity-fast` | Perplexity Sonar | Web search specialist |

Switch models with `/model <name>` or the inline keyboard via `/model`.

---

## Troubleshooting

### Bot doesn't respond

1. Check that `TELEGRAM_BOT_TOKEN` is set correctly
2. Check Railway/Render/Fly logs for errors
3. Try sending `/start` again
4. Verify the bot is running: check the **Logs** tab on your platform

### "Unauthorized" error in logs

Your `TELEGRAM_BOT_TOKEN` is invalid. Get a new one from @BotFather.

### Images not generating

- The image URL might take a few seconds to resolve
- Try a different image model: `/model` then switch, or use `flux` which is most reliable
- Check your Pollinations API key if you have rate-limit errors

### "HTTP 429" rate limit errors

- Add a `POLLINATIONS_API_KEY` (free from [enter.pollinations.ai](https://enter.pollinations.ai))
- Reduce `MAX_AGENT_ITERATIONS` to 4

### Webhook not working (Railway/Render)

1. Make sure `WEBHOOK_URL` exactly matches: `https://your-domain.com/<BOT_TOKEN>`
2. The token in the URL must match `TELEGRAM_BOT_TOKEN`
3. HTTPS is required — self-signed certificates won't work
4. Check that port 443 or 8443 is accessible from the internet
5. Try deleting and re-setting the webhook:
   ```
   https://api.telegram.org/bot<TOKEN>/deleteWebhook
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WEBHOOK_URL>
   ```

### Bot works locally but not in production

- Make sure all environment variables from `.env` are set on your platform
- Check that `WEBHOOK_URL` is set for production (enables webhook mode)
- Without `WEBHOOK_URL`, the bot runs in polling mode — fine for Railway, but not Render

### Conversation context lost after restart

This is by design — conversation history is stored **in memory** and is cleared when the bot restarts. For persistent history across restarts, you would need to add a database (Redis, SQLite, etc.).

---

## Architecture Overview

```
User (Telegram) ──► bot.py (Telegram handlers)
                        │
                        ▼
                    agent.py (Agentic loop)
                    ┌─────────────────────────────────┐
                    │  1. Send messages to model       │
                    │  2. Model returns tool_calls     │
                    │  3. Execute tools                │
                    │  4. Append results to messages   │
                    │  5. Repeat until text response   │
                    └─────────────────────────────────┘
                        │
                    tools.py (Tool implementations)
                    ├── generate_image  ──► Pollinations /image/
                    ├── web_search      ──► Pollinations /v1/chat (gemini-search)
                    ├── text_to_speech  ──► Pollinations /audio/
                    ├── get_current_time ──► (local)
                    └── calculate       ──► (local, safe eval)
```

The agentic loop is inspired by [Claude Code's](https://claude.ai/code) coordinator/agent architecture, using OpenAI-compatible tool-calling via the Pollinations API.

---

## Contributing / Extending

To add new tools:

1. **Define the tool schema** in `tools.py` → add to the `TOOLS` list
2. **Implement the function** in `tools.py`
3. **Add the dispatch case** in the `dispatch_tool()` function
4. The agent will automatically discover and use the new tool

Example — adding a "get_joke" tool:

```python
# In TOOLS list:
{
    "type": "function",
    "function": {
        "name": "get_joke",
        "description": "Tell a random joke.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}

# Implementation:
async def tool_get_joke() -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get("https://official-joke-api.appspot.com/random_joke")
        data = r.json()
    return {"joke": f"{data['setup']} — {data['punchline']}"}

# In dispatch_tool():
elif name == "get_joke":
    result = await tool_get_joke()
```

That's all you need — the model will call it when appropriate!
