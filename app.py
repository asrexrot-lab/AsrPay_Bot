import os
import hmac
import hashlib
import requests
from datetime import datetime, timezone
from flask import Flask, request, render_template_string
from supabase import create_client, Client

app = Flask(__name__)

# Credentials Directly Set
SUPABASE_URL = "https://mfrmudgpjjonycdrvlhe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcm11ZGdwampvbnljZHJ2bGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY4NzI4NDksImV4cCI6MjEwMjQ0ODg0OX0.gjsVOT0TKdiHJVcEkp5SuJklq65XQVQKzjQ0SmS5l2Q"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U")
WEBHOOK_SECRET = os.getenv("PANEL_WEBHOOK_SECRET", "")

OTP_GROUP_ID = os.getenv("OTP_GROUP_ID", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

EARNING_PER_SMS = 0.05
REFERRAL_BONUS_BDT = 3.00
NUMBER_TIMEOUT_MINUTES = 5

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

def check_service_status():
    try:
        res = supabase.table('settings').select('value').eq('key', 'service_status').execute()
        if res.data:
            return res.data[0]['value'] == 'ON'
    except Exception as e:
        print(f"Supabase check error: {e}")
    return True

@app.route('/')
def home():
    return "AsrPay Master Server & Admin Panel Running!", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    raw_data = request.get_data()
    signature = request.headers.get('X-KSIIPRNTECHNOLOGY-Signature', '')
    
    if WEBHOOK_SECRET:
        expected_sig = 'sha256=' + hmac.new(WEBHOOK_SECRET.encode(), raw_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return "Unauthorized", 401

    data = request.get_json(silent=True) or {}
    if data.get('event') == 'message.received':
        sms_data = data.get('data', {})
        number = sms_data.get('number')
        message_text = sms_data.get('message')
        source = sms_data.get('source', 'Unknown')

        num_query = supabase.table('numbers').select('chat_id, assigned_at').eq('phone_number', number).execute()
        
        if num_query.data:
            num_info = num_query.data[0]
            chat_id = num_info['chat_id']
            assigned_at_str = num_info.get('assigned_at')

            is_expired = False
            if assigned_at_str:
                assigned_at = datetime.fromisoformat(assigned_at_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                elapsed_minutes = (now - assigned_at).total_seconds() / 60
                if elapsed_minutes > NUMBER_TIMEOUT_MINUTES:
                    is_expired = True

            msg_status = "delivered"
            if not is_expired and chat_id:
                user_res = supabase.table('users').select('balance, referred_by, pending_usd').eq('chat_id', chat_id).execute()
                if user_res.data:
                    curr_bal = float(user_res.data[0]['balance'])
                    referred_by = user_res.data[0].get('referred_by')
                    pending_usd = float(user_res.data[0].get('pending_usd') or 0.0)

                    new_bal = curr_bal + EARNING_PER_SMS
                    pending_usd += EARNING_PER_SMS

                    if referred_by and pending_usd >= 1.00:
                        ref_user = supabase.table('users').select('balance').eq('chat_id', referred_by).execute()
                        if ref_user.data:
                            ref_bal = float(ref_user.data[0]['balance'])
                            supabase.table('users').update({'balance': ref_bal + REFERRAL_BONUS_BDT}).eq('chat_id', referred_by).execute()
                            send_telegram(referred_by, f"🎉 *AsrPay Referral Bonus!* Your referred user earned $1. You received {REFERRAL_BONUS_BDT} BDT bonus!")
                        pending_usd -= 1.00

                    supabase.table('users').update({
                        'balance': new_bal,
                        'pending_usd': pending_usd
                    }).eq('chat_id', chat_id).execute()

                    msg_text = (
                        f"📩 *[AsrPay Bot] New OTP Received!*\n"
                        f"📱 *Number:* `{number}`\n"
                        f"🌐 *Service:* {source}\n"
                        f"💬 *Message:* `{message_text}`\n\n"
                        f"💵 *Earned:* +${EARNING_PER_SMS:.2f}"
                    )
                    sent = send_telegram(chat_id, msg_text)
                    if not sent:
                        msg_status = "failed_to_send_bot"
            else:
                msg_status = "expired_timeout"

            supabase.table('otp_logs').insert({
                'chat_id': chat_id,
                'phone_number': number,
                'service': source,
                'otp_message': message_text,
                'status': msg_status
            }).execute()

            if OTP_GROUP_ID:
                group_msg = f"🔥 *[AsrPay] NEW OTP ARRIVED*\n📱 *Number:* `{number[:-4]}****`\n🌐 *Service:* {source}\n💬 *SMS:* {message_text}"
                send_telegram(OTP_GROUP_ID, group_msg)

    return "OK", 200

@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    update = request.get_json(silent=True) or {}
    
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text.startswith("/start"):
            args = text.split()
            referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
            
            res = supabase.table('users').select('chat_id').eq('chat_id', chat_id).execute()
            if not res.data:
                supabase.table('users').insert({
                    'chat_id': chat_id,
                    'balance': 0.00,
                    'referred_by': referrer_id if referrer_id != chat_id else None
                }).execute()
            
            # কীবোর্ডের নিচে স্থায়ী রেগুলার বাটন
            main_keyboard = {
                "keyboard": [
                    [{"text": "📱 Get Number"}, {"text": "💳 Balance"}]
                ],
                "resize_keyboard": True
            }
            send_telegram(chat_id, "🤖 *Welcome to AsrPay Bot!*\n\nনিচের বাটন থেকে অপশন সিলেক্ট করুন:", reply_markup=main_keyboard)

        elif text in ["📱 Get Number", "/getnumber"]:
            if not check_service_status():
                send_telegram(chat_id, "⚠️ *দুঃখিত! বর্তমানে নম্বর প্রোভাইড করার সার্ভিস সাময়িকভাবে বন্ধ আছে। কিছু সময় পর চেষ্টা করুন।")
                return "OK", 200

            menu = {
                "inline_keyboard": [
                    [{"text": "🎵 TikTok", "callback_data": "get_tiktok"}, {"text": "🍏 Apple", "callback_data": "get_apple"}],
                    [{"text": "💬 WhatsApp", "callback_data": "get_whatsapp"}, {"text": "✈️ Telegram", "callback_data": "get_telegram"}],
                    [{"text": "📘 Facebook", "callback_data": "get_facebook"}, {"text": "🌐 Other", "callback_data": "get_other"}]
                ]
            }
            send_telegram(chat_id, "📱 *AsrPay - সার্ভিস সিলেক্ট করুন:*", reply_markup=menu)

        elif text in ["💳 Balance", "/balance"]:
            res = supabase.table('users').select('balance').eq('chat_id', chat_id).execute()
            bal = res.data[0]['balance'] if res.data else 0.00
            send_telegram(chat_id, f"💳 *AsrPay Balance:* ${bal:.2f}")

    elif "callback_query" in update:
        callback = update["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        
        if not check_service_status():
            send_telegram(chat_id, "⚠️ *বর্তমানে নম্বর সার্ভিস বন্ধ রয়েছে!*")
            return "OK", 200

        service = callback["data"].replace("get_", "").upper()
        send_telegram(chat_id, f"✅ Selected: *{service}*\n\nআপনার জন্য নম্বর প্রসেস করা হচ্ছে...")

    return "OK", 200

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AsrPay Control Center</title>
    <style>
        body { font-family: Arial, sans-serif; background: #eef2f5; margin: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .btn-on { background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
        .btn-off { background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
        input, select { width: 95%; padding: 8px; margin: 8px 0; border: 1px solid #ccc; border-radius: 4px; }
        button { background: #007bff; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h2>🚀 AsrPay Master Control Panel</h2>

    <div class="card">
        <h3>🔴 / 🟢 Number Service Status</h3>
        <p>Current Status: <strong>{{ status }}</strong></p>
        {% if status == 'ON' %}
            <a href="/admin/toggle-service/OFF" class="btn-off">Turn OFF Service</a>
        {% else %}
            <a href="/admin/toggle-service/ON" class="btn-on">Turn ON Service</a>
        {% endif %}
    </div>

    <div class="card">
        <h3>🛡️ Add / Remove Moderator</h3>
        <form action="/admin/set-moderator" method="POST">
            <input type="text" name="chat_id" placeholder="User Telegram Chat ID" required><br>
            <select name="action">
                <option value="add">Make Moderator</option>
                <option value="remove">Remove Moderator Role</option>
            </select><br>
            <button type="submit">Submit</button>
        </form>
    </div>

    <div class="card">
        <h3>📱 Assign Number to User (5-Min Limit)</h3>
        <form action="/admin/assign-number" method="POST">
            <input type="text" name="phone_number" placeholder="Phone Number" required><br>
            <input type="text" name="chat_id" placeholder="User Telegram Chat ID" required><br>
            <button type="submit" style="background: #28a745;">Assign Number</button>
        </form>
    </div>

    <div class="card">
        <h3>📩 Recent OTP History & Logs</h3>
        <table>
            <tr>
                <th>User ID</th>
                <th>Phone Number</th>
                <th>Service</th>
                <th>OTP Message</th>
                <th>Status</th>
            </tr>
            {% for log in logs %}
            <tr>
                <td>{{ log.chat_id }}</td>
                <td>{{ log.phone_number }}</td>
                <td>{{ log.service }}</td>
                <td><code>{{ log.otp_message }}</code></td>
                <td>
                    {% if log.status == 'delivered' %}
                        <span style="color: green;">Delivered</span>
                    {% else %}
                        <span style="color: red;">{{ log.status }}</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

@app.route('/admin')
def admin_panel():
    try:
        status_res = supabase.table('settings').select('value').eq('key', 'service_status').execute()
        status = status_res.data[0]['value'] if status_res.data else 'ON'
    except Exception:
        status = 'ON'
    
    try:
        logs_res = supabase.table('otp_logs').select('*').order('id', desc=True).limit(15).execute()
        logs = logs_res.data if logs_res.data else []
    except Exception:
        logs = []

    return render_template_string(ADMIN_HTML, status=status, logs=logs)

@app.route('/admin/toggle-service/<state>')
def toggle_service(state):
    supabase.table('settings').upsert({'key': 'service_status', 'value': state}).execute()
    return f"Service turned {state}! <br><a href='/admin'>Go Back</a>"

@app.route('/admin/set-moderator', methods=['POST'])
def set_moderator():
    chat_id = request.form.get('chat_id')
    action = request.form.get('action')
    is_mod = True if action == 'add' else False

    supabase.table('users').update({'is_moderator': is_mod}).eq('chat_id', chat_id).execute()
    return f"User {chat_id} moderator status updated to {is_mod}! <br><a href='/admin'>Go Back</a>"

@app.route('/admin/assign-number', methods=['POST'])
def assign_number():
    phone_number = request.form.get('phone_number')
    chat_id = request.form.get('chat_id')
    now_iso = datetime.now(timezone.utc).isoformat()

    supabase.table('numbers').upsert({
        'phone_number': phone_number, 
        'chat_id': chat_id,
        'assigned_at': now_iso
    }).execute()

    send_telegram(chat_id, f"📱 *[AsrPay] New Number Assigned:* `{phone_number}`\n⏰ *Time Limit:* 5 Minutes.")
    return "Number Assigned successfully! <br><a href='/admin'>Go Back</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
