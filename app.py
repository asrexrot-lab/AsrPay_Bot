import os
import requests
from flask import Flask, request

app = Flask(__name__)

# টেলিগ্রাম বোট টোকেন
TELEGRAM_BOT_TOKEN = "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U"

def send_telegram(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Error sending msg: {e}")
        return False

@app.route('/')
def home():
    return "AsrPay Bot Server is Active!", 200

@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    update = request.get_json(silent=True) or {}
    
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text.startswith("/start"):
            send_telegram(chat_id, "🤖 *Welcome to AsrPay Bot!*\n\n/getnumber দিয়ে ফ্রী নম্বর নিন।")

        elif text == "/getnumber":
            menu = {
                "inline_keyboard": [
                    [{"text": "🎵 TikTok", "callback_data": "get_tiktok"}, {"text": "🍏 Apple", "callback_data": "get_apple"}],
                    [{"text": "💬 WhatsApp", "callback_data": "get_whatsapp"}, {"text": "✈️ Telegram", "callback_data": "get_telegram"}],
                    [{"text": "📘 Facebook", "callback_data": "get_facebook"}, {"text": "🌐 Other", "callback_data": "get_other"}]
                ]
            }
            send_telegram(chat_id, "📱 *AsrPay - সার্ভিস সিলেক্ট করুন:*", reply_markup=menu)

        elif text == "/balance":
            send_telegram(chat_id, "💳 *AsrPay Balance:* $0.00")

    elif "callback_query" in update:
        callback = update["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        service = callback["data"].replace("get_", "").upper()
        send_telegram(chat_id, f"✅ Selected: *{service}*\n\nআপনার জন্য নম্বর প্রসেস করা হচ্ছে...")

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
