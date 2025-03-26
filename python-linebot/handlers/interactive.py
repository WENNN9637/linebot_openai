import openai
import requests
import threading
from linebot.models import TextSendMessage

# === 設定 ===
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
openai.api_key = "你的 OpenAI API Key（可省略用 app.py）"

# === 等待提示語 ===
def get_waiting_message(context="general_chat"):
    return {
        "general_chat": "我想想怎麼說比較好 🤔"
    }.get(context, "稍等一下，我想想看 🤔")

# === GPT 背景回覆推送（有記憶） ===
def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api, history_messages=None):
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
            "message_type": "bot"
        }, timeout=10)

    except Exception as e:
        print(f"❌ GPT 回覆失敗：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了 🥲 再問我一次好嗎？"))

# === 🗨️ 互動式模式處理主函式 ===
def handle_interactive_mode(event, user_id, user_text, line_bot_api, history):
    # 整理歷史對話
    recent = [
        msg for msg in history
        if msg["role"] in ["user", "assistant"] and msg["content"].strip() not in ["", "請選擇學習模式"]
    ]
    short_history = recent[-3:]  # 留最近 3 筆

    # 🔔 回覆等待訊息
    wait_msg = get_waiting_message("general_chat")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 💾 儲存使用者輸入
    try:
        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": user_text,
            "bot_response": "",
            "message_type": "text"
        }, timeout=10)
        print(f"✅ [Interactive Mode] 儲存使用者輸入：{user_text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ [Interactive Mode] 儲存使用者輸入失敗：{e}")

    # 🧠 建立 prompt
    system_prompt = (
        "你是一位熱心、有耐心的 C 語言學習夥伴，會用自然、口語的方式與使用者互動。\n"
        "請根據使用者最近提問內容，清楚但輕鬆地回答。\n"
        "可舉例、比喻、給程式碼，但不要太正式。\n"
        "最後加一句反問：例如「你會怎麼做？」或「這樣合理嗎？」"
    )

    # ✅ 開啟背景回覆執行緒
    threading.Thread(
        target=gpt_push_response,
        args=("general_chat", user_id, user_text, system_prompt, line_bot_api, short_history)
    ).start()

