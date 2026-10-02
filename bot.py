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
        "Send a KukuFM show URL. The bot will process the series. "
        "Use this only for content you are authorized to download."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    workdir = tempfile.mkdtemp(prefix="kuku_")
    status = await update.message.reply_text("Checking series…")

    try:
        show_id = get_show_id(url)
        episodes = await asyncio.to_thread(get_all_episodes, show_id)
        await status.edit_text(f"Found {len(episodes)} episodes. Starting processing…")

        completed = 0
        failed = 0
        for episode in episodes:
            try:
                path = await asyncio.to_thread(download_episode, episode, workdir)
                completed += 1
                # Upload behavior will be expanded in the next phase.
                path.unlink(missing_ok=True)
                await status.edit_text(
                    f"Processing series… {completed}/{len(episodes)} completed"
                )
            except Exception:
                logging.exception("Episode processing failed")
                failed += 1

        await status.edit_text(
            f"Finished. Processed: {completed}, Failed: {failed}. "
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
