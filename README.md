# 🤖 Anonymous Chat Bot — White-Label Telegram Bot

A white-label, production-ready Telegram bot for anonymous stranger chat. Buyers can deploy it under their own brand, in any language, with no coding required.

---

## ✨ Features

- 🔍 **Anonymous matchmaking** — pair strangers for private, one-on-one chats
- 🌐 **Multi-language UI** — English, Hindi, Spanish and more (configurable)
- 🤖 **AI fallback engine** — LLM-powered simulated partner keeps users engaged (optional)
- 💳 **Telegram Stars payments** — built-in Premium and VIP subscription tiers (optional)
- 👑 **Priority queue** — VIP users matched faster
- 🛡️ **Anti-abuse system** — automatic spam detection and cooldowns
- 📊 **Admin dashboard** — real-time stats and runtime config at `http://localhost:8000`
- 🏷️ **White-label ready** — change brand name, language, and features via `.env` only

---

## 🚀 Setup — Step by Step

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/chatbot.git
cd chatbot
```

### 2. Create your environment file

```bash
cp .env.example .env
```

### 3. Add your Bot Token

Open `.env` in any text editor and set your token:

```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

> Get a token by messaging [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`.

### 4. (Optional) Set your brand name

In `.env`, change:

```
BRAND_NAME=YourBotName
```

This name appears in all welcome messages sent to users.

### 5. Start the bot

```bash
docker-compose up -d
```

Docker will pull the required images (MongoDB, Redis) and start three services:

| Service | Description |
|---------|-------------|
| `bot` | The Telegram bot |
| `admin` | Admin dashboard at port 8000 |
| `mongo` | MongoDB database |
| `redis` | Redis cache |

### 6. Verify it's running

```bash
docker-compose logs -f bot
```

You should see `Bot started.` in the logs. Send `/start` to your bot on Telegram.

### 7. Access the admin dashboard

Open `http://localhost:8000` in your browser.  
Enter your `ADMIN_TOKEN` from `.env` to log in.

---

## 🏷️ How to Change Branding

Edit `.env`:

```
BRAND_NAME=MyChatApp
```

Restart the bot:

```bash
docker-compose restart bot
```

The bot's welcome message will now say *"Welcome to **MyChatApp**!"*.

---

## 🤖 How to Enable / Disable AI

### ✅ Zero-Config Setup — one line only

Just paste your API key from **any** supported provider and restart. The bot automatically detects the provider and picks the best model — nothing else needs to change:

```
AI_ENABLED=true
LLM_API_KEY=your-api-key-here
```

**Supported providers and how the key is auto-detected:**

| Key prefix | Provider | Model selection |
|------------|----------|-----------------|
| `sk-ant-…` | Anthropic (Claude) | Auto-discovered from provider's API |
| `gsk_…`    | Groq (Llama / Mixtral) | Auto-discovered from provider's API |
| `AIza…`    | Gemini (Google) | Auto-discovered from provider's API |
| `xai-…`    | Grok (xAI) | Auto-discovered from provider's API |
| `sk-…`     | OpenAI (GPT) | Auto-discovered from provider's API |

> For providers without a recognizable prefix (Mistral, DeepSeek, Together) either set `LLM_PROVIDER=mistral` alongside `LLM_API_KEY`, or use the provider-specific alias (`MISTRAL_API_KEY=…`).

> **Note:** DeepSeek also uses `sk-…` keys. If your key starts with `sk-` but you are using DeepSeek, set `LLM_PROVIDER=deepseek` explicitly to override the auto-detection.

### Override provider or model (optional)

You can override the auto-detected provider and/or model:

```
LLM_API_KEY=your-api-key-here
LLM_PROVIDER=gemini          # optional — overrides auto-detection
LLM_MODEL=gemini-2.0-flash   # optional — overrides auto-discovered model
```

### Disable AI

```
AI_ENABLED=false
```

Template responses only — no API key or cost required.

Restart after any change:

```bash
docker-compose restart bot
```

---

## 🌐 How to Change Language

Set the default language for new users:

```
DEFAULT_LANGUAGE=es
```

Restrict which languages users can pick from:

```
ALLOWED_LANGUAGES=en,es,pt
```

Available language codes: `en` (English), `hi` (Hindi), `es` (Spanish), `fr` (French), `de` (German), `pt` (Portuguese), `ar` (Arabic), `ru` (Russian), `tr` (Turkish), `id` (Indonesian).

Change how the bot mixes languages in chat:

```
DEFAULT_CHAT_MODE=mixed    # blend native + English
DEFAULT_CHAT_MODE=english  # English only
DEFAULT_CHAT_MODE=native   # native language only
```

---

## 💳 How to Enable / Disable Payments

**Enable** Telegram Stars payments (`/pay`, `/vip` commands):

```
PAYMENT_ENABLED=true
```

**Disable** all payment features:

```
PAYMENT_ENABLED=false
```

---

## ⚙️ Full Configuration Reference

See **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)** for a complete explanation of every setting.

---

## 🛑 Stopping the Bot

```bash
docker-compose down
```

To also remove stored data (MongoDB volume):

```bash
docker-compose down -v
```

---

## 📁 Project Structure

```
chatbot/
├── bot/              # Telegram bot (aiogram)
│   ├── handlers/     # Command handlers (/start, /search, /pay …)
│   ├── i18n/         # Translation files (en, hi, es …)
│   ├── services/     # Matchmaking, AI, anti-abuse, analytics
│   └── config.py     # Infrastructure settings (loaded from .env)
├── admin/            # Admin dashboard (FastAPI + HTML)
├── config/           # White-label config (app_config.py, default.json)
├── .env.example      # Template — copy to .env and fill in
├── docker-compose.yml
└── CONFIG_GUIDE.md   # Full config reference
```

---

## 🆘 Support

For white-label customisation requests or deployment help, contact the seller via the platform you purchased this product from.
