import os
import hmac
import hashlib
import requests
from flask import Flask, request, render_template_string
from datetime import datetime, timezone
from supabase import create_client, Client

app = Flask(__name__)

# Supabase & Telegram Config
SUPABASE_URL = "https://mfrmudgpjjonycdrvlhe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcm11ZGdwampvbnljZHJ2bGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY4NzI4NDksImV4cCI6MjEwMjQ0ODg0OX0.gjsVOT0TKdiHJVcEkp5SuJklq65XQVQKzjQ0SmS5l2Q"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U")
WEBHOOK_SECRET = os.getenv("PANEL_WEBHOOK_SECRET", "")
OTP_GROUP_ID = os.getenv("OTP_GROUP_ID", "")
ADMIN_CHAT_ID = "8745487398"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_telegram(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

@app.route('/')
def home():
    return "🚀 AsrPay OTP Automation Server is Running!", 200

# ------------------- 1. WEBHOOK (KSI IPRN SMS RECEIVED) -------------------
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    raw_data = request.get_data()
    signature = request.headers.get('X-KSIIPRNTECHNOLOGY-Signature', '')
    
    if WEBHOOK_SECRET:
        expected_sig = 'sha256=' + hmac.new(WEBHOOK_SECRET.encode(), raw_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return "Unauthorized", 401

    event = request.get_json(silent=True) or {}
    if event.get('event') == 'message.received':
        d = event.get('data', {})
        number = d.get('number')
        source = d.get('source')
        message_text = d.get('message')

        # ডাটাবেজ চেক করা কোন ইউজার এই নম্বরটি নিয়েছিল
        try:
            num_res = supabase.from_('numbers_assigned').select('*').eq('phone_number', number).eq('status', 'active').execute()
            if num_res and num_res.data:
                info = num_res.data[0]
                chat_id = info.get('chat_id')
                rate = float(info.get('rate', 0.05))

                # ইউজারের ব্যালেন্স আপডেট করা
                user_res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                if user_res and user_res.data:
                    curr_bal = float(user_res.data[0].get('balance', 0.0))
                    new_bal = curr_bal + rate
                    supabase.from_('users').update({'balance': new_bal}).eq('chat_id', chat_id).execute()

                    # ইউজারের ইনবক্সে ওটিপি পাঠানো
                    msg = f"📩 *New OTP Received!*\n\n📱 Number: `{number}`\n🌐 Service: `{source}`\n💬 Message: `{message_text}`\n\n💵 Earned: `+${rate:.2f}`"
                    send_telegram(chat_id, msg)

                    # নম্বরটি ইউজ হয়ে গেছে তাই ইনঅ্যাক্টিভ করা
                    supabase.from_('numbers_assigned').update({'status': 'used'}).eq('phone_number', number).execute()

                    # গ্রুপে নোটিশ পাঠানো (যদি থাকে)
                    if OTP_GROUP_ID:
                        group_msg = f"🔥 *OTP Delivered*\n📱 Number: `{number[:-4]}****`\n🌐 Service: {source}\n💬 SMS: {message_text}"
                        send_telegram(OTP_GROUP_ID, group_msg)
        except Exception as e:
            print(f"Webhook DB error: {e}")

    return "ok", 200

# ------------------- 2. TELEGRAM BOT HANDLER -------------------
@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    update = request.get_json(silent=True) or {}
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text.startswith("/start"):
            send_telegram(chat_id, "✨ *Welcome to AsrPay OTP Bot!*\n\nসার্ভিস পেতে নিচের মেনু ব্যবহার করুন:")
        
        elif text.startswith("/admin"):
            if str(chat_id) == str(ADMIN_CHAT_ID):
                admin_kb = {
                    "inline_keyboard": [
                        [{"text": "🌐 Open Web Admin Panel", "url": request.host_url + "admin"}],
                        [{"text": "📢 Broadcast Notice", "callback_data": "admin_notice"}]
                    ]
                }
                send_telegram(chat_id, "👑 *Admin Control Panel*\n\nকমপ্লিট ম্যানেজমেন্টের জন্য নিচের ওয়েব প্যানেলটি ব্যবহার করুন:", reply_markup=admin_kb)
            else:
                send_telegram(chat_id, "❌ আপনার এই কমান্ড ব্যবহারের অনুমতি নেই!")

    return "ok", 200

# ------------------- 3. WEB ADMIN PANEL (MOBILE FRIENDLY) -------------------
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AsrPay Master Admin</title>
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: sans-serif; margin: 0; padding: 15px; }
        .card { background: #1e293b; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #334155; }
        h2, h3 { color: #38bdf8; margin-top: 0; }
        input, select { width: 100%; padding: 10px; margin: 5px 0 12px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 6px; }
        .btn { background: #0284c7; color: white; border: none; padding: 10px; width: 100%; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .btn-danger { background: #ef4444; }
    </style>
</head>
<body>
    <h2>👑 AsrPay Admin Dashboard</h2>
    
    <div class="card">
        <h3>➕ Add / Manage Section (Category)</h3>
        <form action="/admin/add-section" method="POST">
            <input type="text" name="section_name" placeholder="Section Name (e.g. TikTok, Facebook)" required>
            <button class="btn">Add Section</button>
        </form>
    </div>

    <div class="card">
        <h3>🌍 Add Country & Rate</h3>
        <form action="/admin/add-country" method="POST">
            <input type="text" name="section_name" placeholder="Section Name (e.g. TikTok)" required>
            <input type="text" name="country_name" placeholder="Country Name (e.g. USA, UK)" required>
            <input type="number" step="0.01" name="rate" placeholder="Rate (USD per SMS)" required>
            <button class="btn">Save Country & Rate</button>
        </form>
    </div>

    <div class="card">
        <h3>📢 Send Notice to Bot / Group</h3>
        <form action="/admin/broadcast" method="POST">
            <input type="text" name="notice_text" placeholder="Notice Message..." required>
            <button class="btn">Broadcast Notice</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/admin')
def admin_dashboard():
    return render_template_string(ADMIN_HTML)

@app.route('/admin/broadcast', methods=['POST'])
def broadcast_notice():
    notice = request.form.get('notice_text', '')
    if OTP_GROUP_ID:
        send_telegram(OTP_GROUP_ID, f"📢 *Official Notice*\n\n{notice}")
    return "Notice Sent! <br><a href='/admin'>Go Back</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
