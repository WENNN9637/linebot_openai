import threading
import openai
import requests
from linebot.models import TextSendMessage

NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
openai.api_key = "你的 OpenAI API Key"  # 或用 app.py 中設定即可

def get_waiting_message(context="general_chat"):
    return {
        "general_chat": "我想想怎麼說比較好 🤔"
    }.get(context, "稍等一下，我想想看 🤔")

def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ]
        )
        reply_text = response["choices"][0]["message"]["content"].strip()
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))

        # 儲存回應
        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": "",
            "bot_response": reply_text,
            "message_type": "bot"
        }, timeout=10)

    except Exception as e:
        print(f"❌ Passive 回覆錯誤：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了，再問一次看看 🥲"))

def handle_passive_mode(event, user_id, user_text, line_bot_api):
    wait_msg = get_waiting_message()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 在這個檔案裡不需要儲存 user_text，統一由 app.py 處理

    # 開始背景回覆
    threading.Thread(
        target=gpt_push_response,
        args=(
            "general_chat",
            user_id,
            user_text,
            "你是一位具有歷史記憶的 C 語言助教，請自然回應。",
            line_bot_api
        )
    ).start()
