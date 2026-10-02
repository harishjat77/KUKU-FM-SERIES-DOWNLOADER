# HB Kuku Audio Uploader

Telegram bot workflow for show URLs and authorized/downloadable audio.

## Commands

- `/start` — welcome + command list
- `/HB` — asks for a clean `https://kukufm.com/show/<show-slug>` URL
- `/pause` — pause between episode steps
- `/resume` — continue
- `/stop` — stop after the current blocking step finishes

## Render variables

- `BOT_TOKEN` — Telegram bot token
- `TARGET_CHANNEL` — target channel username (for example `@mychannel`) or numeric chat ID
- `OWNER_USER_ID` — optional but recommended; only this Telegram user can control the bot
- `REQUEST_TIMEOUT` — defaults to 30

Add the bot as an administrator in the target channel with permission to post messages.

The bot validates the show URL, reads show metadata, downloads the poster when available, creates M4A audio with embedded cover art, and uploads each episode to the configured Telegram channel.

Only use it for media you own or are authorized to download/distribute.
