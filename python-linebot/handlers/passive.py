import threading
import openai
import requests
from linebot.models import TextSendMessage



def get_waiting_message(context="general_chat"):
    return {
        "general_chat": "我想想怎麼說比較好 🤔"
    }.get(context, "稍等一下，我想想看 🤔")

def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ]
        )
        reply_text = response["choices"][0]["message"]["content"].strip()

        print("✅ GPT 回覆成功：", reply_text)

        # 嘗試推播訊息
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
        print("✅ LINE 推送成功")

        # 儲存到資料庫
        res = requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": "",
            "bot_response": reply_text,
            "message_type": "bot"
        }, timeout=10)
        print("✅ 儲存成功", res.status_code)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Passive 回覆錯誤：{type(e)} → {e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了，再問一次看看 🥲"))


def handle_passive_mode(event, user_id, user_text, line_bot_api):
    wait_msg = get_waiting_message()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 在這個檔案裡不需要儲存 user_text，統一由 app.py 處理

    # 開始背景回覆
    threading.Thread(
        target=gpt_push_response,
        args=(
            "general_chat",
            user_id,
            user_text,
            """
            你是一位具有歷史記憶、親切且會主動協助學習的 C 語言助教。你不只回答問題，還會根據使用者的興趣或問題內容，自然地提供補充知識、範例、相關主題延伸閱讀，甚至偶爾插入趣味語法冷知識。
            
            你可以：
            - 推薦學習資源
            - 提供類似主題
            - 鼓勵與提醒複習
            - 偶爾主動推送知識點（如每日一句）
            """,
            line_bot_api
        )
    ).start()
