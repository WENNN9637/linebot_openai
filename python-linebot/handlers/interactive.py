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
def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api, history_messages=None):
    try:
        gpt_messages = [{"role": "system", "content": system_prompt}]
        if history_messages:
            # ✅ 過濾掉包含「回聲程序」的訊息
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

        # ✅ 將儲存動作獨立 try 避免誤判
        try:
            requests.post(f"{NODE_SERVER_URL}/save_message", json={
                "user_id": user_id,
                "message_text": "",
                "bot_response": reply_text,
                "message_type": "bot"
            }, timeout=10)
        except Exception as e:
            print(f"⚠️ 儲存訊息失敗: {e}")

    except Exception as e:
        print(f"❌ GPT 回覆失敗：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了 🥲 再問我一次好嗎？"))

# === 🗨️ 互動式模式處理主函式 ===
def handle_interactive_mode(event, user_id, user_text, line_bot_api, history):
    # 歷史簡化（只留最近幾筆有用對話）
    recent = [
        msg for msg in history
        if msg["role"] in ["user", "assistant"]
        and msg["content"].strip() not in ["", "請選擇學習模式"]
        and "回聲程序" not in msg["content"]  # ✅ 再次過濾
    ]
    short_history = recent[-3:]  # 最近三筆互動

    # 回覆等待語
    wait_msg = get_waiting_message("general_chat")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 判斷互動情境（未來可進一步分類）
    context = "interactive_learning"

    # 設計 prompt
    system_prompt = """
你是一位親切、有耐心的 C 語言學習助手，角色像是一位陪伴學生自學的教練。
請根據使用者的輸入判斷他是主動提問，還是需要引導學習（例如今天該複習什麼、動手寫練習）。

🟢 若學生主動提問：請以輕鬆口語的語氣解釋觀念、舉例、搭配簡單 C 語言程式碼。
    - 解釋不要太嚴肅，像是朋友對話。
    - 用生活比喻來幫助理解。
    - 最後加一句互動問題：例如「你看得懂這段程式嗎？」或「想自己改改看嗎？」

🔵 若學生沒有具體提問：請你主動出題或安排學習任務。
    - 可以提一個簡單的題目，或讓學生改寫某段 C 程式碼。
    - 給一些提示，不用一次講完。
    - 鼓勵學生回覆你的問題或練習結果。

⚠️ 回覆不要太長，也不要一下子講太多知識。一步一步來，引導對話。
    """

    threading.Thread(
        target=gpt_push_response,
        args=(context, user_id, user_text, system_prompt, line_bot_api, short_history)
    ).start()
