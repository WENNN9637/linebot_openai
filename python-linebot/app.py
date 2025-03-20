from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai
import requests

def load_history(user_id):
    url = f"{NODE_SERVER_URL}/get_history"
    try:
        response = requests.get(url, params={"user_id": user_id}, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data if "messages" in data else {"messages": []}
    except requests.exceptions.RequestException as e:
        print(f"❌ API 讀取失敗: {e}")
        return {"messages": []}

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
user_mode = {}

def is_c_language(text):
    c_keywords = ["#include", "int ", "void ", "printf(", "return", "malloc", "struct "]
    return any(keyword in text for keyword in c_keywords)

def GPT_response(messages):
    if not isinstance(messages, list) or len(messages) == 0:
        raise ValueError("messages 必須是一個包含字典的列表")
    if messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": "你只能使用繁體中文或英文回答。"})
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(messages[-1].get("content", "")) else "gpt-4o"
    print(f"使用模型: {model}")
    response = openai.ChatCompletion.create(model=model, messages=messages, max_tokens=500, timeout=30)
    return response["choices"][0]["message"]["content"].strip()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    print(f"💬 收到來自 {user_id} 的訊息: {user_text}")
    history = load_history(user_id)
    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    for msg in history.get("messages", [])[-10:]:
        if msg.get("message_text") and msg.get("bot_response"):
            messages.append({"role": "user", "content": msg["message_text"]})
            messages.append({"role": "assistant", "content": msg["bot_response"]})
    messages.append({"role": "user", "content": user_text})
    response_text = GPT_response(messages)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))
    if response_text.strip():
        message_data = {"user_id": user_id, "message_text": user_text, "bot_response": response_text, "message_type": "text"}
        try:
            requests.post(f"{NODE_SERVER_URL}/save_message", json=message_data, timeout=10)
            print(f"✅ 成功儲存對話: {message_data}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 儲存對話失敗: {e}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
