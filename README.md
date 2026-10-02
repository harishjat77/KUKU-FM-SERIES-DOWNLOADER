# KUKU-FM-SERIES-DOWNLOADER

Telegram bot + KukuFM show parser prepared for Render.

## Environment variables

- `BOT_TOKEN` — Telegram BotFather token
- `FFMPEG_PATH` — optional; defaults to `ffmpeg`
- `USER_AGENT` — optional browser-style user agent
- `REQUEST_TIMEOUT` — optional HTTP timeout in seconds; defaults to `30`

Never commit authentication/session secrets to GitHub.

## Bot flow

1. Start the bot with `/start`
2. Send a valid `/show/<slug>` URL
3. The current show response is parsed for `initialData.show` and `initialData.episodes`
4. Episodes are sorted by their `index`
5. Only media marked downloadable by the response is processed
6. FFmpeg selects the audio stream and creates an `.m4a` file
7. The bot sends the M4A as Telegram audio
8. Each temporary file is deleted after upload and the job directory is removed at the end
9. A final sent/failed summary is shown

The Dockerfile installs FFmpeg. `render.yaml` defines the bot as a Docker background worker.

Only process content you own or are authorized to download/distribute.
