import openai
import requests
import threading
from linebot.models import TextSendMessage

# === 等待提示語 ===
def get_waiting_message(context="general_chat"):
    return {
        "general_chat": "我想想怎麼說比較好 🤔"
    }.get(context, "稍等一下，我想想看 🤔")

# === GPT 背景回覆推送（有記憶） ===
def gpt_push_response(context, user_id, user_text, system_prompt, line_bot_api, history_messages=None):
    gpt_messages = [{"role": "system", "content": system_prompt}]
    if history_messages:
        gpt_messages += history_messages  # ⬅️ 用來保留歷史記憶
    gpt_messages.append({"role": "user", "content": user_text})  # ⬅️ 新問題才是這回合的重點

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
    # 歷史簡化（只留最近幾筆有用對話）
    recent = [
        msg for msg in history
        if msg["role"] in ["user", "assistant"]
        and msg["content"].strip() not in ["", "請選擇學習模式"]
    ]
    short_history = recent[-3:]  # 最近三筆互動

    # 回覆等待語
    wait_msg = get_waiting_message("general_chat")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))

    # 判斷互動情境（未來可進一步分類）
    context = "interactive_learning"  # 你可以依據模式切換用不同 context

    # 設計 prompt（含主動、被動式學習區別）
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

    # 啟動背景 GPT 回覆
    threading.Thread(
        target=gpt_push_response,
        args=(context, user_id, user_text, system_prompt, line_bot_api, short_history)
    ).start()
#GPT 題目生成邏輯
def generate_daily_challenge_by_gpt(user_level):
    level_description = {
        "beginner": "初學者（剛接觸 C 語言，適合 if/else、變數、輸入輸出）",
        "intermediate": "中階學生（會用陣列、迴圈、函式）",
        "advanced": "進階學生（懂指標、記憶體管理、遞迴等）"
    }

    prompt = f"""
你是一位熱心、有耐心的 C 語言講師。

請根據以下程度說明，為學生出一題「當日練習題」：
- 程度：{level_description.get(user_level, '初學者')}
- 題目風格：清楚明確的中文描述，可以加入一些趣味主題（如生活化小任務）
- 不需太長，也不要超過 100 字
- 最後加一句鼓勵語，例如「寫完可以貼給我看看哦 👀」或「你會怎麼寫呢？」

只需題目內容本身，不需程式碼、解答或說明。
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        )
        question = response.choices[0].message.content.strip()
        return question
    except Exception as e:
        print(f"❌ 無法生成每日題目：{e}")
        return "今天有點塞車，明天再來挑戰吧！🚧"
#推送題目
def push_daily_challenge(user_id, user_level, line_bot_api):
    challenge = generate_daily_challenge_by_gpt(user_level)
    intro = f"🌞【每日挑戰 - {user_level.upper()}】\n\n"
    outro = "\n\n完成後可以回傳給我，我幫你看看 👍"
    
    full_message = intro + challenge + outro
    line_bot_api.push_message(user_id, TextSendMessage(text=full_message))


