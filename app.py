import os
import hmac
import hashlib
import requests
from flask import Flask, request

app = Flask(__name__)

# টেলিগ্রাম মেসেজ পাঠানোর ফাংশন (একই ফাইলে রয়েছে)
def send_telegram(text):
    token = os.getenv('TG_TOKEN')
    chat = os.getenv('TG_CHAT')
    if not token or not chat: 
        print("Error: TG_TOKEN or TG_CHAT environment variable is missing!")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat, 
        'text': text[:4093], 
        'disable_web_page_preview': True
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

@app.route('/')
def home():
    return "🚀 AsrPay Notifier Server is Running Successfully!", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    raw_data = request.get_data()
    signature = request.headers.get('X-KSIIPRNTECHNOLOGY-Signature', '')
    secret = os.getenv('PANEL_WEBHOOK_SECRET', '')

    # সিগনেচার ভেরিফিকেশন
    if secret:
        expected_sig = 'sha256=' + hmac.new(secret.encode(), raw_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return "Unauthorized", 401

    event = request.get_json(silent=True) or {}
    
    # যখনই নতুন কোনো এসএমএস বা ওটিপি আসবে
    if event.get('event') == 'message.received':
        d = event.get('data', {})
        number = d.get('number')
        source = d.get('source')
        message = d.get('message')
        
        # টেলিগ্রামে নোটিফিকেশন পাঠানো
        msg_text = f"SMS on {number}\nFrom: {source}\n\n{message}"
        send_telegram(msg_text)

    return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
