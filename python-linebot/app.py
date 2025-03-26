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

def get_waiting_message(context):
    messages = {
        "answer_feedback": "來看看你答得怎麼樣 🤔",
        "explain_answer": "讓我查查正確答案是什麼 🧐",
        "followup_concept": "好問題，我來解釋一下 ✍️",
        "next_question": "等我生一題新的出來 🎯",
        "general_chat": "我想想怎麼說比較好 🤔"
    }
    return messages.get(context, "稍等一下，我想想看 🤔")

def gpt_with_typing(context, user_id, reply_token, system_prompt, user_prompt):
    wait_msg = get_waiting_message(context)
    line_bot_api.reply_message(reply_token, TextSendMessage(text=wait_msg))

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    reply_text = response["choices"][0]["message"]["content"].strip()
    line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
    return reply_text

def load_history(user_id, retries=3, delay=3):
    url = f"{NODE_SERVER_URL}/get_history"
    for attempt in range(retries):
        try:
            response = requests.get(url, params={"user_id": user_id, "limit": 10}, timeout=30)
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

    mode = user_mode.get(user_id, "passive")
    print(f"用戶 {user_id} 的目前模式：{mode}")

    history = load_history(user_id)
    messages = [{"role": "system", "content": "你是一個智慧助理，請記住使用者的對話歷史。"}]
    
    for msg in sorted(history.get("messages", []), key=lambda x: x.get("timestamp", "")):
        if msg.get("message_text"):
            messages.append({"role": "user", "content": msg["message_text"]})
        elif msg.get("bot_response"):
            messages.append({"role": "assistant", "content": msg["bot_response"]})
    if mode == "passive":
        # 被動模式：使用 gpt_with_typing 回覆
        response_text = gpt_with_typing(
            context="general_chat",
            user_id=user_id,
            reply_token=event.reply_token,
            system_prompt="你是一位具有歷史記憶的 C 語言助教，請以自然有耐心的方式回應。",
            user_prompt=user_text
        )

    elif mode == "interactive":
        recent = [
            msg for msg in messages
            if msg["role"] in ["user", "assistant"] and msg["content"].strip() not in ["", "請選擇學習模式"]
        ]
        short_history = recent[-3:]
        short_history.append({"role": "user", "content": user_text})

        joined_prompt = "\n".join([msg["content"] for msg in short_history])

        response_text = gpt_with_typing(
            context="general_chat",
            user_id=user_id,
            reply_token=event.reply_token,
            system_prompt="""
你是一位熱心、有耐心的 C 語言學習夥伴，會用自然、口語的方式與使用者互動。
請根據使用者「最近的提問內容」，做出清楚但輕鬆的回答。
""",
            user_prompt=joined_prompt
        )

    elif mode == "constructive":
        explanation = gpt_with_typing(
            context="general_chat",
            user_id=user_id,
            reply_token=event.reply_token,
            system_prompt="你是一位 C 語言助教，請自然地解釋以下使用者說的內容：",
            user_prompt=user_text
        )

        followup = gpt_with_typing(
            context="answer_feedback",
            user_id=user_id,
            reply_token=event.reply_token,
            system_prompt="你是一位擅長引導學習的助教，請提出一個有深度的追問。",
            user_prompt=f"針對這段回應：「{user_text}」，請提出一個追問。"
        )

        response_text = f"{explanation}\n\n{followup}"
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

        def is_followup_question(user_input):
            user_input = user_input.lower()
            return any(kw in user_input for kw in ["為什麼", "是什麼", "代表", "差別", "怎麼", "如何", "什麼意思", "跟", "有什麼關係"])

        if awaiting and last_q:
            if is_asking_for_answer(user_text):
                response_text = gpt_with_typing(
                    context="explain_answer",
                    user_id=user_id,
                    reply_token=event.reply_token,
                    system_prompt="你是一位 C 語言教學助理，請用簡單方式提供明確解答。",
                    user_prompt=f"請針對以下 C 語言問題給出簡單明確的解釋與答案：\n\n問題：「{last_q}」"
                )
                user_state[user_id].update({
                    "awaiting_answer": False,
                    "last_question": None,
                    "responded": False,
                    "irrelevant_count": 0
                })

            elif wants_next_question(user_text):
                question = generate_active_question(level=level)
                response_text = f"Level {level} 新挑戰來囉！\n\n{question}\n\n你覺得答案是什麼？"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_waiting_message("next_question")))
                line_bot_api.push_message(user_id, TextSendMessage(text=response_text))
                user_state[user_id].update({
                    "last_question": question,
                    "awaiting_answer": True,
                    "responded": False,
                    "irrelevant_count": 0
                })
                return

            elif is_answer_related(user_text, last_q):
                response_text = gpt_with_typing(
                    context="answer_feedback",
                    user_id=user_id,
                    reply_token=event.reply_token,
                    system_prompt="你是一位 C 語言助教，請針對使用者的回答進行建設性回饋。",
                    user_prompt=f"""以下是你先前問的 C 語言問題：
「{last_q}」

使用者回覆：「{user_text}」

請針對他的回答給出回饋（不給答案），可鼓勵、修正錯誤、引導思考。"""
                )
                user_state[user_id]["responded"] = True
                user_state[user_id]["irrelevant_count"] = 0

                # 自動調整難度
                if "答對" in response_text or "正確" in response_text:
                    user_state[user_id]["difficulty_level"] = min(level + 1, 3)
                else:
                    user_state[user_id]["difficulty_level"] = max(level - 1, 1)

            elif is_followup_question(user_text):
                response_text = gpt_with_typing(
                    context="followup_concept",
                    user_id=user_id,
                    reply_token=event.reply_token,
                    system_prompt="你是一位 C 語言助教，請用鼓勵且清楚的方式解釋使用者延伸詢問的概念。",
                    user_prompt=f"""你是一位 C 語言教學助教。
目前使用者正在延伸問與這題有關的概念：「{user_text}」
問題本身是：「{last_q}」
請用簡單清楚的方式回答他，不要提供原本問題的正確解答，也不要出新題。"""
                )
                user_state[user_id]["irrelevant_count"] = 0

            else:
                count = user_state[user_id].get("irrelevant_count", 0) + 1
                user_state[user_id]["irrelevant_count"] = count

                if user_state[user_id].get("responded") and count >= 2:
                    question = generate_active_question(level=level)
                    response_text = f"看起來這題你差不多了，來一題新的吧：\n\n{question}\n\n你覺得答案是什麼？"
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_waiting_message("next_question")))
                    line_bot_api.push_message(user_id, TextSendMessage(text=response_text))
                    user_state[user_id].update({
                        "last_question": question,
                        "awaiting_answer": True,
                        "responded": False,
                        "irrelevant_count": 0
                    })
                    return
                else:
                    response_text = "我記得你還在這題喔～想聽答案可以問我「這題答案是什麼？」；想下一題可以說「下一題」！"
        else:
            question = generate_active_question(level=level)
            response_text = f"來挑戰看看這題吧（Level {level}）：\n\n{question}\n\n你覺得答案是什麼？"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_waiting_message("next_question")))
            line_bot_api.push_message(user_id, TextSendMessage(text=response_text))
            user_state[user_id] = {
                "mode": "active",
                "last_question": question,
                "awaiting_answer": True,
                "responded": False,
                "irrelevant_count": 0,
                "difficulty_level": level
            }
            return
    # 儲存使用者輸入
    try:
        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": user_text,
            "bot_response": "",
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
                "message_text": "",
                "bot_response": response_text,
                "message_type": "bot"
            }, timeout=10)
            print(f"✅ 儲存 AI 回覆: {response_text}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 儲存 AI 回覆失敗: {e}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
