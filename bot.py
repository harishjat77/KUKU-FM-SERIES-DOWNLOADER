import asyncio
import logging
import os
import shutil
import tempfile

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import download_episode, get_all_episodes, get_show_id

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
BOT_TOKEN = os.environ["BOT_TOKEN"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a KukuFM /show/<slug> URL. Permitted episodes will be processed "
        "as M4A audio and sent here."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    url = (message.text or "").strip()
    workdir = tempfile.mkdtemp(prefix="kuku_")
    status = await message.reply_text("Checking series…")

    try:
        show_slug = get_show_id(url)
        episodes = await asyncio.to_thread(get_all_episodes, show_slug)

        if not episodes:
            await status.edit_text("No episodes were found.")
            return

        total = len(episodes)
        await status.edit_text(f"Found {total} episodes. Starting M4A processing…")

        sent = 0
        skipped = 0

        for position, episode in enumerate(episodes, start=1):
            title = str(episode.get("title") or f"Episode {position}")
            try:
                await status.edit_text(
                    f"Processing {position}/{total}\n{title}"
                )
                path = await asyncio.to_thread(download_episode, episode, workdir)

                try:
                    with path.open("rb") as audio_file:
                        await message.reply_audio(
                            audio=audio_file,
                            title=title,
                            filename=path.name,
                            caption=f"{position}/{total} • {title}",
                            read_timeout=300,
                            write_timeout=300,
                            connect_timeout=60,
                            pool_timeout=60,
                        )
                    sent += 1
                finally:
                    path.unlink(missing_ok=True)

            except TelegramError as exc:
                logging.exception("Telegram upload failed")
                skipped += 1
                logging.warning("Upload skipped for %s: %s", title, exc)
            except Exception as exc:
                logging.exception("Episode processing failed")
                skipped += 1
                logging.warning("Episode skipped: %s", exc)

        await status.edit_text(
            f"Finished. Sent: {sent}/{total}. Failed/skipped: {skipped}."
        )

    except ValueError as exc:
        await status.edit_text(str(exc))
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
