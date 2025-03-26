from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai
import requests
import time

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
user_mode = {}
user_state = {}  # user_id: { "mode": "active", "last_question": "...", "awaiting_answer": True }


def load_history(user_id, retries=3, delay=3):
    url = f"{NODE_SERVER_URL}/get_history"
    for attempt in range(retries):
        try:
            response = requests.get(url, params={"user_id": user_id, "limit": 10}, timeout=10)
            response.raise_for_status()
            data = response.json()
            print(f"✅ 第 {attempt+1} 次嘗試成功取得歷史訊息")
            return data if "messages" in data else {"messages": []}
        except requests.exceptions.RequestException as e:
            print(f"❌ API 讀取失敗 ({attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    print("⚠️ 多次重試後仍失敗，返回空歷史訊息")
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
            """try:
                response = requests.post(f"{NODE_SERVER_URL}/save_message", json=message_data)
                print("📤 發送至 Node.js:", response.status_code, response.text)
            except requests.exceptions.RequestException as e:
                print(f"❌ 儲存失敗: {e}")"""

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
def generate_active_question(level=1):
    system_message = (
        "你是一位 C 語言教學助手，會根據題目難度產生挑戰性問題。\n"
        "Level 1：選擇題（簡單）\n"
        "Level 2：填空題（中等）\n"
        "Level 3：簡答題（進階）\n"
        "這些難度資訊只用於內部控制，請勿顯示給使用者。\n"
        "出題範圍從 C 語言基本語法、變數、流程控制，到進階如指標與迴圈。"
    )

    user_prompt = (
        f"請產生一題 C 語言的問題，難度為 Level {level}。\n"
        "請從選擇題、填空題、簡答題中擇一產生，幫助學習者思考。\n"
        "不要提供答案。"
    )

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt}
        ]
    )

    return response["choices"][0]["message"]["content"].strip()


# 產生互動式對話
def generate_interactive_response(conversation):
    """
    conversation: List of dicts (e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}])
    """

    system_prompt = """
你是一位熱心、有耐心的 C 語言學習夥伴，會用自然、口語的方式與使用者互動。

請根據使用者「最近的提問內容」，做出清楚但輕鬆的回答。
即使之前講過某個主題，若使用者切換話題，請優先回應「目前的提問」。

請避免重複使用者的語句，盡量提供實際說明、比喻、或簡單的程式碼範例。

最後可以加上一句反問，引導使用者繼續思考，例如：
- 你有遇過這樣的情況嗎？
- 如果是你會怎麼寫？
- 這樣的設計你覺得有什麼風險？

請用像朋友一樣聊天的語氣。
"""

    messages = [{"role": "system", "content": system_prompt}] + conversation

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=500,
        timeout=20
    )
    return response["choices"][0]["message"]["content"].strip()


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
        messages.insert(0, {
            "role": "system",
            "content": (
                "你是一個具有對話歷史記憶能力的 C 語言教學助手。"
                "你會根據使用者的過去提問與回答記錄進行回應。"
                "請使用繁體中文或英文回答，不要使用簡體中文。"
                "如果使用者問你是否有記憶，請說你會記得最近的對話紀錄，但不會永久保存。"
                "請以自然、有耐心的語氣回應。"
            )
        })
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
    keywords = ["答案", "是什麼", "不懂", "為什麼", "我覺得", "我猜", "可能", "因為", "應該", "嗎", "不太懂", "可以", "幫我"]
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
            reply_text = f"✅ 已切換至『{mode_name}』模式\n\n{description}\n\n第一題：{question}\n\n你覺得答案是什麼？"
        else:
            reply_text = f"✅ 已切換至『{mode_name}』模式\n\n{description}"
    
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        return

    # **📌 取得使用者當前模式，預設為被動模式**
    mode = user_mode.get(user_id, "passive")
    print(f"用戶 {user_id} 的目前模式：{mode}")

    history = load_history(user_id)
    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    
    # 取得歷史對話，按時間順序組合 user 和 bot 的訊息
    for msg in sorted(history.get("messages", []), key=lambda x: x.get("timestamp", "")):
        if msg.get("message_text"):
            messages.append({"role": "user", "content": msg["message_text"]})
        elif msg.get("bot_response"):
            messages.append({"role": "assistant", "content": msg["bot_response"]})


    # **📌 根據模式來選擇 AI 互動方式**
    if mode == "passive":
        history = load_history(user_id)
        messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    
        # 加入歷史訊息
        for msg in sorted(history.get("messages", []), key=lambda x: x.get("timestamp", "")):
            if msg.get("message_text"):
                messages.append({"role": "user", "content": msg["message_text"]})
            elif msg.get("bot_response"):
                messages.append({"role": "assistant", "content": msg["bot_response"]})
    
        # ✅ 加入目前輸入（關鍵！）
        messages.append({"role": "user", "content": user_text})
        response_text = GPT_response(messages)
        
    elif mode == "active":
        state = user_state.get(user_id, {})
        last_q = state.get("last_question")
        awaiting = state.get("awaiting_answer", False)
        level = state.get("difficulty_level", 1)
    
        def is_asking_for_answer(user_input):
            user_input = user_input.lower()
            return any(kw in user_input for kw in ["答案", "正確", "解答", "告訴我"])
    
        def wants_next_question(user_input):
            user_input = user_input.lower()
            return any(kw in user_input for kw in ["下一題", "下一個", "再一題", "請再給一題", "再來", "下一"])
    
        def is_answer_related(user_input, question):
            user_input = user_input.strip().lower()
            abcd_set = {"a", "b", "c", "d"}
            if user_input in abcd_set:
                return True
            if re.search(r"(選|答案是|應該是)[\s]*[a-d]", user_input):
                return True
            keywords = ["printf", "int", "指標", "陣列", "return", "變數"]
            return any(kw in user_input for kw in keywords)
    
        if awaiting and last_q:
            if is_asking_for_answer(user_text):
                # 使用者問答案，給出解釋與正解，重設狀態
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
                user_state[user_id].update({
                    "awaiting_answer": False,
                    "last_question": None,
                    "responded": False,
                    "irrelevant_count": 0
                })
    
            elif wants_next_question(user_text):
                # 使用者主動要求下一題，使用當前難度
                question = generate_active_question(level=level)
                response_text = f"Level {level} 新挑戰來囉！\n\n{question}\n\n你覺得答案是什麼？"
                user_state[user_id].update({
                    "last_question": question,
                    "awaiting_answer": True,
                    "responded": False,
                    "irrelevant_count": 0
                })
    
            elif is_answer_related(user_text, last_q):
                # 使用者回答問題，進行回饋（不給正解）
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
                user_state[user_id]["responded"] = True
                user_state[user_id]["irrelevant_count"] = 0
    
                # 🔁 根據 GPT 回饋內容決定是否調整難度
                if "答對" in response_text or "正確" in response_text:
                    new_level = min(level + 1, 3)
                else:
                    new_level = max(level - 1, 1)
                user_state[user_id]["difficulty_level"] = new_level
    
            else:
                # 無關輸入，若已回應則累積跳題次數
                count = user_state[user_id].get("irrelevant_count", 0) + 1
                user_state[user_id]["irrelevant_count"] = count
    
                if user_state[user_id].get("responded") and count >= 2:
                    level = user_state[user_id].get("difficulty_level", 1)
                    question = generate_active_question(level=level)
                    response_text = f"看起來這題你差不多了，來一題新的吧：\n\n{question}\n\n你覺得答案是什麼？"
                    user_state[user_id].update({
                        "last_question": question,
                        "awaiting_answer": True,
                        "responded": False,
                        "irrelevant_count": 0
                    })
                else:
                    response_text = "我記得你還在這題喔～想聽答案可以問我「這題答案是什麼？」；想下一題可以說「下一題」！"
    
        else:
            # 新使用者或主動進入 active 模式
            level = state.get("difficulty_level", 1)
            question = generate_active_question(level=level)
            response_text = f"來挑戰看看這題吧（Level {level}）：\n\n{question}\n\n你覺得答案是什麼？"
            user_state[user_id] = {
                "mode": "active",
                "last_question": question,
                "awaiting_answer": True,
                "responded": False,
                "irrelevant_count": 0,
                "difficulty_level": level
            }

    elif mode == "interactive":
        # 取最近 4 筆對話（含使用者輸入與 AI 回應）
        recent = [
            msg for msg in messages
            if msg["role"] in ["user", "assistant"] and msg["content"].strip() not in ["", "請選擇學習模式"]
        ]
        short_history = recent[-3:]  # 留 3 則歷史（太多沒意義）
        short_history.append({"role": "user", "content": user_text})  # 現在輸入強制加入
        response_text = generate_interactive_response(short_history)
    
    
    elif mode == "constructive":
        explanation = generate_interactive_response([{"role": "user", "content": user_text}])
        followup = generate_constructive_prompt(user_text)
        response_text = f"{explanation}\n\n{followup}"
    else:
        response_text = "未知模式，請重新選擇。"
        
    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))
    # 儲存使用者輸入
    try:
        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": user_text,
            "bot_response": "",  # 使用者輸入不包含 bot_response
            "message_type": "text"
        }, timeout=10)
        print(f"✅ 儲存使用者訊息: {user_text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 儲存使用者訊息失敗: {e}")
    
    # 儲存 AI 回覆
    if response_text.strip():
        try:
            requests.post(f"{NODE_SERVER_URL}/save_message", json={
                "user_id": user_id,
                "message_text": "",  # AI 沒有 user text
                "bot_response": response_text,
                "message_type": "bot"
            }, timeout=10)
            print(f"✅ 儲存 AI 回覆: {response_text}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 儲存 AI 回覆失敗: {e}")


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
