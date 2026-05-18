import os
import re
import sys
import time
import datetime
import requests
from threading import Thread
from flask import Flask
import telebot

# --- إعداد خادم الويب الوهمي لإبقاء السيرفر حياً ---
app = Flask('')

@app.route('/')
def home():
    return "🚀 البوت يعمل بنجاح 24/7!"

def run_web_server():
    # السيرفر سيعمل على بورت 8080 وهو المطلوب لمنصة Render
    app.run(host='0.0.0.0', port=8080)

# --- إعدادات البوت والـ APIs ---
TELEGRAM_BOT_TOKEN = "ضع_توكن_تليجرام_هنا"
GROQ_API_KEY = "ضع_مفتاح_Groq_هنا"
TRANSLATION_MODEL = "llama-3.1-8b-instant" 

AUDIO_CHUNKS_DIR = "audio_chunks"
FINAL_SRT_PATH = "translated_movie.srt"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- الدوال المساعدة للتفريغ والترجمة (نفس كودك الناجح) ---

def format_whisper_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def json_segments_to_srt(segments):
    srt_text = ""
    for i, seg in enumerate(segments):
        start_str = format_whisper_time(seg['start'])
        end_str = format_whisper_time(seg['end'])
        text = seg['text'].strip()
        srt_text += f"{i+1}\n{start_str} --> {end_str}\n{text}\n\n"
    return srt_text

def extract_and_chunk_audio_from_stream(video_url, chunk_length_seconds=600):
    if os.path.exists(AUDIO_CHUNKS_DIR): os.system(f"rm -rf {AUDIO_CHUNKS_DIR}")
    os.makedirs(AUDIO_CHUNKS_DIR, exist_ok=True)
    ffmpeg_stream_options = "-reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    command = f'ffmpeg {ffmpeg_stream_options} -i "{video_url}" -vn -acodec libmp3lame -ac 1 -ab 24k -f segment -segment_time {chunk_length_seconds} "{AUDIO_CHUNKS_DIR}/chunk_%03d.mp3" -y'
    exit_code = os.system(command)
    if exit_code != 0: return []
    return sorted([os.path.join(AUDIO_CHUNKS_DIR, f) for f in os.listdir(AUDIO_CHUNKS_DIR) if f.endswith('.mp3')])

def shift_srt_timestamps(srt_text, shift_seconds):
    if shift_seconds == 0: return srt_text
    def shift_match(match):
        h, m, s, ms = map(int, match.groups())
        td = datetime.timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms) + datetime.timedelta(seconds=shift_seconds)
        total_sec = int(td.total_seconds())
        return f"{total_sec // 3600:02d}:{(total_sec % 3600) // 60:02d}:{total_sec % 60:02d},{int(td.microseconds / 1000):03d}"
    return re.sub(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", shift_match, srt_text)

def transcribe_audio_chunk(chunk_path):
    audio_url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with open(chunk_path, "rb") as f:
                files = {"file": f}
                data = {"model": "whisper-large-v3", "response_format": "verbose_json"}
                response = requests.post(audio_url, headers=headers, files=files, data=data)
            if response.status_code == 200:
                return json_segments_to_srt(response.json().get('segments', []))
            elif response.status_code == 429:
                time.sleep(15)
                continue
        except:
            time.sleep(5)
    return ""

def translate_srt_with_groq(srt_content):
    if not srt_content.strip(): return ""
    url = "https://api.openai.com/v1/chat/completions" # صيغة متوافقة مع جروق
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Translate the following SRT subtitle text into professional movie Arabic. Keep timestamps unchanged. Return ONLY SRT:\n\n{srt_content}"
    payload = {"model": TRANSLATION_MODEL, "messages": [{"role": "user", "content": prompt}]}
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            elif response.status_code == 429:
                time.sleep(15)
                continue
        except:
            time.sleep(5)
    return srt_content

# --- استقبال رسائل تليجرام ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🎬 **أهلاً بك!** أرسل رابط الفيلم المباشر (.mp4 أو .m3u8) وسأتولى ترجمته فوراً مجاناً!")

@bot.message_handler(func=lambda message: True)
def handle_movie_request(message):
    video_url = message.text.strip()
    if not (video_url.startswith("http://") or video_url.startswith("https://")):
        bot.reply_to(message, "⚠️ من فضلك أرسل رابطاً صحيحاً.")
        return
        
    status_msg = bot.reply_to(message, "⏳ جاري الاتصال بالبث وفصل الصوت وتفكيك الفيلم...")
    chunk_length = 600
    audio_chunks = extract_and_chunk_audio_from_stream(video_url, chunk_length)
    
    if not audio_chunks:
        bot.edit_message_text("❌ فشل الاتصال بالرابط.", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
        
    complete_translated_srt = ""
    total = len(audio_chunks)
    
    for index, chunk in enumerate(audio_chunks):
        bot.edit_message_text(f"⚡ جاري معالجة الجزء [{index + 1}/{total}]...", chat_id=message.chat.id, message_id=status_msg.message_id)
        srt_chunk = transcribe_audio_chunk(chunk)
        if srt_chunk.strip():
            shift_seconds = index * chunk_length
            corrected_srt = shift_srt_timestamps(srt_chunk, shift_seconds)
            translated_chunk = translate_srt_with_groq(corrected_srt)
            complete_translated_srt += translated_chunk + "\n\n"
            time.sleep(2)
            
    with open(FINAL_SRT_PATH, "w", encoding="utf-8") as f:
        f.write(complete_translated_srt.strip())
        
    bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
    with open(FINAL_SRT_PATH, "rb") as f:
        bot.send_document(message.chat.id, f, caption="🎯 مبروك! انتهت ترجمة فيلمك بنجاح.")
        
    for chunk in audio_chunks:
        if os.path.exists(chunk): os.remove(chunk)
    if os.path.exists(FINAL_SRT_PATH): os.remove(FINAL_SRT_PATH)

# --- تشغيل المنظومة المزدوجة ---
if __name__ == "__main__":
    # 1. تشغيل سيرفر الويب في خلفية منفصلة لRender
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    # 2. تشغيل البوت الأساسي لاستقبال رسائل تليجرام
    print("🚀 البوت والسيرفر نشطان الآن...")
    bot.infinity_polling()
