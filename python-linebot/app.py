from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai
import requests
import time

app = Flask(__name__)

# 環境變數
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')

NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"

# 紀錄使用者模式
user_mode = {}

@app.route("/health", methods=['GET'])
def health_check():
    return "OK", 200

# ✅ 加入安全的歷史紀錄讀取函式
def load_history(user_id):
    url = f"{NODE_SERVER_URL}/get_history"
    try:
        response = requests.get(url, params={"user_id": user_id}, timeout=10)
        response.raise_for_status()  # 確保 API 回應 200 OK
        data = response.json()
        return data if "messages" in data else {"messages": []}
    except requests.exceptions.RequestException as e:
        print(f"❌ API 讀取失敗: {e}")
        return {"messages": []}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(403)

    body = request.get_data(as_text=True)
    print("📥 收到 LINE Webhook:", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ LINE 簽名驗證失敗")
        abort(400)

    # **解析 JSON 並儲存到 MongoDB**
    data = request.get_json(silent=True)
    if not data or "events" not in data:
        return jsonify({"error": "Invalid data"}), 400

    for event in data["events"]:
        if event["type"] == "message":
            message_data = {
                "user_id": event["source"].get("userId", "Unknown"),
                "message_text": event["message"].get("text", ""),
                "message_type": event["message"].get("type", "unknown")
            }
            print("📩 LINE 訊息:", message_data)

            # **安全地傳送到 Node.js**
            try:
                response = requests.post(f"{NODE_SERVER_URL}/save_message", json=message_data)
                print("📤 發送至 Node.js:", response.status_code, response.text)
            except requests.exceptions.RequestException as e:
                print(f"❌ 儲存失敗: {e}")

    return 'OK'

@handler.add(FollowEvent)
def send_welcome(event):
    user_id = event.source.user_id
    user_mode[user_id] = "passive"
    send_mode_selection(user_id)

def is_c_language(text):
    c_keywords = ["C", "c", "c語言", "C語言", "c language", "C language", "c programming", "C programming", "#include", "int ", "void ", "printf(", "scanf(", "return", "malloc", "free", "sizeof", "struct ", "typedef ", "->", "::", "main()"]
    return any(keyword in text for keyword in c_keywords)

def GPT_response(messages):
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(messages[-1]["content"]) else "gpt-4o"
    print(f"使用模型: {model}")

    # 直接將 system 訊息加進 messages
    messages.insert(0, {"role": "system", "content": "你只能使用繁體中文或英文回答。"})

    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,  # ✅ 正確的格式，傳遞完整的歷史對話
        max_tokens=500,
        timeout=30
    )
    
    return response["choices"][0]["message"]["content"].strip()

def send_mode_selection(user_id):
    flex_message = FlexSendMessage(
        alt_text="請選擇學習模式",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "請選擇學習模式", "weight": "bold", "size": "lg"},
                    {"type": "button", "style": "primary", "color": "#1DB446",
                     "action": {"type": "message", "label": "互動式 (Interactive)", "text": "mode_interactive"}},
                    {"type": "button", "style": "primary", "color": "#FFB74D",
                     "action": {"type": "message", "label": "建構式 (Constructive)", "text": "mode_constructive"}},
                    {"type": "button", "style": "primary", "color": "#42A5F5",
                     "action": {"type": "message", "label": "主動式 (Active)", "text": "mode_active"}},
                    {"type": "button", "style": "primary", "color": "#9E9E9E",
                     "action": {"type": "message", "label": "被動式 (Passive)", "text": "mode_passive"}}
                ]
            }
        }
    )
    line_bot_api.push_message(user_id, flex_message)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    
    print(f"💬 收到來自 {user_id} 的訊息: {user_text}")

    mode = user_mode.get(user_id, "passive")
    print(f"🛠 用戶 {user_id} 的目前模式：{mode}")

    # **安全讀取 MongoDB 歷史紀錄**
    history = load_history(user_id)

    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    for msg in history.get("messages", [])[-10:]:  # 取最近 10 筆對話
    if msg.get("message_text") and msg.get("bot_response"):  # 確保對話完整
        messages.append({"role": "user", "content": msg["message_text"]})
        messages.append({"role": "assistant", "content": msg["bot_response"]})

    messages.append({"role": "user", "content": user_text})  # 加入最新問題

    response_text = GPT_response(user_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))

    # ✅ 只有 `bot_response` 存在時才發送到 Node.js
    if response_text.strip():  
        message_data = {
            "user_id": user_id,
            "message_text": user_text,
            "bot_response": response_text,
            "message_type": "text"
        }
    
        try:
            requests.post(f"{NODE_SERVER_URL}/save_message", json=message_data, timeout=10)
            print(f"✅ 成功儲存對話: {message_data}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 儲存對話失敗: {e}")
    else:
        print("⚠️ `bot_response` 為空，跳過儲存")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
