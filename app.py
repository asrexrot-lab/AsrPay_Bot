import os
import hmac
import hashlib
import requests
from flask import Flask, request
from supabase import create_client, Client

app = Flask(__name__)

SUPABASE_URL = "https://mfrmudgpjjonycdrvlhe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1mcm11ZGdwampvbnljZHJ2bGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY4NzI4NDksImV4cCI6MjEwMjQ0ODg0OX0.gjsVOT0TKdiHJVcEkp5SuJklq65XQVQKzjQ0SmS5l2Q"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8831964761:AAFA8OyHWniT5RlPBpSItoszKei2ahO_U8U")
WEBHOOK_SECRET = os.getenv("PANEL_WEBHOOK_SECRET", "")
OTP_GROUP_ID = "-1003980634872"
ADMIN_CHAT_ID = "8745487398"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

admin_sessions = {}

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
    return "🚀 AsrPay Bot Admin System is Running!", 200

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

        if chat_id == str(ADMIN_CHAT_ID) and chat_id in admin_sessions:
            step = admin_sessions[chat_id].get("step")
            
            if step == "waiting_section":
                admin_sessions[chat_id]["section"] = text
                admin_sessions[chat_id]["step"] = "waiting_country"
                send_telegram(chat_id, "🌍 এখন **Country Name** লিখুন (যেমন: USA):")
                return "ok", 200
                
            elif step == "waiting_country":
                admin_sessions[chat_id]["country"] = text
                admin_sessions[chat_id]["step"] = "waiting_rate"
                send_telegram(chat_id, "💵 এখন প্রতি SMS এর **Rate (USD)** লিখুন (যেমন: 0.05):")
                return "ok", 200
                
            elif step == "waiting_rate":
                try:
                    rate = float(text)
                    admin_sessions[chat_id]["rate"] = rate
                    admin_sessions[chat_id]["step"] = "waiting_numbers"
                    send_telegram(chat_id, "📦 এখন একসাথে **নম্বরগুলো** দিন (প্রতি লাইনে একটি করে অথবা কমা দিয়ে):")
                except ValueError:
                    send_telegram(chat_id, "❌ সঠিক রেট দিন (সংখ্যায়, যেমন: 0.05):")
                return "ok", 200
                
            elif step == "waiting_numbers":
                sec = admin_sessions[chat_id]["section"]
                cou = admin_sessions[chat_id]["country"]
                rate = admin_sessions[chat_id]["rate"]
                
                numbers = [n.strip() for n in text.replace(',', '\n').split('\n') if n.strip()]
                
                try:
                    supabase.table('sections').upsert({'section_name': sec}, on_conflict='section_name').execute()
                    supabase.table('countries').upsert({'section_name': sec, 'country_name': cou, 'rate': rate}, on_conflict='section_name,country_name').execute()
                    
                    count = 0
                    for num in numbers:
                        supabase.table('numbers_pool').insert({
                            'phone_number': num,
                            'section': sec,
                            'country': cou,
                            'rate': rate,
                            'status': 'available'
                        }).execute()
                        count += 1
                        
                    del admin_sessions[chat_id]
                    send_telegram(chat_id, f"✅ সফলভাবে **{count}টি নম্বর** যোগ করা হয়েছে!\n\n📂 Section: `{sec}`\n🌍 Country: `{cou}`\n💵 Rate: `${rate}`", reply_markup=reply_keyboard)
                except Exception as e:
                    send_telegram(chat_id, f"❌ ডেটাবেজে সেভ করতে সমস্যা হয়েছে: {e}")
                    del admin_sessions[chat_id]
                return "ok", 200

        if text.startswith("/start"):
            if chat_id in admin_sessions:
                del admin_sessions[chat_id]
            send_telegram(chat_id, "✨ *Welcome to AsrPay OTP Bot!*\n\nনিচের শর্টকাট মেনু থেকে আপনার প্রয়োজনীয় অপশন সিলেক্ট করুন:", reply_markup=reply_keyboard)
        
        elif text == "📥 Get Number":
            try:
                sec_res = supabase.table('sections').select('section_name').execute()
                buttons = []
                if sec_res and sec_res.data:
                    for s in sec_res.data:
                        s_name = s['section_name']
                        buttons.append([{"text": f"📂 {s_name}", "callback_data": f"sec_{s_name}"}])
                
                if buttons:
                    send_telegram(chat_id, "📂 *Select a Section/Category:*", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram(chat_id, "⚠️ বর্তমানে কোনো সেকশন বা ক্যাটাগরি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"⚠️ Error: {e}")

        elif text == "💰 My Balance":
            try:
                user_res = supabase.table('users').select('balance').eq('chat_id', chat_id).execute()
                balance = 0.0
                if user_res and user_res.data:
                    balance = float(user_res.data[0].get('balance', 0.0))
                else:
                    supabase.table('users').insert({'chat_id': chat_id, 'balance': 0.0}).execute()
                
                send_telegram(chat_id, f"💰 *Your Current Balance:* `${balance:.2f}`")
            except Exception as e:
                send_telegram(chat_id, f"❌ Error: {e}")

        elif text == "👥 Referral":
            bot_username = "AsrPayBot"
            ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
            send_telegram(chat_id, f"👥 *Referral Program*\n\nআপনার রেফারেল লিংক:\n`{ref_link}`\n\nএই লিংকের মাধ্যমে বন্ধুরা জয়েন করলে আপনি বোনাস পাবেন!")

        elif text == "☎️ Support":
            send_telegram(chat_id, "☎️ *Support:* যেকোনো সমস্যায় যোগাযোগ করুন: @AsrPaySupport")

        elif text == "/admin":
            if chat_id == str(ADMIN_CHAT_ID):
                admin_kb = {
                    "inline_keyboard": [
                        [{"text": "➕ Bulk Add Numbers & Section", "callback_data": "admin_start_add"}]
                    ]
                }
                send_telegram(chat_id, "👑 *Bot Admin Panel*\n\nবটের ভেতর থেকেই নম্বর এবং সেকশন ম্যানেজ করতে নিচে ক্লিক করুন:", reply_markup=admin_kb)
            else:
                send_telegram(chat_id, "❌ আপনার এই কমান্ড ব্যবহারের অনুমতি নেই!")

    elif "callback_query" in update:
        query = update["callback_query"]
        chat_id = str(query["message"]["chat"]["id"])
        data = query["data"]

        if data == "admin_start_add":
            if chat_id == str(ADMIN_CHAT_ID):
                admin_sessions[chat_id] = {"step": "waiting_section"}
                send_telegram(chat_id, "📂 নতুন সেকশন বা ক্যাটাগরির নাম লিখুন (যেমন: Social Media বা Gaming):")

        elif data.startswith("sec_"):
            section_name = data.replace("sec_", "")
            try:
                country_res = supabase.table('countries').select('*').eq('section_name', section_name).execute()
                buttons = []
                if country_res and country_res.data:
                    for c in country_res.data:
                        c_name = c['country_name']
                        rate = c['rate']
                        buttons.append([{"text": f"🌍 {c_name} (${rate})", "callback_data": f"getnum_{section_name}_{c_name}"}])
                
                if buttons:
                    send_telegram(chat_id, f"🌍 *Select Country for {section_name}:*", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram(chat_id, "⚠️ এই সেকশনে বর্তমানে কোনো কান্ট্রি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"⚠️ Error: {e}")

        elif data.startswith("getnum_"):
            parts = data.split("_")
            section_name = parts[1]
            country_name = parts[2]

            try:
                num_check = supabase.table('numbers_pool').select('*').eq('section', section_name).eq('country', country_name).eq('status', 'available').limit(1).execute()
                if num_check and num_check.data:
                    num_data = num_check.data[0]
                    phone = num_data.get('phone_number')
                    rate = num_data.get('rate', 0.05)

                    supabase.table('numbers_pool').update({'status': 'assigned'}).eq('phone_number', phone).execute()
                    supabase.table('numbers_assigned').insert({'chat_id': chat_id, 'phone_number': phone, 'status': 'active', 'rate': rate}).execute()

                    send_telegram(chat_id, f"📱 *Number Assigned Successfully!*\n\nSection: `{section_name}`\nCountry: `{country_name}`\nNumber: `{phone}`\nRate: `${rate}`\n\nএখন এই নম্বরে কোড পাঠান!")
                else:
                    send_telegram(chat_id, "⚠️ দুঃখিত, এই কান্ট্রিতে বর্তমানে কোনো নম্বর খালি নেই।")
            except Exception as e:
                send_telegram(chat_id, f"❌ Error: {e}")

    return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
