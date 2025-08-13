import logging
import os
import yt_dlp
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Your Telegram bot token
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# Dictionary to store search results for each user
user_search_results = {}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Send me a song name to search.")

# Search handler
async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text("❌ Please type a song name.")
        return

    await update.message.reply_text("🔍 Searching...")

    # Search using yt-dlp
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
        'default_search': 'ytsearch10'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" not in info:
                await update.message.reply_text("⚠️ No results found.")
                return

            entries = info["entries"][:5]  # top 5 results
            buttons = []
            user_search_results[update.effective_chat.id] = {}

            for idx, video in enumerate(entries):
                title = video.get("title", "Unknown title")
                url = video.get("url")
                user_search_results[update.effective_chat.id][str(idx)] = f"https://youtube.com/watch?v={url}"
                buttons.append([InlineKeyboardButton(title, callback_data=str(idx))])

            await update.message.reply_text(
                "🎶 Select a song:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    except Exception as e:
        logger.error(f"Search error: {e}")
        await update.message.reply_text("⚠️ Search failed. Please try again.")

# Handle song selection
async def song_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_chat.id
    selection = query.data

    if user_id not in user_search_results or selection not in user_search_results[user_id]:
        await query.edit_message_text("❌ Invalid selection.")
        return

    video_url = user_search_results[user_id][selection]
    await query.edit_message_text("⬇️ Downloading song...")

    # Download audio
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

        # Send the song
        await context.bot.send_audio(chat_id=user_id, audio=open(filename, 'rb'), title=info.get("title"))

        # Remove file after sending
        os.remove(filename)

    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text("⚠️ Failed to download song.")

# Main function
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))
    app.add_handler(CallbackQueryHandler(song_selected))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
