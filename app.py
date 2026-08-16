import os
import hmac
import hashlib
import requests
from datetime import datetime, timezone
from flask import Flask, request, render_template_string
from supabase import create_client, Client

app = Flask(__name__)

# Credentials & Database Configuration
SUPABASE_URL = "https://mfrmudgpjjonycdrvlhe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcm11ZGdwampvbnljZHJ2bGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY4NzI4NDksImV4cCI6MjEwMjQ0ODg0OX0.gjsVOT0TKdiHJVcEkp5SuJklq65XQVQKzjQ0SmS5l2Q"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U")
WEBHOOK_SECRET = os.getenv("PANEL_WEBHOOK_SECRET", "")

OTP_GROUP_ID = os.getenv("OTP_GROUP_ID", "")

# আপনার টেলিগ্রাম আইডি এখানে দিন (যাতে আপনি টেলিগ্রাম থেকে অ্যাডমিন প্যানেল চালাতে পারেন)
ADMIN_CHAT_IDS = ["আপনার_টেলিগ্রাম_আইডি_এখানে_দিন"] 

EARNING_PER_SMS = 0.05
REFERRAL_BONUS_BDT = 3.00
MIN_WITHDRAWAL_USD = 1.00
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

def get_setting(key, default=""):
    try:
        res = supabase.from_('settings').select('value').eq('key', key).execute()
        if res and hasattr(res, 'data') and res.data:
            return res.data[0].get('value', default)
    except Exception as e:
        print(f"Setting get error [{key}]: {e}")
    return default

def check_service_status():
    status = get_setting('service_status', 'ON')
    return status == 'ON'

@app.route('/')
def home():
    return "🚀 AsrPay Professional Master Server Running!", 200

# ------------------- 1. API & SMS WEBHOOK (5-MIN EXPIRY CHECK) -------------------
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
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

            num_query = supabase.from_('numbers').select('chat_id, assigned_at').eq('phone_number', number).execute()
            
            if num_query and hasattr(num_query, 'data') and num_query.data:
                num_info = num_query.data[0]
                chat_id = num_info.get('chat_id')
                assigned_at_str = num_info.get('assigned_at')

                is_expired = False
                if assigned_at_str:
                    assigned_at = datetime.fromisoformat(assigned_at_str.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    if (now - assigned_at).total_seconds() / 60 > NUMBER_TIMEOUT_MINUTES:
                        is_expired = True

                msg_status = "delivered"
                if not is_expired and chat_id:
                    user_res = supabase.from_('users').select('balance, referred_by, pending_usd').eq('chat_id', chat_id).execute()
                    if user_res and hasattr(user_res, 'data') and user_res.data:
                        curr_bal = float(user_res.data[0].get('balance', 0.0))
                        referred_by = user_res.data[0].get('referred_by')
                        pending_usd = float(user_res.data[0].get('pending_usd') or 0.0)

                        new_bal = curr_bal + EARNING_PER_SMS
                        pending_usd += EARNING_PER_SMS

                        if referred_by and pending_usd >= 1.00:
                            ref_user = supabase.from_('users').select('balance').eq('chat_id', referred_by).execute()
                            if ref_user and hasattr(ref_user, 'data') and ref_user.data:
                                ref_bal = float(ref_user.data[0].get('balance', 0.0))
                                supabase.from_('users').update({'balance': ref_bal + REFERRAL_BONUS_BDT}).eq('chat_id', referred_by).execute()
                                send_telegram(referred_by, f"🎉 *AsrPay Bonus Reward!*\n\nআপনার রেফারকৃত ইউজার $১.০০ আয় করেছেন! আপনি পেয়েছেন *{REFERRAL_BONUS_BDT} BDT* বোনাস! 💰")
                            pending_usd -= 1.00

                        supabase.from_('users').update({'balance': new_bal, 'pending_usd': pending_usd}).eq('chat_id', chat_id).execute()

                        msg_text = f"📩 *[AsrPay] New OTP Received!*\n\n📱 *Number:* `{number}`\n🌐 *Service:* `{source}`\n💬 *Message:* `{message_text}`\n\n💵 *Earned:* `+${EARNING_PER_SMS:.2f}`"
                        sent = send_telegram(chat_id, msg_text)
                        if not sent:
                            msg_status = "failed_to_send_bot"
                else:
                    msg_status = "expired_timeout"
                    if chat_id:
                        send_telegram(chat_id, f"⚠️ *Time Out!* `{number}` নম্বরটির ৫ মিনিটের মেয়াদ শেষ হয়ে গেছে।")

                supabase.from_('otp_logs').insert({'chat_id': chat_id, 'phone_number': number, 'service': source, 'otp_message': message_text, 'status': msg_status}).execute()

                if OTP_GROUP_ID:
                    group_msg = f"🔥 *[AsrPay] NEW OTP ARRIVED*\n📱 *Number:* `{number[:-4]}****`\n🌐 *Service:* {source}\n💬 *SMS:* {message_text}"
                    send_telegram(OTP_GROUP_ID, group_msg)
    except Exception as e:
        print(f"Webhook processing error: {e}")

    return "OK", 200

# ------------------- 2. TELEGRAM BOT WORKFLOW -------------------
@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    try:
        update = request.get_json(silent=True) or {}
        
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")

            if text.startswith("/start"):
                args = text.split()
                referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
                
                try:
                    res = supabase.from_('users').select('chat_id').eq('chat_id', chat_id).execute()
                    if not (res and hasattr(res, 'data') and res.data):
                        supabase.from_('users').insert({
                            'chat_id': chat_id,
                            'balance': 0.00,
                            'referred_by': referrer_id if referrer_id != chat_id else None
                        }).execute()
                except Exception as db_e:
                    print(f"User insert error: {db_e}")

                main_keyboard = {
                    "keyboard": [
                        [{"text": "📱 Get Number"}, {"text": "💳 Balance"}],
                        [{"text": "🔗 Referral Link"}, {"text": "ℹ️ Support"}]
                    ],
                    "resize_keyboard": True
                }
                welcome_msg = (
                    "✨ *Welcome to AsrPay Official Bot!* ✨\n\n"
                    "নিচের বাটনগুলো ব্যবহার করে দ্রুত সার্ভিস সিলেক্ট করুন:\n"
                    "🔹 *Get Number:* নতুন ভেরিফিকেশন নম্বর নিন।\n"
                    "🔹 *Balance:* একাউন্ট ব্যালেন্স ও উইথড্র অপশন।\n"
                    "🔹 *Referral:* বন্ধুদের ইনভাইট করে ইনকাম করুন।"
                )
                send_telegram(chat_id, welcome_msg, reply_markup=main_keyboard)

            elif text in ["📱 Get Number", "/getnumber"]:
                if not check_service_status():
                    send_telegram(chat_id, "⚠️ *দুঃখিত! বর্তমানে নম্বর সার্ভিস সাময়িকভাবে বন্ধ আছে। পরে চেষ্টা করুন।*")
                    return "OK", 200

                menu = {
                    "inline_keyboard": [
                        [{"text": "🎵 TikTok", "callback_data": "get_tiktok"}, {"text": "🍏 Apple", "callback_data": "get_apple"}],
                        [{"text": "💬 WhatsApp", "callback_data": "get_whatsapp"}, {"text": "✈️ Telegram", "callback_data": "get_telegram"}],
                        [{"text": "📘 Facebook", "callback_data": "get_facebook"}, {"text": "🌐 Other", "callback_data": "get_other"}]
                    ]
                }
                send_telegram(chat_id, "📱 *AsrPay - আপনার প্রয়োজনীয় সার্ভিসটি সিলেক্ট করুন:*", reply_markup=menu)

            elif text in ["💳 Balance", "/balance"]:
                bal = 0.00
                try:
                    res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                    if res and hasattr(res, 'data') and res.data:
                        bal = float(res.data[0].get('balance', 0.00))
                except Exception as db_e:
                    print(f"Balance check error: {db_e}")

                balance_inline_btn = {
                    "inline_keyboard": [
                        [{"text": "💸 Request Withdraw", "callback_data": "req_withdraw"}]
                    ]
                }
                bal_msg = (
                    f"💳 *AsrPay Account Overview*\n\n"
                    f"👤 *User ID:* `{chat_id}`\n"
                    f"💰 *Current Balance:* `${bal:.2f} USD`\n"
                    f"🎯 *Minimum Withdraw:* `${MIN_WITHDRAWAL_USD:.2f} USD`\n\n"
                    f"উইথড্র করতে নিচের *Request Withdraw* বাটনে ক্লিক করুন:"
                )
                send_telegram(chat_id, bal_msg, reply_markup=balance_inline_btn)

            elif text in ["🔗 Referral Link", "/referral"]:
                ref_link = f"https://t.me/AsrPay_Bot?start={chat_id}"
                ref_msg = (
                    f"💎 *AsrPay Referral Program*\n\n"
                    f"আপনার রেফারেল লিংক শেয়ার করে বন্ধুদের ইনভাইট করুন!\n\n"
                    f"🔗 *লিংক:* `{ref_link}`\n\n"
                    f"🎁 *রিওয়ার্ড:* আপনার রেফারকৃত ইউজার $১ আয় করলে পাবেন *{REFERRAL_BONUS_BDT} BDT* তাৎক্ষণিক বোনাস!"
                )
                send_telegram(chat_id, ref_msg)

            elif text in ["ℹ️ Support", "/support"]:
                admin_user = get_setting('admin_username', '@AsrPayAdmin')
                support_group = get_setting('support_group', '')
                
                support_buttons = []
                if admin_user:
                    clean_user = admin_user.replace("@", "")
                    support_buttons.append([{"text": "👨‍💻 Admin Support", "url": f"https://t.me/{clean_user}"}])
                if support_group:
                    support_buttons.append([{"text": "📢 Official Group", "url": support_group}])

                reply_markup = {"inline_keyboard": support_buttons} if support_buttons else None
                
                sup_msg = (
                    "🎧 *AsrPay Support Center*\n\n"
                    "আপনার যেকোনো সমস্যা বা অনুসন্ধানের জন্য সরাসরি আমাদের সাথে যোগাযোগ করুন:"
                )
                send_telegram(chat_id, sup_msg, reply_markup=reply_markup)

            # টেলিগ্রাম থেকে অ্যাডমিন প্যানেল কমান্ড (/admin)
            elif text.startswith("/admin"):
                if str(chat_id) in ADMIN_CHAT_IDS:
                    admin_inline_keyboard = {
                        "inline_keyboard": [
                            [{"text": "🟢 Turn ON Service", "callback_data": "admin_on"}, {"text": "🔴 Turn OFF Service", "callback_data": "admin_off"}],
                            [{"text": "📊 View Logs", "callback_data": "admin_logs"}]
                        ]
                    }
                    send_telegram(chat_id, "👑 *AsrPay Telegram Admin Panel*\n\nনিচের অপশনগুলো থেকে আপনার কন্ট্রোল সিলেক্ট করুন:", reply_markup=admin_inline_keyboard)
                else:
                    send_telegram(chat_id, "❌ আপনার এই প্যানেলটি ব্যবহার করার অনুমতি নেই!")

        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]

            if data == "req_withdraw":
                bal = 0.00
                try:
                    res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                    if res and hasattr(res, 'data') and res.data:
                        bal = float(res.data[0].get('balance', 0.00))
                except Exception:
                    pass

                admin_user = get_setting('admin_username', '@AsrPayAdmin')

                if bal < MIN_WITHDRAWAL_USD:
                    send_telegram(chat_id, f"❌ *উইথড্র ব্যর্থ হয়েছে!*\n\nআপনার বর্তমান ব্যালেন্স: *${bal:.2f}*\nসর্বনিম্ন উইথড্র লিমিট: *${MIN_WITHDRAWAL_USD:.2f}*")
                else:
                    send_telegram(chat_id, f"✅ *উইথড্র করার জন্য প্রস্তুত!*\n\nআপনার ব্যালেন্স: *${bal:.2f}*\n\nউইথড্র প্রসেস করতে সরাসরি এডমিনের সাথে যোগাযোগ করুন:\n👉 {admin_user}")

            elif data == "admin_on":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    supabase.from_('settings').upsert({'key': 'service_status', 'value': 'ON'}).execute()
                    send_telegram(chat_id, "✅ সার্ভিস সফলভাবে চালু (ON) করা হয়েছে!")

            elif data == "admin_off":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    supabase.from_('settings').upsert({'key': 'service_status', 'value': 'OFF'}).execute()
                    send_telegram(chat_id, "❌ সার্ভিস সফলভাবে বন্ধ (OFF) করা হয়েছে!")

            elif data == "admin_logs":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    try:
                        logs_res = supabase.from_('otp_logs').select('*').order('id', desc=True).limit(5).execute()
                        if logs_res and hasattr(logs_res, 'data') and logs_res.data:
                            log_text = "📊 *Recent OTP Logs (Last 5):*\n\n"
                            for log in logs_res.data:
                                log_text += f"📱 `{log.get('phone_number')}`\n🌐 {log.get('service')}\n💬 `{log.get('otp_message')}`\nStatus: {log.get('status')}\n------------------\n"
                            send_telegram(chat_id, log_text)
                        else:
                            send_telegram(chat_id, "⚠️ কোনো লগ পাওয়া যায়নি।")
                    except Exception as e:
                        send_telegram(chat_id, f"❌ লগ আনতে সমস্যা হয়েছে: {e}")

            elif data.startswith("get_"):
                if not check_service_status():
                    send_telegram(chat_id, "⚠️ *বর্তমানে নম্বর সার্ভিস বন্ধ রয়েছে!*")
                    return "OK", 200

                service = data.replace("get_", "").upper()
                send_telegram(chat_id, f"✅ *Selected Service:* `{service}`\n\nঅ্যাডমিন প্যানেল থেকে নম্বর অ্যাসাইন হওয়া পর্যন্ত অপেক্ষা করুন... (মেয়াদ: ৫ মিনিট)")

    except Exception as main_e:
        print(f"Bot Webhook Fatal Error Avoided: {main_e}")

    return "OK", 200

# ------------------- 3. POWERFUL ADMIN PANEL CONTROL -------------------
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AsrPay Master Control Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 950px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #1e293b, #334155); padding: 25px; border-radius: 16px; border: 1px solid #475569; text-align: center; margin-bottom: 25px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }
        .header h1 { margin: 0; font-size: 28px; color: #38bdf8; letter-spacing: 1px; }
        .card { background: #1e293b; padding: 22px; border-radius: 14px; margin-bottom: 20px; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); }
        .card h3 { margin-top: 0; color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 10px; font-size: 19px; }
        .status-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 14px; margin-left: 8px; }
        .status-on { background: #059669; color: #ecfdf5; }
        .status-off { background: #dc2626; color: #fef2f2; }
        .btn { display: inline-block; padding: 10px 20px; border-radius: 8px; color: white; text-decoration: none; font-weight: 600; border: none; cursor: pointer; transition: 0.2s; font-size: 14px; }
        .btn-on { background: #10b981; } .btn-on:hover { background: #059669; }
        .btn-off { background: #ef4444; } .btn-off:hover { background: #dc2626; }
        .btn-primary { background: #0284c7; width: 100%; margin-top: 10px; padding: 12px; } .btn-primary:hover { background: #0369a1; }
        input { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #475569; background: #0f172a; color: white; border-radius: 8px; font-size: 14px; }
        input:focus { border-color: #38bdf8; outline: none; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #334155; padding: 12px; text-align: left; font-size: 14px; }
        th { background: #0f172a; color: #94a3b8; }
        tr:nth-child(even) { background: #182234; }
        .badge-success { color: #34d399; font-weight: 600; }
        .badge-fail { color: #f87171; font-weight: 600; }
    </style>
</head>
<body>

<div class="container">
    <div class="header">
        <h1>🚀 AsrPay Control Dashboard</h1>
        <p style="margin: 6px 0 0 0; color: #94a3b8;">Fully Powered Admin Management Panel</p>
    </div>

    <!-- Service Switch -->
    <div class="card">
        <h3>🔴 / 🟢 Service Status Control</h3>
        <p>Current Status: 
            <span class="status-badge {{ 'status-on' if status == 'ON' else 'status-off' }}">
                {{ status }}
            </span>
        </p>
        {% if status == 'ON' %}
            <a href="/admin/toggle-service/OFF" class="btn btn-off">Turn OFF Service</a>
        {% else %}
            <a href="/admin/toggle-service/ON" class="btn btn-on">Turn ON Service</a>
        {% endif %}
    </div>

    <!-- Dynamic Settings (Admin Username & Group) -->
    <div class="card">
        <h3>⚙️ Support & Admin Settings</h3>
        <form action="/admin/update-settings" method="POST">
            <label style="color:#94a3b8;">Admin Telegram Username:</label>
            <input type="text" name="admin_username" value="{{ admin_username }}" placeholder="@AsrPayAdmin" required>
            
            <label style="color:#94a3b8;">Official Support Group Link (Optional):</label>
            <input type="text" name="support_group" value="{{ support_group }}" placeholder="https://t.me/yourgroup">
            
            <button type="submit" class="btn btn-primary">Save Settings</button>
        </form>
    </div>

    <!-- Assign Number Section -->
    <div class="card">
        <h3>📱 Assign Number to User (5-Min Timeout)</h3>
        <form action="/admin/assign-number" method="POST">
            <input type="text" name="phone_number" placeholder="Phone Number (+8801XXXXXXXXX)" required>
            <input type="text" name="chat_id" placeholder="User Telegram Chat ID (e.g. 123456789)" required>
            <button type="submit" class="btn btn-primary" style="background: #10b981;">Assign Number Now</button>
        </form>
    </div>

    <!-- OTP History -->
    <div class="card">
        <h3>📩 Recent OTP History Logs</h3>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>User Chat ID</th>
                        <th>Phone Number</th>
                        <th>Service</th>
                        <th>OTP Message</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for log in logs %}
                    <tr>
                        <td><code>{{ log.chat_id }}</code></td>
                        <td><code>{{ log.phone_number }}</code></td>
                        <td>{{ log.service }}</td>
                        <td><code>{{ log.otp_message }}</code></td>
                        <td>
                            {% if log.status == 'delivered' %}
                                <span class="badge-success">Delivered</span>
                            {% else %}
                                <span class="badge-fail">{{ log.status }}</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="5" style="text-align: center; color: #64748b;">No recent OTP logs found.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

</body>
</html>
"""

@app.route('/admin')
def admin_panel():
    status = get_setting('service_status', 'ON')
    admin_username = get_setting('admin_username', '@AsrPayAdmin')
    support_group = get_setting('support_group', '')
    
    logs = []
    try:
        logs_res = supabase.from_('otp_logs').select('*').order('id', desc=True).limit(10).execute()
        if logs_res and hasattr(logs_res, 'data') and logs_res.data:
            logs = logs_res.data
    except Exception:
        logs = []

    return render_template_string(
        ADMIN_HTML, 
        status=status, 
        admin_username=admin_username, 
        support_group=support_group, 
        logs=logs
    )

@app.route('/admin/toggle-service/<state>')
def toggle_service(state):
    try:
        supabase.from_('settings').upsert({'key': 'service_status', 'value': state}).execute()
    except Exception as e:
        print(f"Toggle error: {e}")
    return f"Service status changed to {state}! <br><a href='/admin'>Go Back to Admin Panel</a>"

@app.route('/admin/update-settings', methods=['POST'])
def update_settings():
    admin_username = request.form.get('admin_username', '').strip()
    support_group = request.form.get('support_group', '').strip()
    
    try:
        supabase.from_('settings').upsert({'key': 'admin_username', 'value': admin_username}).execute()
        supabase.from_('settings').upsert({'key': 'support_group', 'value': support_group}).execute()
    except Exception as e:
        print(f"Settings update error: {e}")
        
    return "Settings Updated Successfully! <br><a href='/admin'>Go Back to Admin Panel</a>"

@app.route('/admin/assign-number', methods=['POST'])
def assign_number():
    phone_number = request.form.get('phone_number', '').strip()
    chat_id = request.form.get('chat_id', '').strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        supabase.from_('numbers').upsert({
            'phone_number': phone_number, 
            'chat_id': chat_id,
            'assigned_at': now_iso
        }).execute()
        send_telegram(chat_id, f"📱 *[AsrPay] New Number Assigned!*\n\nYour Phone Number: `{phone_number}`\n⏰ *Time Limit:* 5 Minutes.")
    except Exception as e:
        print(f"Assign error: {e}")

    return "Number Assigned successfully! <br><a href='/admin'>Go Back to Admin Panel</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
