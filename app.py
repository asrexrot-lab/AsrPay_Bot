import os
import hmac
import hashlib
from flask import Flask, request
from lib import send_telegram

app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 AsrPay Notifier Server is Running!", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    # অত্যন্ত গুরুত্বপূর্ণ: পার্স করা অবজেক্ট নয়, একদম র মেটেরিয়াল বাইট নিতে হবে
    raw_data = request.get_data()
    signature = request.headers.get('X-KSIIPRNTECHNOLOGY-Signature', '')
    secret = os.getenv('PANEL_WEBHOOK_SECRET', '')

    # ১. সিগনেচার চেক করা (ভুল হলে 401 রিটার্ন করে স্টপ করে দেওয়া)
    if secret:
        expected_sig = 'sha256=' + hmac.new(secret.encode(), raw_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return "Unauthorized", 401

    # ২. ইভেন্ট ডাটা রিড করা
    event = request.get_json(silent=True) or {}
    event_type = event.get('event')

    # ৩. শুধুমাত্র message.received ইভেন্ট হ্যান্ডেল করা
    if event_type == 'message.received':
        d = event.get('data', {})
        number = d.get('number')
        source = d.get('source')
        message = d.get('message')

        # টেলিগ্রামে নোটিফিকেশন পাঠানো
        msg_text = f"SMS on {number}\nFrom: {source}\n\n{message}"
        send_telegram(msg_text)

    # ৪. নিয়ম অনুযায়ী ৫ সেকেন্ডের মধ্যে 200 OK রেসপন্স দেওয়া
    return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
