# HB KukuFM Audio Uploader

Telegram bot that downloads KukuFM show episodes (with show poster as cover art) and uploads them to your Telegram channel.

## Commands

- `/start` — Welcome message + command list (no download starts)
- `/HB` — Asks for a clean show URL, then downloads + uploads
- `/pause` — Pause between episode steps
- `/resume` — Continue a paused job
- `/stop` — Stop after the current step finishes

### Show URL format (strict)

Only accepted:

```
https://kukufm.com/show/<show-slug>
```

Example:

```
https://kukufm.com/show/entrepreneur-5pm-to-9am-1
```

Any other format (extra path, query string, http, wrong domain) → bot replies with **Invalid URL** error.

## Caption format (per episode)

```
🎧 “Show Name”     ← bold + quotes

🎙 Episode 01
📖 Episode Title
```

Show poster is downloaded from the show page and:
1. Embedded as cover art inside each `.m4a`
2. Sent as Telegram audio thumbnail

## Required environment variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `TARGET_CHANNEL` | Channel username (`@yourchannel`) or numeric chat ID |
| `OWNER_USER_ID` | (Recommended) Your Telegram user ID — only this user can control the bot |

## Optional (for authenticated / premium audio)

Set these if public API does not return downloadable URLs (same values as in your working local script):

| Variable | Cookie / value |
|----------|----------------|
| `JWT_TOKEN` | `jwtToken` |
| `CLOUDFRONT_POLICY` | `CloudFront-Policy` |
| `CLOUDFRONT_SIGNATURE` | `CloudFront-Signature` |
| `CLOUDFRONT_KEY_PAIR_ID` | `CloudFront-Key-Pair-Id` |
| `GUEST_USER_ID` | `guest_user_id` |
| `CLIENT_ID` | `clientId` |
| `PREFERRED_LANG` | `hindi` (default) |
| `REQUEST_TIMEOUT` | API timeout seconds (default 30) |

**Important:** CloudFront cookies expire. When downloads start failing, refresh them from browser and update the env vars on Render (or wherever the bot runs).

## Deploy on Render

1. Connect this repo.
2. It uses the included `Dockerfile` + `render.yaml` (worker service).
3. Add the env vars above in the Render dashboard.
4. Add the bot as **administrator** in your target channel (permission to post messages).
5. Start the service → send `/start` to the bot.

## Local run

```bash
export BOT_TOKEN=...
export TARGET_CHANNEL=@yourchannel
export OWNER_USER_ID=123456789
# optional cookies...
python bot.py
```

Only use for media you own or are authorized to download/distribute.
