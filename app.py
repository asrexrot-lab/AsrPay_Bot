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

# Your Live API Key Integration
LIVE_SECRET_API_KEY = "Sk_live_5OMGmu5v4UY3pXjDokxOtOVaba25WSi55cfYrc3h"

OTP_GROUP_ID = os.getenv("OTP_GROUP_ID", "")
ADMIN_CHAT_IDS = ["8745487398"] 

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
        res = requests.post(url, json=payload, timeout=5)
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

def is_user_banned(chat_id):
    try:
        res = supabase.from_('users').select('is_banned').eq('chat_id', chat_id).execute()
        if res and hasattr(res, 'data') and res.data:
            return bool(res.data[0].get('is_banned', False))
    except Exception:
        pass
    return False

@app.route('/')
def home():
    return "🚀 AsrPay Professional Master Server Running with Live API!", 200

# ------------------- 1. API & SMS WEBHOOK -------------------
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

                if is_user_banned(chat_id):
                    return "OK", 200

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

user_wd_state = {}

# ------------------- 2. TELEGRAM BOT WORKFLOW -------------------
@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    try:
        update = request.get_json(silent=True) or {}
        
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")

            if is_user_banned(chat_id):
                send_telegram(chat_id, "❌ *আপনার এই প্যানেলটি ব্যবহার করার অনুমতি নেই!*")
                return "OK", 200

            if text.startswith("/start"):
                args = text.split()
                referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
                
                try:
                    res = supabase.from_('users').select('chat_id').eq('chat_id', chat_id).execute()
                    if not (res and hasattr(res, 'data') and res.data):
                        supabase.from_('users').insert({
                            'chat_id': chat_id,
                            'balance': 0.00,
                            'referred_by': referrer_id if referrer_id != chat_id else None,
                            'is_banned': False
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
                    send_telegram(chat_id, "⚠️ *দুঃখিত! বর্তমানে নম্বর সার্ভিস সাময়িকভাবে বন্ধ আছে।*")
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
                    f"🎁 *রিওয়ার্ড:* আপনার রেফারকৃত ইউজার $১ আয় করলে পাবেন ঠিক *{REFERRAL_BONUS_BDT} BDT* বোনাস!"
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
                    "আপনার যেকোনো সমস্যা বা অনুসন্ধানের জন্য সরাসরি যোগাযোগ করুন:"
                )
                send_telegram(chat_id, sup_msg, reply_markup=reply_markup)

            elif chat_id in user_wd_state:
                method = user_wd_state.pop(chat_id)
                wallet_no = text.strip()
                
                bal = 0.00
                try:
                    res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                    if res and hasattr(res, 'data') and res.data:
                        bal = float(res.data[0].get('balance', 0.00))
                except Exception:
                    pass

                try:
                    supabase.from_('withdrawals').insert({
                        'chat_id': chat_id,
                        'method': method,
                        'wallet_number': wallet_no,
                        'amount': bal,
                        'status': 'Pending'
                    }).execute()
                except Exception as e:
                    print(f"Wd db error: {e}")

                supabase.from_('users').update({'balance': 0.00}).eq('chat_id', chat_id).execute()
                send_telegram(chat_id, f"✅ *Withdrawal Request Successful!*\n\n💳 Method: *{method}*\n📱 Number: `{wallet_no}`\n💰 Amount: *${bal:.2f}*")

            elif text.startswith("/admin"):
                if str(chat_id) in ADMIN_CHAT_IDS:
                    admin_inline_keyboard = {
                        "inline_keyboard": [
                            [{"text": "🟢 Turn ON Service", "callback_data": "admin_on"}, {"text": "🔴 Turn OFF Service", "callback_data": "admin_off"}],
                            [{"text": "👥 Registered Users", "callback_data": "admin_users_list"}],
                            [{"text": "📊 Recent OTP Logs", "callback_data": "admin_logs"}]
                        ]
                    }
                    send_telegram(chat_id, "👑 *AsrPay Telegram Admin Panel*", reply_markup=admin_inline_keyboard)
                else:
                    send_telegram(chat_id, "❌ আপনার এই প্যানেলটি ব্যবহার করার অনুমতি নেই!")

        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]

            if is_user_banned(chat_id):
                return "OK", 200

            if data == "req_withdraw":
                bal = 0.00
                try:
                    res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                    if res and hasattr(res, 'data') and res.data:
                        bal = float(res.data[0].get('balance', 0.00))
                except Exception:
                    pass

                if bal < MIN_WITHDRAWAL_USD:
                    send_telegram(chat_id, f"❌ ব্যালেন্স কম আছে! সর্বনিম্ন উইথড্র: *${MIN_WITHDRAWAL_USD:.2f}*")
                else:
                    method_menu = {
                        "inline_keyboard": [
                            [{"text": "🔴 bKash", "callback_data": "wd_bkash"}, {"text": "🟠 Nagad", "callback_data": "wd_nagad"}]
                        ]
                    }
                    send_telegram(chat_id, f"💸 *আপনার ব্যালেন্স: ${bal:.2f}*\n\nপেমেন্ট মাধ্যম সিলেক্ট করুন:", reply_markup=method_menu)

            elif data in ["wd_bkash", "wd_nagad"]:
                method_name = "bKash" if data == "wd_bkash" else "Nagad"
                user_wd_state[chat_id] = method_name
                send_telegram(chat_id, f"📱 আপনার *{method_name}* নম্বরটি লিখে পাঠান:")

            elif data == "admin_on":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    supabase.from_('settings').upsert({'key': 'service_status', 'value': 'ON'}).execute()
                    send_telegram(chat_id, "✅ সার্ভিস চালু (ON) করা হয়েছে!")

            elif data == "admin_off":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    supabase.from_('settings').upsert({'key': 'service_status', 'value': 'OFF'}).execute()
                    send_telegram(chat_id, "❌ সার্ভিস বন্ধ (OFF) করা হয়েছে!")

            elif data == "admin_users_list":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    try:
                        users_res = supabase.from_('users').select('*').limit(10).execute()
                        if users_res and hasattr(users_res, 'data') and users_res.data:
                            u_text = "👥 *Registered Users (Last 10):*\n\n"
                            for u in users_res.data:
                                status_str = "🔴 Banned" if u.get('is_banned') else "🟢 Active"
                                u_text += f"🆔 `{u.get('chat_id')}`\n💰 Balance: `${float(u.get('balance', 0)):.2f}`\nStatus: {status_str}\n------------------\n"
                            send_telegram(chat_id, u_text)
                    except Exception as e:
                        send_telegram(chat_id, f"❌ Error: {e}")

            elif data == "admin_logs":
                if str(chat_id) in ADMIN_CHAT_IDS:
                    try:
                        logs_res = supabase.from_('otp_logs').select('*').order('id', desc=True).limit(5).execute()
                        if logs_res and hasattr(logs_res, 'data') and logs_res.data:
                            log_text = "📊 *Recent OTP Logs (Last 5):*\n\n"
                            for log in logs_res.data:
                                log_text += f"📱 `{log.get('phone_number')}`\n🌐 {log.get('service')}\n💬 `{log.get('otp_message')}`\n------------------\n"
                            send_telegram(chat_id, log_text)
                    except Exception as e:
                        send_telegram(chat_id, f"❌ Error: {e}")

            elif data.startswith("get_"):
                if not check_service_status():
                    send_telegram(chat_id, "⚠️ *বর্তমানে নম্বর সার্ভিস বন্ধ রয়েছে!*")
                    return "OK", 200

                service = data.replace("get_", "").upper()
                send_telegram(chat_id, f"✅ *Selected Service:* `{service}`\n\nঅ্যাডমিন প্যানেল থেকে নম্বর অ্যাসাইন হওয়া পর্যন্ত অপেক্ষা করুন... (মেয়াদ: ৫ মিনিট)")

    except Exception as main_e:
        print(f"Bot Webhook Error: {main_e}")

    return "OK", 200

# ------------------- 3. MOBILE-FRIENDLY WEB ADMIN PANEL DASHBOARD -------------------
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AsrPay Mobile Admin Panel</title>
    <style>
        * { box-sizing: border-box; font-family: sans-serif; }
        body { background: #0f172a; color: #f8fafc; margin: 0; padding: 10px; }
        .container { max-width: 100%; margin: 0 auto; }
        .header { background: #1e293b; padding: 15px; border-radius: 12px; text-align: center; margin-bottom: 15px; border: 1px solid #334155; }
        .header h1 { margin: 0; font-size: 22px; color: #38bdf8; }
        .card { background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 1px solid #334155; }
        .card h3 { margin-top: 0; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 8px; font-size: 16px; }
        .btn { display: block; width: 100%; text-align: center; padding: 12px; border-radius: 8px; color: white; text-decoration: none; font-weight: 600; border: none; cursor: pointer; font-size: 14px; margin-top: 8px; }
        .btn-on { background: #10b981; } 
        .btn-off { background: #ef4444; } 
        .btn-primary { background: #0284c7; } 
        .btn-danger { background: #dc2626; padding: 6px 10px; font-size: 12px; display: inline-block; width: auto; }
        .btn-success { background: #059669; padding: 6px 10px; font-size: 12px; display: inline-block; width: auto; }
        input { width: 100%; padding: 10px; margin: 6px 0; border: 1px solid #475569; background: #0f172a; color: white; border-radius: 8px; font-size: 14px; }
        .table-responsive { width: 100%; overflow-x: auto; margin-top: 10px; }
        table { width: 100%; border-collapse: collapse; min-width: 300px; }
        th, td { border: 1px solid #334155; padding: 8px; text-align: left; font-size: 12px; white-space: nowrap; }
        th { background: #0f172a; color: #94a3b8; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🚀 AsrPay Mobile Panel</h1>
    </div>
    <div class="card">
        <h3>Service Status: {{ status }}</h3>
        {% if status == 'ON' %}
            <a href="/admin/toggle-service/OFF" class="btn btn-off">Turn OFF Service</a>
        {% else %}
            <a href="/admin/toggle-service/ON" class="btn btn-on">Turn ON Service</a>
        {% endif %}
    </div>
    <div class="card">
        <h3>User Balance Management</h3>
        <form action="/admin/manage-user" method="POST">
            <input type="text" name="chat_id" placeholder="Telegram Chat ID" required>
            <input type="number" step="0.01" name="amount" placeholder="Amount (+ or -)" required>
            <button type="submit" class="btn btn-primary">Update Balance</button>
        </form>
    </div>
    <div class="card">
        <h3>Assign Number</h3>
        <form action="/admin/assign-number" method="POST">
            <input type="text" name="phone_number" placeholder="Phone Number" required>
            <input type="text" name="chat_id" placeholder="Telegram Chat ID" required>
            <button type="submit" class="btn btn-primary">Assign Number</button>
        </form>
    </div>
</div>
</body>
</html>
"""

@app.route('/admin')
def admin_panel():
    status = get_setting('service_status', 'ON')
    return render_template_string(ADMIN_HTML, status=status)

@app.route('/admin/toggle-service/<state>')
def toggle_service(state):
    supabase.from_('settings').upsert({'key': 'service_status', 'value': state}).execute()
    return f"Status updated to {state}! <br><a href='/admin'>Go Back</a>"

@app.route('/admin/manage-user', methods=['POST'])
def manage_user():
    chat_id = request.form.get('chat_id', '').strip()
    amount = float(request.form.get('amount', '0'))
    res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
    if res and res.data:
        new_bal = float(res.data[0].get('balance', 0.0)) + amount
        supabase.from_('users').update({'balance': new_bal}).eq('chat_id', chat_id).execute()
        send_telegram(chat_id, f"💳 আপনার অ্যাকাউন্টে ব্যালেন্স আপডেট হয়েছে। নতুন ব্যালেন্স: `${new_bal:.2f}`")
    return "Updated! <br><a href='/admin'>Go Back</a>"

@app.route('/admin/assign-number', methods=['POST'])
def assign_number():
    phone_number = request.form.get('phone_number', '').strip()
    chat_id = request.form.get('chat_id', '').strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.from_('numbers').upsert({'phone_number': phone_number, 'chat_id': chat_id, 'assigned_at': now_iso}).execute()
    send_telegram(chat_id, f"📱 *New Number Assigned:* `{phone_number}` (Valid for 5 Mins)")
    return "Assigned! <br><a href='/admin'>Go Back</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)

