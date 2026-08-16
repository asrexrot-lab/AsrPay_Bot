import os
import hmac
import hashlib
import requests
from flask import Flask, request, render_template_string
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
    return "🚀 AsrPay Advanced OTP Automation Server is Running!", 200

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

        try:
            num_res = supabase.from_('numbers_assigned').select('*').eq('phone_number', number).eq('status', 'active').execute()
            if num_res and num_res.data:
                info = num_res.data[0]
                chat_id = info.get('chat_id')
                rate = float(info.get('rate', 0.05))

                user_res = supabase.from_('users').select('balance').eq('chat_id', chat_id).execute()
                if user_res and user_res.data:
                    curr_bal = float(user_res.data[0].get('balance', 0.0))
                    new_bal = curr_bal + rate
                    supabase.from_('users').update({'balance': new_bal}).eq('chat_id', chat_id).execute()

                    msg = f"📩 *New OTP Received!*\n\n📱 Number: `{number}`\n🌐 Service: `{source}`\n💬 Message: `{message_text}`\n\n💵 Earned: `+${rate:.2f}`"
                    send_telegram(chat_id, msg)

                    supabase.from_('numbers_assigned').update({'status': 'used'}).eq('phone_number', number).execute()

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
        args = text.split(" ")

        # রেফারেল সিস্টেম হ্যান্ডেল করা (/start ref_12345)
        if text.startswith("/start"):
            if len(args) > 1:
                ref_code = args[1]
                # রেফারেল ডাটা সেভ বা কাউন্ট করার লজিক এখানে থাকতে পারে
            
            main_menu = {
                "inline_keyboard": [
                    [{"text": "📥 Get Number", "callback_data": "menu_sections"}, {"text": "💰 Balance", "callback_data": "my_balance"}],
                    [{"text": "👥 Referral", "callback_data": "my_referral"}, {"text": "☎️ Support", "url": "https://t.me/AsrPaySupport"}]
                ]
            }
            send_telegram(chat_id, "✨ *Welcome to AsrPay OTP Bot!*\n\nনিচের মেনু থেকে আপনার প্রয়োজনীয় অপشن সিলেক্ট করুন:", reply_markup=main_menu)
        
        elif text.startswith("/admin"):
            if str(chat_id) == str(ADMIN_CHAT_ID):
                admin_kb = {
                    "inline_keyboard": [
                        [{"text": "🌐 Open Web Admin Panel", "url": request.host_url + "admin"}],
                        [{"text": "📢 Broadcast Notice", "callback_data": "admin_notice"}]
                    ]
                }
                send_telegram(chat_id, "👑 *Admin Control Panel*\n\nএকাধিক নম্বর একসাথে যোগ করতে এবং প্যানেল কন্ট্রোল করতে নিচে যান:", reply_markup=admin_kb)
            else:
                send_telegram(chat_id, "❌ আপনার এই কমান্ড ব্যবহারের অনুমতি নেই!")

    elif "callback_query" in update:
        query = update["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        data = query["data"]

        if data == "menu_sections":
            # ডাটাবেজ থেকে সেকশন বা ক্যাটাগরি লোড করা
            try:
                sec_res = supabase.from_('sections').select('section_name').execute()
                buttons = []
                if sec_res and sec_res.data:
                    for s in sec_res.data:
                        s_name = s['section_name']
                        buttons.append([{"text": f"📂 {s_name}", "callback_data": f"sec_{s_name}"}])
                
                buttons.append([{"text": "⬅️ Back to Home", "callback_data": "home_menu"}])
                send_telegram(chat_id, "📂 *Select a Section/Category:*", reply_markup={"inline_keyboard": buttons})
            except Exception as e:
                send_telegram(chat_id, "⚠️ বর্তমানে কোনো সেকশন পাওয়া যায়নি।")

        elif data.startswith("sec_"):
            section_name = data.replace("sec_", "")
            # নির্দিষ্ট সেকশনের কান্ট্রি লোড করা
            try:
                country_res = supabase.from_('countries').select('*').eq('section_name', section_name).execute()
                buttons = []
                if country_res and country_res.data:
                    for c in country_res.data:
                        c_name = c['country_name']
                        rate = c['rate']
                        buttons.append([{"text": f"🌍 {c_name} (${rate})", "callback_data": f"getnum_{section_name}_{c_name}"}])
                
                buttons.append([{"text": "⬅️ Back", "callback_data": "menu_sections"}])
                send_telegram(chat_id, f"🌍 *Select Country for {section_name}:*", reply_markup={"inline_keyboard": buttons})
            except Exception as e:
                send_telegram(chat_id, "⚠️ এই সেকশনে কোনো কান্ট্রি নেই।")

        elif data.startswith("getnum_"):
            parts = data.split("_")
            section_name = parts[1]
            country_name = parts[2]

            try:
                num_check = supabase.from_('numbers_pool').select('*').eq('section', section_name).eq('country', country_name).eq('status', 'available').limit(1).execute()
                if num_check and num_check.data:
                    num_data = num_check.data[0]
                    phone = num_data.get('phone_number')
                    rate = num_data.get('rate', 0.05)

                    supabase.from_('numbers_pool').update({'status': 'assigned'}).eq('phone_number', phone).execute()
                    supabase.from_('numbers_assigned').insert({'chat_id': str(chat_id), 'phone_number': phone, 'status': 'active', 'rate': rate}).execute()

                    send_telegram(chat_id, f"📱 *Number Assigned Successfully!*\n\nSection: `{section_name}`\nCountry: `{country_name}`\nNumber: `{phone}`\nRate: `${rate}`\n\nএখন এই নম্বরে কোড পাঠান!")
                else:
                    send_telegram(chat_id, "⚠️ দুঃখিত, এই কান্ট্রিতে বর্তমানে কোনো নম্বর খালি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"❌ Error: {e}")

        elif data == "my_balance":
            try:
                user_res = supabase.from_('users').select('balance').eq('chat_id', str(chat_id)).execute()
                balance = 0.0
                if user_res and user_res.data:
                    balance = float(user_res.data[0].get('balance', 0.0))
                else:
                    supabase.from_('users').insert({'chat_id': str(chat_id), 'balance': 0.0}).execute()
                
                send_telegram(chat_id, f"💰 *Your Current Balance:* `${balance:.2f}`")
            except Exception as e:
                send_telegram(chat_id, f"❌ Error: {e}")

        elif data == "my_referral":
            bot_username = "AsrPayBot" # আপনার বটের ইউজারনেম দিন
            ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
            send_telegram(chat_id, f"👥 *Referral Program*\n\nআপনার রেফারেল লিংক:\n`{ref_link}`\n\nএই লিংকের মাধ্যমে বন্ধুরা জয়েন করলে আপনি বোনাস পাবেন!")

        elif data == "home_menu":
            main_menu = {
                "inline_keyboard": [
                    [{"text": "📥 Get Number", "callback_data": "menu_sections"}, {"text": "💰 Balance", "callback_data": "my_balance"}],
                    [{"text": "👥 Referral", "callback_data": "my_referral"}, {"text": "☎️ Support", "url": "https://t.me/AsrPaySupport"}]
                ]
            }
            send_telegram(chat_id, "✨ *Main Menu:*", reply_markup=main_menu)

    return "ok", 200

# ------------------- 3. WEB ADMIN PANEL (BULK NUMBER ADD) -------------------
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
        input, select, textarea { width: 100%; padding: 10px; margin: 5px 0 12px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 6px; box-sizing: border-box; }
        .btn { background: #0284c7; color: white; border: none; padding: 10px; width: 100%; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .btn:hover { background: #0369a1; }
    </style>
</head>
<body>
    <h2>👑 AsrPay Admin Dashboard</h2>
    
    <div class="card">
        <h3>➕ Add Section & Country</h3>
        <form action="/admin/add-structure" method="POST">
            <input type="text" name="section_name" placeholder="Section Name (e.g. Social Media)" required>
            <input type="text" name="country_name" placeholder="Country Name (e.g. USA)" required>
            <input type="number" step="0.01" name="rate" placeholder="Rate per SMS (USD)" required>
            <button class="btn">Save Section & Country</button>
        </form>
    </div>

    <div class="card">
        <h3>📦 Bulk Add Numbers (একসাথে অনেক নম্বর)</h3>
        <form action="/admin/bulk-add" method="POST">
            <input type="text" name="section_name" placeholder="Section Name" required>
            <input type="text" name="country_name" placeholder="Country Name" required>
            <input type="number" step="0.01" name="rate" placeholder="Rate (USD)" required>
            <textarea name="numbers_list" rows="5" placeholder="প্রতি লাইনে একটি করে অথবা কমা দিয়ে নম্বরগুলো দিন..." required></textarea>
            <button class="btn">Upload All Numbers</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/admin')
def admin_dashboard():
    return render_template_string(ADMIN_HTML)

@app.route('/admin/add-structure', methods=['POST'])
def add_structure():
    sec = request.form.get('section_name')
    cou = request.form.get('country_name')
    rate = float(request.form.get('rate', 0.05))
    try:
        supabase.from_('sections').upsert({'section_name': sec}).execute()
        supabase.from_('countries').upsert({'section_name': sec, 'country_name': cou, 'rate': rate}).execute()
        return "Section & Country Added Successfully! <br><br><a href='/admin'>⬅️ Go Back</a>"
    except Exception as e:
        return f"Error: {e} <br><br><a href='/admin'>⬅️ Go Back</a>"

@app.route('/admin/bulk-add', methods=['POST'])
def bulk_add():
    sec = request.form.get('section_name')
    cou = request.form.get('country_name')
    rate = float(request.form.get('rate', 0.05))
    raw_text = request.form.get('numbers_list', '')
    
    # কমা অথবা নতুন লাইন দিয়ে নম্বর আলাদা করা
    numbers = [n.strip() for n in raw_text.replace(',', '\n').split('\n') if n.strip()]
    
    count = 0
    try:
        for num in numbers:
            supabase.from_('numbers_pool').insert({
                'phone_number': num,
                'section': sec,
                'country': cou,
                'rate': rate,
                'status': 'available'
            }).execute()
            count += 1
        return f"Successfully Added {count} Numbers! <br><br><a href='/admin'>⬅️ Go Back</a>"
    except Exception as e:
        return f"Error: {e} <br><br><a href='/admin'>⬅️ Go Back</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
