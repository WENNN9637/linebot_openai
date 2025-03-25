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
user_state = {}  # user_id: { "mode": "active", "last_question": "...", "awaiting_answer": True }

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
    prompt = """
你是一位 C 語言的學習輔導老師，請你設計一個與 C 語言相關的挑戰性問題，讓學習者可以思考並嘗試回答。問題應涵蓋 C 語言的核心概念，例如：記憶體管理、指標、結構、陣列、流程控制、函式、或字串操作等，難度適中，有助於理解語法與邏輯。

請只產生問題，不要附加答案。
"""
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "你是一個 C 語言教學助手，會主動提出具挑戰性的問題。"},
            {"role": "user", "content": prompt}
        ]
    )
    return response["choices"][0]["message"]["content"].strip()

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
    prompt = f"""
使用者輸入了以下內容：

「{user_input}」

你是 C 語言教學助理，請根據這段內容，提出一個「具啟發性」的追問，引導使用者：

- 解釋自己的觀點
- 補充細節或例子
- 進一步思考其他可能性
- 或重構他剛剛的理解

請只給一句具體、自然的追問，例如：
- 你這樣設計的原因是什麼？
- 有其他方式可以達到同樣效果嗎？
- 這段程式在什麼情況下會出錯？
"""
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "你是一位擅長引導學習的 C 語言助教。"},
            {"role": "user", "content": prompt}
        ]
    )
    return response["choices"][0]["message"]["content"].strip()


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

def is_answer_related(user_input, last_question):
    """判斷使用者輸入是否與上一題有關聯"""
    user_input = user_input.lower()
    keywords = ["答案", "是什麼", "不懂", "為什麼", "我覺得", "我猜", "可能", "因為", "應該"]
    return any(kw in user_input for kw in keywords) or is_c_language(user_input)

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
    
        descriptions = {
            "passive": "你會以閱讀為主，我會盡量簡潔地回答你，不主動提問。",
            "active": "我會給你一些挑戰性的問題，讓你主動思考和作答。",
            "constructive": "我會根據你的回答，進一步追問，幫助你深化想法。",
            "interactive": "我們會像朋友一樣對話，一起討論主題和觀點。"
        }
    
        mode_key = mode_map[user_text]
        mode_name = user_text.replace("mode_", "").capitalize()
        description = descriptions[mode_key]
    
        if mode_key == "active":
            question = generate_active_question()
            user_state[user_id] = {
                "mode": "active",
                "last_question": question,
                "awaiting_answer": True
            }
            reply_text = f"✅ 已切換至『{mode_name}』模式\n\n{description}\n\n🧠 第一題：{question}\n\n你覺得答案是什麼？"
        else:
            reply_text = f"✅ 已切換至『{mode_name}』模式\n\n{description}"
    
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
        state = user_state.get(user_id, {})
        last_q = state.get("last_question")
        awaiting = state.get("awaiting_answer", False)
    
        def is_asking_for_answer(user_input):
            user_input = user_input.lower()
            return any(kw in user_input for kw in ["答案", "正確", "是什麼", "解答", "告訴我"])
    
        def wants_next_question(user_input):
            user_input = user_input.lower()
            return any(kw in user_input for kw in ["下一題", "下一個", "再一題", "請再給一題", "再來", "下一"])
    
        if awaiting and last_q:
            if is_asking_for_answer(user_text):
                # 使用者在問答案
                answer_prompt = f"""請針對以下 C 語言問題給出簡單明確的解釋與答案：
    
    問題：「{last_q}」
    """
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "你是一位 C 語言教學助理，請用簡單方式提供明確解答。"},
                        {"role": "user", "content": answer_prompt}
                    ]
                )
                response_text = response["choices"][0]["message"]["content"].strip()
                user_state[user_id]["awaiting_answer"] = False
                user_state[user_id]["last_question"] = None
    
            elif is_answer_related(user_text, last_q):
                # 使用者在回答問題
                answer_prompt = f"""以下是你先前問的 C 語言問題：
    「{last_q}」
    
    使用者回覆：「{user_text}」
    
    請針對他的回答給出回饋（不給答案），可鼓勵、修正錯誤、引導思考。
    """
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "你是一位 C 語言助教，請針對使用者的回答進行建設性回饋。"},
                        {"role": "user", "content": answer_prompt}
                    ]
                )
                response_text = response["choices"][0]["message"]["content"].strip()
                user_state[user_id]["awaiting_answer"] = False
                user_state[user_id]["last_question"] = None
    
            elif wants_next_question(user_text):
                # 使用者明確要求下一題
                question = generate_active_question()
                response_text = f"🧠 新挑戰來囉！\n\n❓{question}\n\n你覺得答案是什麼？"
                user_state[user_id] = {
                    "mode": "active",
                    "last_question": question,
                    "awaiting_answer": True
                }
    
            else:
                # 不是明確回答，也不是明確要下一題，提示用戶選擇
                response_text = "📝 你還沒完成上一題喔～如果你想知道答案，可以問我「這題答案是什麼？」；如果想挑戰下一題，請說「下一題」～"
    
        else:
            # 沒有問題在等待中，出新題
            question = generate_active_question()
            response_text = f"🧠 來挑戰看看這題吧：\n\n❓{question}\n\n你覺得答案是什麼？"
            user_state[user_id] = {
                "mode": "active",
                "last_question": question,
                "awaiting_answer": True
            }

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
