import os
import requests
from flask import Flask, request, render_template_string, redirect, url_for
from supabase import create_client, Client

app = Flask(__name__)

SUPABASE_URL = "https://mfrmudgpjjonycdrvlhe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcm11ZGdwampvbnljZHJ2bGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY4NzI4NDksImV4cCI6MjEwMjQ0ODg0OX0.gjsVOT0TKdiHJVcEkp5SuJklq65XQVQKzjQ0SmS5l2Q"
TELEGRAM_BOT_TOKEN = "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U"
OTP_GROUP_ID = "-1003980634872"
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
    return "🚀 AsrPay Server is Running!", 200

# ------------------- TELEGRAM & SMS WEBHOOKS -------------------
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    event = request.get_json(silent=True) or {}
    if event.get('event') == 'message.received':
        d = event.get('data', {})
        number = d.get('number')
        source = d.get('source')
        message_text = d.get('message')

        try:
            num_res = supabase.table('numbers_assigned').select('*').eq('phone_number', number).eq('status', 'active').execute()
            if num_res and num_res.data:
                info = num_res.data[0]
                chat_id = info.get('chat_id')
                rate = float(info.get('rate', 0.05))

                user_res = supabase.table('users').select('balance').eq('chat_id', chat_id).execute()
                if user_res and user_res.data:
                    curr_bal = float(user_res.data[0].get('balance', 0.0))
                    new_bal = curr_bal + rate
                    supabase.table('users').update({'balance': new_bal}).eq('chat_id', chat_id).execute()

                    msg = f"📩 *New OTP Received!*\n\n📱 Number: `{number}`\n🌐 Service: `{source}`\n💬 Message: `{message_text}`\n\n💵 Earned: `+${rate:.2f}`"
                    send_telegram(chat_id, msg)

                    supabase.table('numbers_assigned').update({'status': 'used'}).eq('phone_number', number).execute()

                    if OTP_GROUP_ID:
                        group_msg = f"🔥 *New OTP Delivered*\n📱 Number: `{number[:-4]}****`\n🌐 Service: `{source}`\n💬 SMS: `{message_text}`"
                        send_telegram(OTP_GROUP_ID, group_msg)
        except Exception as e:
            print(f"Webhook DB error: {e}")
    return "ok", 200

@app.route('/bot-webhook', methods=['POST'])
def bot_webhook():
    update = request.get_json(silent=True) or {}
    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "")

        reply_keyboard = {
            "keyboard": [
                [{"text": "📥 Get Number"}, {"text": "💰 My Balance"}],
                [{"text": "👥 Referral"}, {"text": "☎️ Support"}]
            ],
            "resize_keyboard": True,
            "persistent": True
        }

        if text.startswith("/start"):
            # ইউজার স্টার্ট করলে ইউজারের রেকর্ড সেভ করে রাখা
            try:
                user_check = supabase.table('users').select('chat_id').eq('chat_id', chat_id).execute()
                if not user_check.data:
                    supabase.table('users').insert({'chat_id': chat_id, 'balance': 0.0}).execute()
            except Exception as e:
                print(f"User insert error: {e}")

            send_telegram(chat_id, "✨ *Welcome to AsrPay OTP Bot!*", reply_markup=reply_keyboard)
        elif text == "📥 Get Number":
            try:
                sec_res = supabase.table('sections').select('section_name').execute()
                buttons = []
                if sec_res and sec_res.data:
                    for s in sec_res.data:
                        buttons.append([{"text": f"📂 {s['section_name']}", "callback_data": f"sec_{s['section_name']}"}])
                if buttons:
                    send_telegram(chat_id, "📂 *Select Section:*", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram(chat_id, "⚠️ কোনো সেকশন পাওয়া যায়নি।")
            except Exception as e:
                send_telegram(chat_id, f"Error: {e}")
        elif text == "💰 My Balance":
            try:
                user_res = supabase.table('users').select('balance').eq('chat_id', chat_id).execute()
                balance = float(user_res.data[0].get('balance', 0.0)) if user_res and user_res.data else 0.0
                if not user_res.data:
                    supabase.table('users').insert({'chat_id': chat_id, 'balance': 0.0}).execute()
                send_telegram(chat_id, f"💰 *Balance:* `${balance:.2f}`")
            except Exception as e:
                send_telegram(chat_id, f"Error: {e}")
        elif text == "👥 Referral":
            send_telegram(chat_id, f"👥 *Referral Link:* `https://t.me/AsrPayBot?start=ref_{chat_id}`")
        elif text == "☎️ Support":
            send_telegram(chat_id, "☎️ *Support:* @AsrPaySupport")

    elif "callback_query" in update:
        query = update["callback_query"]
        chat_id = str(query["message"]["chat"]["id"])
        data = query["data"]

        if data.startswith("sec_"):
            sec_name = data.replace("sec_", "")
            try:
                c_res = supabase.table('countries').select('*').eq('section_name', sec_name).execute()
                buttons = []
                if c_res and c_res.data:
                    for c in c_res.data:
                        buttons.append([{"text": f"🌍 {c['country_name']} (${c['rate']})", "callback_data": f"getnum_{sec_name}_{c['country_name']}"}])
                if buttons:
                    send_telegram(chat_id, f"🌍 *Select Country for {sec_name}:*", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram(chat_id, "⚠️ এই সেকশনে কোনো কান্ট্রি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"Error: {e}")

        elif data.startswith("getnum_"):
            parts = data.split("_")
            sec_name, cou_name = parts[1], parts[2]
            try:
                rate_res = supabase.table('countries').select('rate').eq('section_name', sec_name).eq('country_name', cou_name).execute()
                rate = float(rate_res.data[0]['rate']) if rate_res and rate_res.data else 0.05

                num_res = supabase.table('numbers_pool').select('*').eq('section', sec_name).eq('country', cou_name).eq('status', 'available').limit(1).execute()
                if num_res and num_res.data:
                    num_data = num_res.data[0]
                    phone = num_data['phone_number']
                    
                    supabase.table('numbers_pool').update({'status': 'assigned'}).eq('phone_number', phone).execute()
                    supabase.table('numbers_assigned').insert({'chat_id': chat_id, 'phone_number': phone, 'status': 'active', 'rate': rate}).execute()
                    
                    send_telegram(chat_id, f"📱 *Number Assigned:* `{phone}`\n💵 Rate: `${rate}`")
                else:
                    send_telegram(chat_id, "⚠️ এই মুহূর্তে এই কান্ট্রিতে কোনো নম্বর খালি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"Error: {e}")
    return "ok", 200

# ------------------- ADVANCED HTML ADMIN PANEL -------------------
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AsrPay Master Admin Dashboard</title>
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: Arial, sans-serif; margin: 0; padding: 15px; }
        .container { max-width: 1000px; margin: auto; }
        .card { background: #1e293b; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #334155; }
        h2, h3 { color: #38bdf8; text-align: center; }
        input, select, textarea { width: 100%; padding: 10px; margin: 8px 0 15px 0; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 6px; box-sizing: border-box; }
        .btn { background: #0284c7; color: white; border: none; padding: 12px; width: 100%; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .btn:hover { background: #0369a1; }
        .btn-danger { background: #ef4444; padding: 6px 12px; border: none; color: white; border-radius: 4px; cursor: pointer; }
        .btn-danger:hover { background: #dc2626; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border: 1px solid #475569; padding: 10px; text-align: left; font-size: 14px; }
        th { background: #334155; color: #38bdf8; }
    </style>
</head>
<body>
    <div class="container">
        <h2>👑 AsrPay Master Admin Dashboard</h2>
        
        <!-- 1. Add Numbers & Structure -->
        <div class="card">
            <h3>📦 Add Section, Country & Numbers</h3>
            <form action="/admin/bulk-add" method="POST">
                <label>Section Name:</label>
                <input type="text" name="section_name" placeholder="e.g. Social Media" required>
                <label>Country Name:</label>
                <input type="text" name="country_name" placeholder="e.g. USA" required>
                <label>Rate per SMS (USD):</label>
                <input type="number" step="0.01" name="rate" placeholder="0.05" required>
                <label>Numbers List (কমা বা নতুন লাইনে দিন):</label>
                <textarea name="numbers_list" rows="4" placeholder="+123456789\n+198765432" required></textarea>
                <button class="btn">Upload Numbers</button>
            </form>
        </div>

        <!-- 2. Delete Sections / Countries -->
        <div class="card">
            <h3>🗑️ Delete Section & Country</h3>
            <form action="/admin/delete-structure" method="POST">
                <label>Select Section to Delete:</label>
                <select name="section_name" required>
                    <option value="">-- Select Section --</option>
                    {% for s in sections %}
                    <option value="{{ s.section_name }}">{{ s.section_name }}</option>
                    {% endfor %}
                </select>
                <label>Country Name (ঐচ্ছিক: পুরো সেকশন মুছতে চাইলে খালি রাখুন):</label>
                <input type="text" name="country_name" placeholder="e.g. USA (Leave blank to delete entire section)">
                <button class="btn-danger" style="width:100%; padding:12px; font-weight:bold;">Delete Section/Country</button>
            </form>
        </div>

        <!-- 3. Manage Users Balance (+ / -) & Details -->
        <div class="card">
            <h3>👥 Users Details & Balance Management (+ / -)</h3>
            <table>
                <tr>
                    <th>Chat ID</th>
                    <th>Current Balance</th>
                    <th>Update Balance (+ / - amount)</th>
                </tr>
                {% for u in users %}
                <tr>
                    <td>{{ u.chat_id }}</td>
                    <td>${{ u.balance }}</td>
                    <td>
                        <form action="/admin/update-balance" method="POST" style="display:flex; gap:10px; margin:0;">
                            <input type="hidden" name="chat_id" value="{{ u.chat_id }}">
                            <input type="number" step="0.01" name="amount" placeholder="e.g. +1.50 or -0.50" required style="margin:0;">
                            <button class="btn" style="width:120px; padding:6px;">Update</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <!-- 4. Manage Numbers Pool -->
        <div class="card">
            <h3>📋 Numbers Pool (Delete Numbers)</h3>
            <table>
                <tr>
                    <th>Number</th>
                    <th>Section</th>
                    <th>Country</th>
                    <th>Rate</th>
                    <th>Status</th>
                    <th>Action</th>
                </tr>
                {% for n in numbers %}
                <tr>
                    <td>{{ n.phone_number }}</td>
                    <td>{{ n.section }}</td>
                    <td>{{ n.country }}</td>
                    <td>${{ n.rate }}</td>
                    <td>{{ n.status }}</td>
                    <td>
                        <form action="/admin/delete-number" method="POST" style="margin:0;">
                            <input type="hidden" name="phone_number" value="{{ n.phone_number }}">
                            <button class="btn-danger">Delete</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/admin')
def admin_dashboard():
    try:
        num_res = supabase.table('numbers_pool').select('*').execute()
        user_res = supabase.table('users').select('*').execute()
        sec_res = supabase.table('sections').select('*').execute()
        
        numbers = num_res.data if num_res and num_res.data else []
        users = user_res.data if user_res and user_res.data else []
        sections = sec_res.data if sec_res and sec_res.data else []
    except Exception:
        numbers, users, sections = [], [], []

    return render_template_string(ADMIN_HTML, numbers=numbers, users=users, sections=sections)

@app.route('/admin/bulk-add', methods=['POST'])
def bulk_add():
    sec = request.form.get('section_name', '').strip()
    cou = request.form.get('country_name', '').strip()
    try:
        rate = float(request.form.get('rate', 0.05))
    except ValueError:
        rate = 0.05

    raw_text = request.form.get('numbers_list', '')
    numbers = [n.strip() for n in raw_text.replace(',', '\n').split('\n') if n.strip()]
    
    try:
        supabase.table('sections').upsert({'section_name': sec}, on_conflict='section_name').execute()
        supabase.table('countries').upsert({'section_name': sec, 'country_name': cou, 'rate': rate}, on_conflict='section_name,country_name').execute()

        for num in numbers:
            supabase.table('numbers_pool').insert({
                'phone_number': num,
                'section': sec,
                'country': cou,
                'rate': rate,
                'status': 'available'
            }).execute()
    except Exception as e:
        print(f"Error: {e}")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-number', methods=['POST'])
def delete_number():
    phone = request.form.get('phone_number')
    if phone:
        try:
            supabase.table('numbers_pool').delete().eq('phone_number', phone).execute()
        except Exception as e:
            print(f"Error: {e}")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-balance', methods=['POST'])
def update_balance():
    chat_id = request.form.get('chat_id')
    try:
        amount = float(request.form.get('amount', 0))
        user_res = supabase.table('users').select('balance').eq('chat_id', chat_id).execute()
        if user_res and user_res.data:
            current_bal = float(user_res.data[0].get('balance', 0.0))
            new_bal = current_bal + amount
            supabase.table('users').update({'balance': max(0.0, new_bal)}).eq('chat_id', chat_id).execute()
    except Exception as e:
        print(f"Error: {e}")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-structure', methods=['POST'])
def delete_structure():
    sec = request.form.get('section_name', '').strip()
    cou = request.form.get('country_name', '').strip()
    try:
        if cou:
            # শুধু নির্দিষ্ট কান্ট্রি এবং ওই কান্ট্রির নম্বরগুলো ডিলিট করবে
            supabase.table('countries').delete().eq('section_name', sec).eq('country_name', cou).execute()
            supabase.table('numbers_pool').delete().eq('section', sec).eq('country', cou).execute()
        else:
            # পুরো সেকশন, তার কান্ট্রি এবং সেকশনের সব নম্বর ডিলিট করবে
            supabase.table('countries').delete().eq('section_name', sec).execute()
            supabase.table('numbers_pool').delete().eq('section', sec).execute()
            supabase.table('sections').delete().eq('section_name', sec).execute()
    except Exception as e:
        print(f"Error: {e}")
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
