# KUKU-FM-SERIES-DOWNLOADER

Telegram bot + KukuFM show parser foundation prepared for Render.

## Environment variables

- `BOT_TOKEN` — Telegram BotFather token
- `FFMPEG_PATH` — optional; defaults to `ffmpeg`
- `USER_AGENT` — optional browser-style user agent
- `REQUEST_TIMEOUT` — optional HTTP timeout in seconds; defaults to `30`

Never commit authentication/session secrets to GitHub.

## Current flow

1. `/start`
2. Send a valid `/show/<slug>` URL
3. The current show response is parsed for `initialData.show` and `initialData.episodes`
4. Episodes are sorted by `index`
5. Only media marked downloadable by the response is processed
6. FFmpeg selects the audio stream and creates `.m4a` output
7. Temporary files are cleaned up

The Dockerfile installs FFmpeg and the repository includes a Render background-worker definition.

Telegram episode delivery is intentionally left for the next development phase.

Only process content you own or are authorized to download/distribute.
