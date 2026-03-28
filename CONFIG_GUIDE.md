# ⚙️ Configuration Guide

This guide explains every configuration field available in `.env` and `config/config.json`.

> **Priority order** (highest wins): Environment variable (`.env`) → `config/config.json` → `config/default.json`

---

## How to Configure

**Option A — Edit `.env`** (recommended for most buyers)

```
BRAND_NAME=MyChatApp
AI_ENABLED=false
```

**Option B — Edit `config/config.json`** (useful for version-controlled deployments)

Create the file if it does not exist:

```json
{
  "brand_name": "MyChatApp",
  "ai_enabled": false,
  "default_language": "es"
}
```

Only include the fields you want to override — missing fields fall back to `config/default.json`.

---

## Field Reference

### `BRAND_NAME` / `brand_name`

| | |
|---|---|
| **Type** | string |
| **Default** | `Anonymous Chat` |
| **Example** | `MyChatApp` |

The name of your bot shown in welcome messages, the admin dashboard title, and all user-facing notifications.

```
# .env
BRAND_NAME=MyChatApp
```

Result in the welcome message:
> *"Welcome to **MyChatApp**!"*

---

### `DEFAULT_LANGUAGE` / `default_language`

| | |
|---|---|
| **Type** | ISO 639-1 language code (2 letters) |
| **Default** | `en` |
| **Example** | `hi` |

The UI language assigned to new users when they first start the bot. Users can always change their language later with `/language`.

```
DEFAULT_LANGUAGE=hi
```

**Supported codes:**

| Code | Language |
|------|----------|
| `en` | English |
| `hi` | Hindi / Hinglish |
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `pt` | Portuguese |
| `ar` | Arabic |
| `ru` | Russian |
| `tr` | Turkish |
| `id` | Indonesian |

---

### `ALLOWED_LANGUAGES` / `allowed_languages`

| | |
|---|---|
| **Type** | Comma-separated list of ISO codes |
| **Default** | `en,hi,es` |
| **Example** | `en,es,pt,fr` |

Controls which languages appear in the `/language` selector. Use this to limit the bot to your target market.

```
# .env — show only English and Spanish
ALLOWED_LANGUAGES=en,es
```

```json
// config/config.json — list form also accepted
{
  "allowed_languages": ["en", "es", "pt"]
}
```

> **Tip:** Keep `DEFAULT_LANGUAGE` within your `ALLOWED_LANGUAGES` list.

---

### `DEFAULT_CHAT_MODE` / `default_chat_mode`

| | |
|---|---|
| **Type** | `mixed` \| `english` \| `native` |
| **Default** | `mixed` |
| **Example** | `native` |

Controls how the AI fallback engine mixes languages in simulated partner messages.

| Value | Behaviour |
|-------|-----------|
| `mixed` | Blends user's language with English (e.g. Hinglish for Hindi users) |
| `english` | Always responds in English regardless of user language |
| `native` | Responds entirely in the user's chosen language, no English mixing |

```
DEFAULT_CHAT_MODE=native
```

---

### `AI_ENABLED` / `ai_enabled`

| | |
|---|---|
| **Type** | `true` / `false` |
| **Default** | `true` |
| **Example** | `false` |

When `true`, the bot uses an LLM (via `OPENAI_API_KEY`) to generate realistic simulated partner messages when no real match is found in time.

When `false`, the bot falls back to pre-written message templates — no API key is needed and there are no per-message AI costs.

```
# Disable AI completely — use templates only
AI_ENABLED=false
```

```
# Enable AI (requires OPENAI_API_KEY)
AI_ENABLED=true
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

> **Cost note:** `gpt-4o-mini` is the recommended model for the best cost-to-quality balance. The bot sends short prompts (1–2 sentence responses), so API costs are typically very low.

---

### `PAYMENT_ENABLED` / `payment_enabled`

| | |
|---|---|
| **Type** | `true` / `false` |
| **Default** | `true` |
| **Example** | `false` |

When `true`, users can purchase Premium and VIP subscriptions using Telegram Stars via `/pay` and `/vip` commands.

| Plan | Price | Benefit |
|------|-------|---------|
| Premium | 100 ⭐ Stars | Gender filter — choose to match only male or female |
| VIP | 250 ⭐ Stars | Priority queue — matched faster than all other users |

When `false`, the `/pay` and `/vip` commands return a friendly "not available" message and no payment UI is shown.

```
# Disable payments entirely
PAYMENT_ENABLED=false
```

```
# Enable payments (default)
PAYMENT_ENABLED=true
```

---

## Other Settings

### `BOT_TOKEN` *(required)*

Your Telegram Bot Token from [@BotFather](https://t.me/BotFather). This is the only value you **must** set.

### `ADMIN_TOKEN` *(required)*

A secret string used to authenticate the admin dashboard at `http://localhost:8000`. Change this to a long random string before deploying.

```
ADMIN_TOKEN=my-very-long-random-secret-token-here
```

### `MONGODB_URI`

MongoDB connection string. The default value works with the included `docker-compose.yml`.

```
MONGODB_URI=mongodb://mongo:27017
```

### `REDIS_URL`

Redis connection string. The default works with `docker-compose.yml`.

```
REDIS_URL=redis://redis:6379
```

### `DB_NAME`

MongoDB database name. Change this if you are running multiple bots on the same MongoDB instance.

```
DB_NAME=my_chat_bot
```

### `DEBUG`

Set to `true` to enable verbose logging. Only use during development.

```
DEBUG=false
```

---

## Minimal `.env` Example

This is the smallest valid `.env` needed to run the bot with your own branding:

```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_TOKEN=my-strong-secret-token
BRAND_NAME=MyChatApp
```

All other settings will use their defaults from `config/default.json`.

---

## Full `.env` Example

```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
MONGODB_URI=mongodb://mongo:27017
REDIS_URL=redis://redis:6379
DB_NAME=anonymous_chat
ADMIN_TOKEN=my-strong-secret-token
DEBUG=false

BRAND_NAME=MyChatApp
DEFAULT_LANGUAGE=en
ALLOWED_LANGUAGES=en,hi,es
DEFAULT_CHAT_MODE=mixed

AI_ENABLED=true
OPENAI_API_KEY=sk-your-openai-key
LLM_MODEL=gpt-4o-mini

PAYMENT_ENABLED=true
```
