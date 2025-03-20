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
                response = requests.post(f"{NODE_SERVER_URL}/save_message", json=message_data, timeout=10)
                response.raise_for_status()
                print("✅ 儲存成功:", response.status_code)
            except requests.exceptions.RequestException as e:
                print(f"❌ 儲存失敗: {e}")

    return 'OK'

@handler.add(FollowEvent)
def send_welcome(event):
    user_id = event.source.user_id
    user_mode[user_id] = "passive"
    send_mode_selection(user_id)

def GPT_response(text):
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(text) else "gpt-4o"
    print(f"使用模型: {model}")

    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": "你只能使用繁體中文或英文回答。"},
            {"role": "user", "content": text}
        ],
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

    mode_map = {
        "mode_passive": "passive",
        "mode_active": "active",
        "mode_constructive": "constructive",
        "mode_interactive": "interactive"
    }

    if user_text in mode_map:
        user_mode[user_id] = mode_map[user_text]
        reply_text = f"已切換至『{user_text.replace('mode_', '').capitalize()}』模式"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        return

    mode = user_mode.get(user_id, "passive")
    print(f"🛠 用戶 {user_id} 的目前模式：{mode}")

    # **安全讀取 MongoDB 歷史紀錄**
    try:
        history = requests.get(f"{NODE_SERVER_URL}/get_history", params={"user_id": user_id}, timeout=10).json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 錯誤: 讀取歷史紀錄失敗 - {e}")
        history = {}

    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    for msg in history.get("messages", [])[-5:]:
        messages.append({"role": "user", "content": msg.get("message_text", "")})
        messages.append({"role": "assistant", "content": msg.get("bot_response", "")})

    messages.append({"role": "user", "content": user_text})

    # **選擇模式回應**
    if mode == "passive":
        response_text = GPT_response(user_text)
    elif mode == "active":
        response_text = f"來挑戰一下吧！\n\n{GPT_response('請產生挑戰性問題')}"
    elif mode == "constructive":
        response_text = GPT_response(f"請引導用戶深入討論: {user_text}")
    elif mode == "interactive":
        response_text = GPT_response(user_text)
    else:
        response_text = "未知模式，請重新選擇。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
