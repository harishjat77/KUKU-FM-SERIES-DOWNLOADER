import asyncio
import html
import logging
import os
import shutil
import tempfile
from pathlib import Path

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.error import Conflict, NetworkError, TelegramError, TimedOut
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
logger = logging.getLogger(__name__)

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
    context.user_data["awaiting_start_episode"] = False
    context.user_data.pop("pending_show_slug", None)
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
    context.user_data["awaiting_start_episode"] = False
    context.user_data.pop("pending_show_slug", None)
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
    context.user_data["awaiting_start_episode"] = False
    context.user_data.pop("pending_show_slug", None)
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

    text = (update.message.text or "").strip()

    if context.user_data.get("awaiting_show_url"):
        try:
            slug = get_show_slug(text)
        except ValueError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

        context.user_data["awaiting_show_url"] = False
        context.user_data["awaiting_start_episode"] = True
        context.user_data["pending_show_slug"] = slug
        await update.message.reply_text(
            "🔢 Enter starting episode number:\n\n"
            "Example: send <b>1</b> to start from the beginning, "
            "or <b>35</b> to resume from Episode 35.",
            parse_mode=ParseMode.HTML,
        )
        return

    if context.user_data.get("awaiting_start_episode"):
        try:
            start_episode = int(text)
            if start_episode < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Please send a valid episode number, for example: 1 or 35."
            )
            return

        slug = context.user_data.get("pending_show_slug")
        if not slug:
            context.user_data["awaiting_start_episode"] = False
            await update.message.reply_text("❌ Show session expired. Use /hb again.")
            return

        context.user_data["awaiting_start_episode"] = False
        context.user_data.pop("pending_show_slug", None)
        uid = update.effective_user.id
        jobs[uid] = {
            "paused": False,
            "stopped": False,
            "start_episode": start_episode,
        }
        asyncio.create_task(process_show(update, uid, slug, start_episode))
        return

    await update.message.reply_text("Use /hb first.")


async def process_show(update: Update, uid: int, slug: str, start_episode: int = 1):
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

        total = len(episodes)
        selected_episodes = []
        for position, episode in enumerate(episodes, start=1):
            ep_no = int(episode.get("index") or position)
            if ep_no >= start_episode:
                selected_episodes.append((position, episode, ep_no))

        if not selected_episodes:
            await status.edit_text(
                f"❌ Episode {start_episode} is outside this show. "
                f"Total episodes: {total}."
            )
            return

        poster = None
        try:
            poster = await asyncio.to_thread(
                download_poster, show.get("poster_url"), workdir
            )
        except Exception:
            logging.exception("Poster download failed")

        # Publish show details before any episode and pin them in the channel.
        show_header = (
            f"🎧 <b>{html.escape(show_name)}</b>\n"
            f"📚 <b>Total Episodes:</b> {total}\n"
            f"▶️ <b>Starting From:</b> Episode {start_episode}\n"
            f"⏳ <b>Status:</b> Download & Upload Started"
        )
        try:
            header_message = await update.get_bot().send_message(
                chat_id=TARGET_CHANNEL,
                text=show_header,
                parse_mode=ParseMode.HTML,
            )
            await update.get_bot().pin_chat_message(
                chat_id=TARGET_CHANNEL,
                message_id=header_message.message_id,
                disable_notification=True,
            )
        except TelegramError as exc:
            logger.warning("Could not send/pin show header: %s", exc)

        await status.edit_text(
            f"🎧 {html.escape(show_name)}\n"
            f"Episodes: {total}\nStarting from Episode {start_episode}…"
        )

        sent = 0
        failed = 0
        selected_total = len(selected_episodes)

        for progress, (position, episode, ep_no) in enumerate(
            selected_episodes, start=1
        ):
            while job["paused"] and not job["stopped"]:
                await asyncio.sleep(1)
            if job["stopped"]:
                break

            ep_name = str(episode.get("title") or f"Episode {ep_no}")

            try:
                await status.edit_text(
                    f"⬇️ Processing {progress}/{selected_total}\n"
                    f"Episode {ep_no}: {ep_name}"
                )
                audio_path = await asyncio.to_thread(
                    download_episode, episode, workdir, poster
                )

                caption = (
                    f"🎙 <b>Episode {ep_no}</b>\n"
                    f"📖 <b>{html.escape(ep_name)}</b>\n\n"
                    f"<blockquote><b>{html.escape(show_name)}</b></blockquote>"
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
                    f"⬆️ Uploaded {sent}/{selected_total}\n"
                    f"Episode {ep_no}: {ep_name}"
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
                f"✅ Completed. Uploaded: {sent}/{selected_total} | Failed: {failed}"
            )
    except Exception as exc:
        logging.exception("Show job failed")
        await status.edit_text(f"❌ Error: {exc}")
    finally:
        job["stopped"] = True
        shutil.rmtree(workdir, ignore_errors=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        # Another getUpdates is running with the same token.
        logger.warning(
            "Polling conflict: another bot instance is using this token. "
            "Stop all other instances (local PC, old Render service, webhook)."
        )
        return
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning("Network issue: %s", err)
        return
    logger.exception("Unhandled error: %s", err)


async def post_init(app: Application):
    # run_webhook/run_polling will configure the correct update transport.
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Welcome and commands"),
            BotCommand("hb", "Start show download/upload"),
            BotCommand("pause", "Pause current job"),
            BotCommand("resume", "Resume paused job"),
            BotCommand("stop", "Stop current job"),
        ]
    )
    logger.info("Bot started. Webhook cleared. Commands registered.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["hb", "HB"], hb))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.add_error_handler(error_handler)

    # Render provides an external HTTPS URL to web services. Use Telegram
    # webhooks there so no long-polling getUpdates process can conflict.
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if render_url:
        port = int(os.getenv("PORT", "10000"))
        webhook_path = f"telegram/{BOT_TOKEN}"
        logger.info("Starting in Render webhook mode on port %s", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=f"{render_url}/{webhook_path}",
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("Starting in local polling mode")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )


if __name__ == "__main__":
    main()
