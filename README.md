# KUKU-FM-SERIES-DOWNLOADER

Telegram bot + downloader foundation prepared for Render.

## Environment variables

- `BOT_TOKEN` — Telegram BotFather token
- `KUKU_GUEST_USER_ID` — optional authenticated guest/user cookie value
- `KUKU_JWT_TOKEN` — optional authenticated session token

Never commit real tokens to GitHub.

## Render

The repository includes a Dockerfile with FFmpeg and a `render.yaml` background-worker definition.

Current bot flow:

1. `/start`
2. Send a valid KukuFM show URL
3. Bot fetches the episode list
4. Episodes are processed one-by-one with FFmpeg
5. Temporary files are removed after processing

Telegram episode delivery is intentionally left for the next development phase.

Only process content you own or are authorized to download/distribute.
