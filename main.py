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

if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أرسل لي أي مقطع فيديو أو مقطع صوتي وسأقوم باستخراج النص منه أو ترجمته 🎥🎤")

# 1. دالة استلام الفيديو/الصوت وعرض الأزرار
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حفظ معلومات الملف لاستخدامها لاحقاً
    if update.message.video:
        file_id = update.message.video.file_id
    elif update.message.audio or update.message.voice:
        file_id = (update.message.audio or update.message.voice).file_id
    else:
        return

    # حفظ معرّف الملف في ذاكرة البوت المؤقتة
    context.user_data['current_file_id'] = file_id

    # إنشاء الأزرار
    keyboard = [
        [
            InlineKeyboardButton("استخراج النص فقط 📝", callback_data="extract_text"),
            InlineKeyboardButton("ترجمة الفيديو 🌍", callback_data="translate_video")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "تم استلام المقطع بنجاح! ماذا تريد أن أفعل به؟",
        reply_markup=reply_markup
    )

# 2. دالة الاستجابة لضغطات الأزرار
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # لإخفاء علامة التحميل من الزر
    
    choice = query.data
    file_id = context.user_data.get('current_file_id')

    if not file_id:
        await query.edit_message_text(text="عذراً، انتهت صلاحية الملف. أرسل المقطع مجدداً.")
        return

    if choice == "extract_text":
        await query.edit_message_text(text="⏳ جاري استخراج النص الأصلي من المقطع... (هذه العملية قد تستغرق بضع ثوانٍ)")
        
        # --- هنا تضع كود تحميل الفيديو واستخدام Groq Whisper لاستخراج النص ---
        # (انظر الملاحظة بالأسفل لكيفية ربطها)
        
        await context.bot.send_message(chat_id=update.effective_chat.id, text="[سيظهر النص المستخرج هنا]")

    elif choice == "translate_video":
        await query.edit_message_text(text="🌍 جاري ترجمة المقطع... (هذه العملية قد تستغرق بضع ثوانٍ)")
        
        # --- هنا تضع كود تحميل الفيديو واستخدام Groq Whisper للترجمة ---
        
        await context.bot.send_message(chat_id=update.effective_chat.id, text="[ستظهر الترجمة هنا]")

def main():
    if not TELEGRAM_TOKEN:
        logger.error("تأكد من إضافة TELEGRAM_TOKEN")
        return
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # أوامر البوت
    app.add_handler(CommandHandler("start", start))
    
    # استقبال الفيديو والصوتيات
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE, handle_media))
    
    # استقبال ضغطات الأزرار
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("تم تشغيل بوت الترجمة بنجاح...")
    # إذا كنت تستخدم Render، استخدم run_webhook بدلاً من polling
    app.run_polling()

if __name__ == "__main__":
    main()
