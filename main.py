import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq

# --- إعداد سجلات الأخطاء ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إعدادات البيئة ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")

# --- إعداد عميل Groq ---
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

os.makedirs("downloads", exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في بوت الاستخراج والترجمة! 🎤🎥\nأرسل لي أي مقطع فيديو أو بصمة صوتية وسأقوم بالواجب.")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.video:
        file_obj = update.message.video
        file_ext = ".mp4"
    elif update.message.audio:
        file_obj = update.message.audio
        file_ext = ".mp3"
    elif update.message.voice:
        file_obj = update.message.voice
        file_ext = ".ogg"
    else:
        return

    if file_obj.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("عذراً، حجم المقطع أكبر من 20 ميجابايت.")
        return

    context.user_data['file_id'] = file_obj.file_id
    context.user_data['file_ext'] = file_ext

    keyboard = [
        [InlineKeyboardButton("📝 استخراج النص", callback_data="extract_text")],
        [InlineKeyboardButton("🌍 ترجمة المقطع", callback_data="translate_video")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("تم استلام المقطع بنجاح! 🎬\nاختر ماذا تريد أن أفعل:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    file_id = context.user_data.get('file_id')
    file_ext = context.user_data.get('file_ext')

    if not file_id:
        await query.edit_message_text(text="عذراً، انتهت صلاحية المقطع. أرسله مجدداً.")
        return

    status_msg = await query.edit_message_text(text="⏳ جاري تحميل المقطع من تيليجرام...")

    try:
        new_file = await context.bot.get_file(file_id)
        file_path = f"downloads/{file_id}{file_ext}"
        await new_file.download_to_drive(file_path)

        await status_msg.edit_text("🎧 جاري الاستماع للمقطع واستخراج النص...")
        
        with open(file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="json"
            )
        
        extracted_text = transcription.text

        if not extracted_text.strip():
            await status_msg.edit_text("لم أتمكن من سماع أي كلام واضح في هذا المقطع.")
            os.remove(file_path)
            return

        if choice == "extract_text":
            await status_msg.edit_text(f"**النص المستخرج:**\n\n{extracted_text}", parse_mode='Markdown')
        elif choice == "translate_video":
            await status_msg.edit_text("🌍 جاري ترجمة النص إلى العربية باحترافية...")
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "أنت مترجم محترف. قم بترجمة النص التالي إلى اللغة العربية الفصحى بدقة واحترافية. أرسل الترجمة فقط دون أي إضافات."},
                    {"role": "user", "content": extracted_text}
                ],
                model="llama-3.3-70b-versatile",
            )
            translated_text = chat_completion.choices[0].message.content
            final_message = f"**النص الأصلي:**\n{extracted_text}\n\n---\n\n**الترجمة العربية:**\n{translated_text}"
            await status_msg.edit_text(final_message, parse_mode='Markdown')

        os.remove(file_path)

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"حدث خطأ أثناء المعالجة. تأكد من أن المقطع يحتوي على صوت واضح.")
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        logger.error("خطأ: مفاتيح مفقودة!")
        return
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE, handle_media))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # تشغيل البوت بنظام Webhook ليتوافق مع منصة Render
    if RENDER_URL:
        logger.info(f"جاري تشغيل Webhook على الرابط: {RENDER_URL}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=RENDER_URL)
    else:
        logger.info("لم يتم العثور على رابط Render، سيتم تشغيل Polling.")
        app.run_polling()

if __name__ == "__main__":
    main()

