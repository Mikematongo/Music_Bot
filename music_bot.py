import os
import re
import uuid
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp

# ----- Config -----
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RESULTS_LIMIT = 5
MP3_QUALITY = "192"

# Keep search results per user
user_search_results = {}

def safe_name(name: str, max_len=80) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", (name or "song")).strip()[:max_len] or "song"

# ----- YouTube search via yt-dlp -----
def search_youtube(query: str, limit: int = RESULTS_LIMIT):
    ydl_opts = {"quiet": True, "skip_download": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        return result.get("entries", [])

# ----- Handlers -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *Welcome!*\n"
        "Type a song or album name and I'll show matches.\n\n"
        "Then pick a result to download or play.\n\n"
        "You can also search inline: `@{bot} <song>`"
    ).format(bot=context.bot.username)
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return await update.message.reply_text("❌ Please type a song or album name.")
    await show_results(update, query)

async def show_results(update: Update, query: str):
    user_id = update.message.from_user.id
    try:
        hits = search_youtube(query)
    except Exception as e:
        return await update.message.reply_text(f"⚠️ Search failed: {e}")

    if not hits:
        return await update.message.reply_text("⚠️ No matches found. Try a different name.")

    user_search_results[user_id] = hits
    rows = []
    for i, v in enumerate(hits):
        title = v.get("title", "Untitled")
        duration = v.get("duration") or "?"
        video_id = v.get("id")  # Use ID to fix download later
        btn = InlineKeyboardButton(f"{i+1}. {title} ({duration})", callback_data=str(i))
        rows.append([btn])

    await update.message.reply_text("🎶 *Select a match:*", parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(rows))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in user_search_results:
        await query.edit_message_text("⚠️ Session expired. Please search again.")
        return

    song_index = int(query.data)
    song_info = user_search_results[user_id][song_index]

    song_url = song_info.get('url')
    if not song_url.startswith("http"):
        song_url = f"https://www.youtube.com/watch?v={song_info.get('id')}"

    song_title = song_info.get("title", "Unknown Song")
    await query.edit_message_text(f"⬇️ Downloading: {song_title}")

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{safe_name(song_title)}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': MP3_QUALITY,
            }],
            'quiet': True
        }

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([song_url]))

        file_path = f"{safe_name(song_title)}.mp3"
        await context.bot.send_audio(chat_id=user_id, audio=open(file_path, 'rb'), title=song_title)
        os.remove(file_path)

    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ Download error: {e}")

# ----- Run Bot -----
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.run_polling()

if __name__ == "__main__":
    main()
