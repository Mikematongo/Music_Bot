import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import yt_dlp

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")  # Put your token in environment variable BOT_TOKEN

# Store user search results in memory
search_results = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Send /search <song name> to find a song.")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a song name.\nExample: `/search shape of you`", parse_mode="Markdown")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching for: {query} ...")

    try:
        ydl_opts = {
            'quiet': True,
            'format': 'bestaudio/best',
            'default_search': 'ytsearch5',  # Search top 5 results
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
        
        if "_type" in info and info["_type"] == "playlist":
            entries = info["entries"]
        else:
            entries = [info]

        if not entries:
            await update.message.reply_text("⚠️ No results found.")
            return

        keyboard = []
        search_results[update.effective_chat.id] = entries
        for i, entry in enumerate(entries, start=1):
            keyboard.append([InlineKeyboardButton(f"{i}. {entry['title']}", callback_data=f"select_{i}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎶 Select a song:", reply_markup=reply_markup)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("⚠️ Search failed. Please try again.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("select_"):
        index = int(data.split("_")[1]) - 1
        entries = search_results.get(update.effective_chat.id)

        if not entries or index >= len(entries):
            await query.edit_message_text("⚠️ Song not found in session.")
            return

        song = entries[index]
        url = song["webpage_url"]

        await query.edit_message_text(f"⬇️ Downloading **{song['title']}** ...", parse_mode="Markdown")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

            await query.message.reply_audio(audio=open(file_path, "rb"), title=info['title'])
            os.remove(file_path)  # Remove file after sending

        except Exception as e:
            logging.error(e)
            await query.message.reply_text("⚠️ Failed to download the song.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
