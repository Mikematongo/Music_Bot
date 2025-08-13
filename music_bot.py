import os, re, shutil, tempfile, uuid
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes, filters
from youtubesearchpython import VideosSearch
import yt_dlp

# ----- Config -----
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()  # Railway environment variable
RESULTS_LIMIT = 8
MP3_QUALITY = "128"

def safe_name(name: str, max_len=80) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", (name or "song")).strip()[:max_len] or "song"

# ----- Handlers -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *Welcome!*\n"
        "Just type a *song or album name* and I'll show matches.\n\n"
        "Then pick a result:\n"
        "• ▶️ *Play/Download MP3* (sent as audio, streamable in Telegram)\n"
        "• 🔗 *Open on YouTube*\n\n"
        "You can also search from anywhere with inline mode:\n"
        "Type `@{bot} <song>` in any chat."
    ).format(bot=context.bot.username)
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return await update.message.reply_text("❌ Please type a song or album name.")
    await show_results(update, query)

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: `/search <song or album>`", parse_mode="Markdown")
    await show_results(update, " ".join(context.args))

async def show_results(update: Update, query: str):
    try:
        hits = VideosSearch(query, limit=RESULTS_LIMIT).result().get("result", [])
    except Exception as e:
        return await update.message.reply_text(f"⚠️ Search error: {e}")

    if not hits:
        return await update.message.reply_text("⚠️ No matches found. Try a different name.")

    rows = []
    for i, v in enumerate(hits, start=1):
        title = v.get("title", "Untitled")
        duration = v.get("duration") or "?"
        link = v.get("link")
        btn = InlineKeyboardButton(f"{i}. {title} ({duration})", callback_data=f"pick|{link}")
        rows.append([btn])

    await update.message.reply_text("🎶 *Select a match:*", parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(rows))

async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    url = q.data.split("|", 1)[1]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Play / Download MP3", callback_data=f"dl|{url}")],
        [InlineKeyboardButton("🔗 Open on YouTube", url=url)],
        [InlineKeyboardButton("🔎 Search again", callback_data="again|_")]
    ])
    await q.edit_message_text("What would you like to do?", reply_markup=kb)

async def on_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    url = q.data.split("|", 1)[1]
    await q.edit_message_text("⬇️ Downloading and tagging… please wait.")
    await download_and_send(context, q.message.chat_id, url)

async def on_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🔎 Type a song or album name…")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qtext = (update.inline_query.query or "").strip()
    if not qtext:
        return
    try:
        hits = VideosSearch(qtext, limit=RESULTS_LIMIT).result().get("result", [])
    except Exception:
        hits = []

    results = []
    for v in hits:
        title = v.get("title", "Untitled")
        duration = v.get("duration") or "?"
        link = v.get("link")
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=title,
                description=f"{duration} • tap to choose action",
                input_message_content=InputTextMessageContent(f"/get {link}")
            )
        )
    await update.inline_query.answer(results, cache_time=0)

async def get_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: `/get <YouTube link>`", parse_mode="Markdown")
    url = context.args[0]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Play / Download MP3", callback_data=f"dl|{url}")],
        [InlineKeyboardButton("🔗 Open on YouTube", url=url)],
    ])
    await update.message.reply_text("Choose an action:", reply_markup=kb)

async def download_and_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(tmp / "%(title).80s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "writethumbnail": True,
            "prefer_ffmpeg": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": MP3_QUALITY},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            return await context.bot.send_message(chat_id, f"⚠️ Download error: {e}")

        title = info.get("title", "Unknown Song")
        artist = info.get("artist") or info.get("uploader") or info.get("channel") or ""
        mp3_candidates = list(tmp.glob("*.mp3"))
        if not mp3_candidates:
            return await context.bot.send_message(chat_id, "⚠️ No MP3 produced.")

        src = mp3_candidates[0]
        nice = safe_name(f"{artist} - {title}" if artist else title) + ".mp3"
        final_path = tmp / nice
        try:
            shutil.move(str(src), str(final_path))
        except Exception:
            final_path = src

        caption = f"🎧 {title}" + (f"\n👤 {artist}" if artist else "")
        try:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=final_path.open("rb"),
                title=title[:128],
                performer=artist[:128] if artist else None,
                caption=caption,
            )
        except Exception as e:
            await context.bot.send_message(chat_id, f"⚠️ Send error: {e}")

# ----- Run Bot -----
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set!")

    # --- Clear webhook to prevent polling conflict ---
    bot = Bot(BOT_TOKEN)
    bot.delete_webhook()
    print("Webhook cleared. Bot ready for polling.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("get", get_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^pick\|"))
    app.add_handler(CallbackQueryHandler(on_download, pattern=r"^dl\|"))
    app.add_handler(CallbackQueryHandler(on_again, pattern=r"^again\|"))
    app.add_handler(InlineQueryHandler(inline_query))

    # Polling (works 24/7 on Railway)
    app.run_polling()

if __name__ == "__main__":
    main()
