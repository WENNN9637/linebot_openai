from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai
import requests

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
user_mode = {}

def load_history(user_id):
    url = f"{NODE_SERVER_URL}/get_history"
    try:
        response = requests.get(url, params={"user_id": user_id, "limit": 10}, timeout=10)
        response.raise_for_status()
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

# 產生主動學習的問題
def generate_active_question():
    prompt = "請產生一個具有挑戰性的問題，適合讓學習者思考並回答。問題應該與學習、科技或邏輯思考相關。"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "你是一個智慧型學習助手，會主動提出有趣的問題來幫助使用者學習。"},
                  {"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

# 產生互動式對話
def generate_interactive_response(user_input):
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "你是一個對話型學習助理，會根據使用者的問題進行互動。"},
                  {"role": "user", "content": user_input}]
    )
    return response["choices"][0]["message"]["content"]

# 產生引導式問題 (建構模式)
def generate_constructive_prompt(user_input):
    prompt = f"使用者說：「{user_input}」，請根據這個內容引導使用者提供更具體的想法，例如詢問他們的觀點或細節。"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "你是一個引導式學習助手，會幫助使用者深入思考。"},
                  {"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

def is_c_language(text):
    c_keywords = ["c", "#include", "int ", "void ", "printf(", "return", "malloc", "struct "]
    text = text.lower()  # 轉換為小寫，避免大小寫不匹配
    return any(keyword in text for keyword in c_keywords)

def GPT_response(messages):
    if not isinstance(messages, list) or len(messages) == 0:
        raise ValueError("messages 必須是一個包含字典的列表")
    if messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": "你只能使用繁體中文或英文回答。"})
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(messages[-1].get("content", "")) else "gpt-4o"
    print(f"使用模型: {model}")
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        max_tokens=500,
        timeout=30  # 避免 API 超時
    )
    return response["choices"][0]["message"]["content"].strip()

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

    # **📌 取得使用者當前模式，預設為被動模式**
    mode = user_mode.get(user_id, "passive")
    print(f"🛠 用戶 {user_id} 的目前模式：{mode}")

    history = load_history(user_id)
    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    for msg in history.get("messages", [])[-10:]:
        if msg.get("message_text") and msg.get("bot_response"):
            messages.append({"role": "user", "content": msg["message_text"]})
            messages.append({"role": "assistant", "content": msg["bot_response"]})
    messages.append({"role": "user", "content": user_text})

    # **📌 根據模式來選擇 AI 互動方式**
    if mode in ["passive", "interactive"]:
        response_text = GPT_response(messages)
    elif mode == "active":
        response_text = f"來挑戰一下吧！\n\n{generate_active_question()}"
    elif mode == "constructive":
        response_text = generate_constructive_prompt(user_text)
    else:
        response_text = "未知模式，請重新選擇。"
        
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
