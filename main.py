import os
import time
import zipfile
import threading
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot
from telebot import types, apihelper
from flask import Flask

# --- نظام البقاء حياً (Keep Alive) لـ Render ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running!"

def run_web():
    # Render يستخدم المنفذ 10000 افتراضياً أو يحدده في البيئة
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- إعدادات البوت ---
apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 120

API_TOKEN = '8697260442:AAHU_c1EidIplaIOZvYkevDWqgl7gUXjwdM'
bot = telebot.TeleBot(API_TOKEN, threaded=True)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://3asq.org/'
})

# --- وظيفة البحث ---
def search_manga(query):
    try:
        url = f"https://3asq.org/?s={query.replace(' ', '+')}&post_type=wp-manga"
        req = session.get(url, timeout=20)
        soup = BeautifulSoup(req.content, 'html.parser')
        item = soup.find('div', class_='c-tabs-item__content')
        if not item: return None
        return {"title": item.find('h3').text.strip(), "url": item.find('a')['href'], "img": item.find('img')['src']}
    except: return None

# --- وظيفة التحميل ---
def process_download(manga_url, manga_title, chat_id, msg_id, start_ch, end_ch):
    try:
        bot.edit_message_text("🔄 جاري التجهيز السحابي...", chat_id, msg_id)
        ajax_url = manga_url.rstrip('/') + '/ajax/chapters/'
        soup = BeautifulSoup(session.post(ajax_url, timeout=30).content, 'html.parser')
        all_ch = soup.find_all('li', class_='wp-manga-chapter')[::-1]
        target = all_ch[start_ch-1 : min(end_ch, len(all_ch))]
        
        imgs_links = []
        for ch in target:
            ch_url = ch.find('a')['href']
            ch_soup = BeautifulSoup(session.get(ch_url, timeout=30).content, 'html.parser')
            for img in ch_soup.find_all('div', class_='page-break'):
                src = img.find('img').get('data-src') or img.find('img').get('src')
                if src: imgs_links.append(src.strip())

        zip_name = f"manga_{int(time.time())}.zip"
        with zipfile.ZipFile(zip_name, 'w') as z:
            with ThreadPoolExecutor(max_workers=15) as ex:
                def d(u, i):
                    try: return i, session.get(u, timeout=25).content
                    except: return i, None
                futures = [ex.submit(d, u, i) for i, u in enumerate(imgs_links)]
                for f in as_completed(futures):
                    idx, data = f.result()
                    if data: z.writestr(f"img_{idx}.jpg", data)

        bot.edit_message_text("📤 جاري الرفع لتليجرام...", chat_id, msg_id)
        with open(zip_name, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"📦 {manga_title}")
        os.remove(zip_name)
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {str(e)}")

# --- الأوامر ---
@bot.message_handler(commands=['start'])
def st(message): bot.reply_to(message, "🚀 بوت المانجا شغال الآن على Render مجاناً!")

@bot.message_handler(func=lambda m: True)
def h(message):
    data = search_manga(message.text)
    if data:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔢 تحميل", callback_data=f"dl_{data['url']}"))
        bot.send_photo(message.chat.id, data['img'], caption=f"الاسم: {data['title']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('dl_'))
def cl(call):
    url = call.data.replace('dl_', '')
    msg = bot.send_message(call.message.chat.id, "اكتب رقم الفصل:")
    bot.register_next_step_handler(msg, lambda m: threading.Thread(target=process_download, args=(url, "Manga", m.chat.id, bot.send_message(m.chat.id, "⏳").message_id, int(m.text), int(m.text))).start())

# --- التشغيل ---
if __name__ == "__main__":
    # تشغيل خادم الويب الصغير في خيط منفصل
    threading.Thread(target=run_web, daemon=True).start()
    
    # تشغيل البوت
    while True:
        try:
            print("🟢 البوت يحاول الاتصال...")
            bot.polling(none_stop=True, interval=0, timeout=120)
        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            time.sleep(10)
