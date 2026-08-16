import os
import requests

def send_telegram(text: str) -> bool:
    token = os.getenv('TG_TOKEN')
    chat = os.getenv('TG_CHAT')

    # টেলিগ্রামের সর্বোচ্চ লিমিট ৪১০৯ ক্যারেক্টার, তাই বেশি হলে কেটে ছোট করে নেওয়া
    if len(text) > 4096:
        text = text[:4093] + '...'

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat,
        'text': text,
        'disable_web_page_preview': True
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        json_res = res.json()
        if not json_res.get('ok'):
            print('Telegram refused it:', json_res.get('description', 'no response'))
            return False
        return True
    except Exception as e:
        print(f"Error sending telegram: {e}")
        return False
