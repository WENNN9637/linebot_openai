import openai
import requests
import threading
import os
from linebot.models import TextSendMessage


# === 等待提示語 ===
def get_waiting_message(context="general_chat"):
    return {
        "general_chat": "我想想怎麼說比較好 🤔"
    }.get(context, "稍等一下，我想想看 🤔")

# === GPT 背景回覆推送（有記憶） ===
# === 改良版 GPT 背景回覆推送（含互動追蹤） ===
def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api, history_messages=None):
    try:
        gpt_messages = [{"role": "system", "content": system_prompt}]
        if history_messages:
            filtered_history = [
                msg for msg in history_messages
                if "回聲程序" not in msg["content"]
            ]
            gpt_messages += filtered_history

        gpt_messages.append({"role": "user", "content": user_text})

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=gpt_messages
        )
        reply_text = response["choices"][0]["message"]["content"].strip()
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))

        # ✅ 記錄互動回合數
        interaction_rounds = len([msg for msg in history_messages if msg["role"] == "user"]) if history_messages else 0
        interaction_rounds += 1  # 加上這一回合

        # ✅ 判斷是否有建設性貢獻
        constructive_contribution = len(user_text.strip()) > 5  # 回覆內容要有5字以上才算有建設性（可再細化判斷）

        # ✅ 儲存互動紀錄
        try:
            requests.post(f"{NODE_SERVER_URL}/save_message", json={
                "user_id": user_id,
                "message_text": user_text,
                "bot_response": reply_text,
                "message_type": "bot",
                "interaction_rounds": interaction_rounds,
                "constructive_contribution": constructive_contribution
            }, timeout=10)
        except Exception as e:
            print(f"⚠️ 儲存訊息失敗: {e}")

    except Exception as e:
        print(f"❌ GPT 回覆失敗：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了 🥲 再問我一次好嗎？"))

# === 🗨️ 互動式模式處理主函式 ===
# === 🗨️ 改良版互動式模式處理主函式 ===
def handle_interactive_mode(event, user_id, user_text, line_bot_api, history):
    # 🛠 修正版：正確建構有 role 的歷史資料
    messages = [{"role": "system", "content": "你是一位專業的 C 語言學習助教，擅長根據上下文進行回答，避免重複主題。"}]
    
    for msg in sorted(history.get("messages", []), key=lambda x: x.get("timestamp", "")):
        if msg.get("message_text"):
            messages.append({"role": "user", "content": msg["message_text"]})
        elif msg.get("bot_response"):
            messages.append({"role": "assistant", "content": msg["bot_response"]})

    # 🔥 這時 messages 就是完整歷史：有 user、有 bot
    short_history = messages[-4:]  # 最近四筆有用互動
    
    # 送出等待提示
    wait_msg = get_waiting_message("general_chat")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 判斷互動情境
    context = "interactive_learning"

    # 設計更互動式 prompt
    system_prompt = """
你是一位親切、有耐心的 C 語言學習教練，目標是促進學生主動學習和建設性對話。

🟢 如果學生主動提問：簡單解釋 + 舉例 + 提問（鼓勵學生延伸自己的例子或想法）
    - 語氣輕鬆，像朋友聊天。
    - 最後用一句引導問題，比如：「你可以試著寫一個類似的嗎？」、「那如果改成XXX會怎樣？」

🔵 如果學生沒有具體提問：主動給一個簡單小挑戰或修改任務。
    - 題目要有開放性，引導學生思考不同做法。
    - 每次只給一點提示，根據學生回覆調整難度。

⚡ 特別注意：
    - 引導學生【具體回答】，例如：自己寫程式片段、舉生活例子、解釋自己的理解。
    - 互動過程要有3次以上的來回才算一次完整互動。
    - 針對學生回應內容，給出正向回饋或追問細節。

請用這個互動策略回應學生！
    """

    # 開背景執行，推送 GPT 回覆
    threading.Thread(
        target=gpt_push_response,
        args=(context, user_id, user_text, system_prompt, line_bot_api, short_history)
    ).start()
