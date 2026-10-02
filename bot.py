import asyncio
import logging
import os
import shutil
import tempfile

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import download_episode, get_all_episodes, get_show_id

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ["BOT_TOKEN"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a KukuFM show URL. The bot will process permitted episodes as M4A audio."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    workdir = tempfile.mkdtemp(prefix="kuku_")
    status = await update.message.reply_text("Checking series…")

    try:
        show_slug = get_show_id(url)
        episodes = await asyncio.to_thread(get_all_episodes, show_slug)
        await status.edit_text(
            f"Found {len(episodes)} episodes. Starting M4A processing…"
        )

        completed = 0
        failed = 0

        for episode in episodes:
            try:
                path = await asyncio.to_thread(download_episode, episode, workdir)
                completed += 1
                # Telegram upload is intentionally kept for the delivery phase.
                path.unlink(missing_ok=True)
                await status.edit_text(
                    f"Processing series… {completed}/{len(episodes)} completed"
                )
            except Exception as exc:
                logging.exception("Episode processing failed")
                failed += 1
                logging.warning("Episode skipped: %s", exc)

        await status.edit_text(
            f"Finished. Processed: {completed}, Failed/skipped: {failed}. "
            "Telegram delivery will be added in the next phase."
        )
    except Exception as exc:
        logging.exception("Job failed")
        await status.edit_text(f"Error: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
