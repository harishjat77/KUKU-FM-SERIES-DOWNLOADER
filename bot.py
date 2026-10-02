import asyncio
import html
import logging
import os
import shutil
import tempfile
from pathlib import Path

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import (
    download_episode,
    download_poster,
    get_all_episodes,
    get_show_info,
    get_show_slug,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"]
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

jobs = {}


def allowed(update: Update) -> bool:
    if not OWNER_USER_ID:
        return True
    return bool(update.effective_user and update.effective_user.id == OWNER_USER_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    context.user_data["awaiting_show_url"] = False
    await update.message.reply_text(
        "👋 Welcome to HB Audio Uploader!\n\n"
        "Available commands:\n"
        "/hb — Start a new show download & upload\n"
        "/pause — Pause current job\n"
        "/resume — Resume paused job\n"
        "/stop — Stop current job\n\n"
        "Use /hb and paste a clean show URL when asked."
    )


async def hb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    uid = update.effective_user.id
    active = jobs.get(uid)
    if active and not active.get("stopped"):
        await update.message.reply_text(
            "A job is already active. Use /stop first."
        )
        return
    context.user_data["awaiting_show_url"] = True
    await update.message.reply_text(
        "Enter show URL:\n"
        "https://kukufm.com/show/<show-slug>\n\n"
        "Example:\nhttps://kukufm.com/show/entrepreneur-5pm-to-9am-1"
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    job = jobs.get(update.effective_user.id)
    if not job or job.get("stopped"):
        await update.message.reply_text("No active job.")
        return
    job["paused"] = True
    await update.message.reply_text("⏸ Job paused. Use /resume to continue.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    job = jobs.get(update.effective_user.id)
    if not job or job.get("stopped"):
        await update.message.reply_text("No paused job.")
        return
    job["paused"] = False
    await update.message.reply_text("▶️ Job resumed.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    job = jobs.get(update.effective_user.id)
    context.user_data["awaiting_show_url"] = False
    if not job or job.get("stopped"):
        await update.message.reply_text("No active job.")
        return
    job["stopped"] = True
    job["paused"] = False
    await update.message.reply_text(
        "⏹ Stop requested. Current step will finish, then the job will stop."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    if not context.user_data.get("awaiting_show_url"):
        await update.message.reply_text("Use /hb first.")
        return

    url = (update.message.text or "").strip()
    try:
        slug = get_show_slug(url)
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return

    context.user_data["awaiting_show_url"] = False
    uid = update.effective_user.id
    jobs[uid] = {"paused": False, "stopped": False}
    asyncio.create_task(process_show(update, uid, slug))


async def process_show(update: Update, uid: int, slug: str):
    job = jobs[uid]
    workdir = Path(tempfile.mkdtemp(prefix="hb_"))
    status = await update.message.reply_text("🔎 Reading show details…")

    try:
        show = await asyncio.to_thread(get_show_info, slug)
        episodes = await asyncio.to_thread(get_all_episodes, slug)
        show_name = show["name"]

        if not episodes:
            await status.edit_text("❌ No episodes found.")
            return

        poster = None
        try:
            poster = await asyncio.to_thread(
                download_poster, show.get("poster_url"), workdir
            )
        except Exception:
            logging.exception("Poster download failed")

        total = len(episodes)
        await status.edit_text(
            f"🎧 {html.escape(show_name)}\nEpisodes: {total}\nStarting…"
        )

        sent = 0
        failed = 0

        for position, episode in enumerate(episodes, start=1):
            while job["paused"] and not job["stopped"]:
                await asyncio.sleep(1)
            if job["stopped"]:
                break

            ep_no = int(episode.get("index") or position)
            ep_name = str(episode.get("title") or f"Episode {ep_no}")

            try:
                await status.edit_text(
                    f"⬇️ Processing {position}/{total}\n{ep_name}"
                )
                audio_path = await asyncio.to_thread(
                    download_episode, episode, workdir, poster
                )

                # Caption: show name bold + quotes, episode number + name
                caption = (
                    f"🎧 <b>“{html.escape(show_name)}”</b>\n\n"
                    f"🎙 <b>Episode {ep_no}</b>\n"
                    f"📖 {html.escape(ep_name)}"
                )

                with audio_path.open("rb") as audio:
                    thumb = (
                        poster.open("rb")
                        if poster and poster.exists()
                        else None
                    )
                    try:
                        await update.get_bot().send_audio(
                            chat_id=TARGET_CHANNEL,
                            audio=audio,
                            thumbnail=thumb,
                            title=ep_name,
                            performer=show_name,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=60,
                            pool_timeout=60,
                        )
                    finally:
                        if thumb:
                            thumb.close()

                sent += 1
                audio_path.unlink(missing_ok=True)
                await status.edit_text(
                    f"⬆️ Uploaded {sent}/{total}\n{ep_name}"
                )

            except TelegramError as exc:
                failed += 1
                logging.exception("Telegram upload failed: %s", exc)
            except Exception as exc:
                failed += 1
                logging.exception("Episode failed: %s", exc)

        if job["stopped"]:
            await status.edit_text(
                f"⏹ Stopped. Uploaded: {sent} | Failed: {failed}"
            )
        else:
            await status.edit_text(
                f"✅ Completed. Uploaded: {sent}/{total} | Failed: {failed}"
            )
    except Exception as exc:
        logging.exception("Show job failed")
        await status.edit_text(f"❌ Error: {exc}")
    finally:
        job["stopped"] = True
        shutil.rmtree(workdir, ignore_errors=True)


async def post_init(app):
    # Telegram requires command names to be lowercase only
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Welcome and commands"),
            BotCommand("hb", "Start show download/upload"),
            BotCommand("pause", "Pause current job"),
            BotCommand("resume", "Resume paused job"),
            BotCommand("stop", "Stop current job"),
        ]
    )


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    # Accept both /hb and /HB (Telegram normalizes; handler is case-insensitive)
    app.add_handler(CommandHandler(["hb", "HB"], hb))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
