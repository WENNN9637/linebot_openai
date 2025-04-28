# =============== 基本套件與初始化 ===============
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

from handlers.active import handle_active_mode
from handlers.interactive import handle_interactive_mode
from handlers.constructive import handle_constructive_mode
from handlers.passive import handle_passive_mode

import os
import openai
import re
import requests
import time
import threading

# =============== 系統初始化 ===============
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"

# =============== 使用者狀態管理 ===============
user_mode = {}
user_state = {}  # user_id: { "mode": "active", "last_question": "...", "awaiting_answer": True }

# =============== GPT回覆推送（背景處理用） ===============
def gpt_push_response(context, user_id, user_text, system_prompt, history_messages=None):
    user_prompt = user_text
    if history_messages:
        user_prompt = "\n".join([msg["content"] for msg in history_messages] + [user_text])

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        reply_text = response["choices"][0]["message"]["content"].strip()
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))

        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": "",
            "bot_response": reply_text,
            "message_type": "bot",
            "interaction_rounds": interaction_rounds  # ✅ 新增這個
        }, timeout=10)

    except Exception as e:
        print(f"❌ GPT 回覆失敗：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了 🥲 再問我一次好嗎？"))

# =============== 系統提示語對應（每種模式的等待語） ===============
def get_waiting_message(context):
    messages = {
        "answer_feedback": "來看看你答得怎麼樣",
        "explain_answer": "讓我查查正確答案是什麼...",
        "followup_concept": "好問題，我來解釋一下！",
        "next_question": "等我生一題新的出來><",
        "general_chat": "我想想怎麼說比較好..."
    }
    return messages.get(context, "稍等一下，我想想看")

# =============== GPT同步回覆版本 ===============
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

# =============== 歷史紀錄讀取（從 MongoDB） ===============
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

# =============== LINE Webhook Endpoint ===============
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

@app.route("/send_daily_challenge", methods=["POST"])
def send_daily_challenge():
    data = request.get_json()
    user_id = data.get("user_id")
    user_level = data.get("user_level", "beginner")
    day_count = data.get("day_count", 1)

    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400

    # ✅ 產生 GPT 題目
    try:
        system_prompt = (
            "你是一位親切、有耐心的 C 語言教練，擅長根據學生程度出一題小挑戰。\n"
            f"目前學生等級是：{user_level.upper()}。\n"
            "請出一題不超過 100 字的 C 語言練習題（可以是 if 判斷、迴圈、字串、指標…），用自然中文描述，盡量生活化。\n"
            "最後加一句鼓勵，例如「你會怎麼做？」或「寫完可以傳給我看看哦 👀」\n"
            "不需要提供答案。"
        )
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "請給我一題每日挑戰題"}
            ]
        )
        challenge_text = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ GPT 題目生成失敗: {e}")
        return jsonify({"error": "GPT 失敗"}), 500

    # ✅ 組合訊息
    message = (
        f"【每日挑戰 - {user_level.upper()}】\n"
        f"#Day{day_count}\n\n"
        f"{challenge_text}\n\n"
        "完成後回傳給我，我幫你看看是否正確"
    )

    # ✅ 發送到 LINE
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
        save_to_mongo(user_id, bot_msg=message)
    except Exception as e:
        print(f"❌ LINE 推送失敗: {e}")
        return jsonify({"error": "LINE 發送失敗"}), 500

    return jsonify({"status": "success", "sent_to": user_id})

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

def save_to_mongo(user_id, user_msg=None, bot_msg=None):
    """儲存對話資料到 MongoDB，可選擇儲存 user 或 bot"""
    try:
        if user_msg:
            requests.post(f"{NODE_SERVER_URL}/save_message", json={
                "user_id": user_id,
                "message_text": user_msg,
                "bot_response": "",
                "message_type": "text"
            }, timeout=10)
            print(f"✅ 儲存使用者訊息: {user_msg}")
        if bot_msg:
            requests.post(f"{NODE_SERVER_URL}/save_message", json={
                "user_id": user_id,
                "message_text": "",
                "bot_response": bot_msg,
                "message_type": "bot"
            }, timeout=10)
            print(f"✅ 儲存 AI 回覆: {bot_msg}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 儲存訊息失敗: {e}")

# =============== 接收使用者訊息 ===============
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    print(f"💬 收到來自 {user_id} 的訊息: {user_text}")

    # 儲存使用者輸入（不管是哪一種模式）
    save_to_mongo(user_id, user_msg=user_text)

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
            reply_text = f"已切換至『{mode_name}』模式\n\n{description}\n\n第一題：{question}\n\n你覺得答案是什麼？"
        else:
            reply_text = f"已切換至『{mode_name}』模式\n\n{description}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        save_to_mongo(user_id, bot_msg=reply_text)
        return

    # 取得使用者目前模式
    mode = user_mode.get(user_id, "passive")
    print(f"用戶 {user_id} 的目前模式：{mode}")

    # 載入歷史訊息（用於有上下文的模式）
    history = load_history(user_id)
    messages = [{"role": "system", "content": "你是一位專業的 C 語言學習助教，擅長根據上下文進行回答，避免重複主題。"}]
    for msg in sorted(history.get("messages", []), key=lambda x: x.get("timestamp", "")):
        if msg.get("message_text"):
            messages.append({"role": "user", "content": msg["message_text"]})
        elif msg.get("bot_response"):
            messages.append({"role": "assistant", "content": msg["bot_response"]})

    # 模式處理
    if mode == "passive":
        handle_passive_mode(event, user_id, user_text, line_bot_api)
        return

    elif mode == "constructive":
        handle_constructive_mode(event, user_id, user_text, line_bot_api)
        return

    
    elif mode == "interactive":
        handle_interactive_mode(event, user_id, user_text, line_bot_api, messages)
        return

    elif mode == "active":
        handle_active_mode(event, user_id, user_text, user_state, line_bot_api)
        return
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="未知模式，請重新選擇 \n請輸入「模式」或點選選單選擇學習模式。")
        )
        return


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
