import re
import threading
import openai
import requests
from linebot.models import TextSendMessage

# === 設定 ===
NODE_SERVER_URL = "https://node-mongo-b008.onrender.com"
openai.api_key = "你的 OpenAI API Key（或用 app.py 設定就可省略）"

# === 🧠 等待語提示 ===
def get_waiting_message(context):
    messages = {
        "answer_feedback": "來看看你答得怎麼樣 🤔",
        "explain_answer": "讓我查查正確答案是什麼 🧐",
        "followup_concept": "好問題，我來解釋一下 ✍️",
        "next_question": "等我生一題新的出來 🎯",
        "general_chat": "我想想怎麼說比較好 🤔"
    }
    return messages.get(context, "稍等一下，我想想看 🤔")

# === 🎯 出題（依照難度） ===
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

# === 🚀 GPT 回覆並推送訊息（背景執行） ===
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

        # 儲存訊息到 MongoDB
        requests.post(f"{NODE_SERVER_URL}/save_message", json={
            "user_id": user_id,
            "message_text": "",
            "bot_response": reply_text,
            "message_type": "bot"
        }, timeout=10)

    except Exception as e:
        print(f"❌ GPT 回覆失敗：{e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="哎呀我卡住了 🥲 再問我一次好嗎？"))

# === 🧠 主動學習模式處理主函式 ===
def handle_active_mode(event, user_id, user_text, user_state, line_bot_api):
    state = user_state.get(user_id, {})
    last_q = state.get("last_question")
    awaiting = state.get("awaiting_answer", False)
    level = state.get("difficulty_level", 1)

    def is_asking_for_answer(user_input):
        return any(kw in user_input.lower() for kw in ["答案", "正確", "解答", "告訴我"])

    def wants_next_question(user_input):
        return any(kw in user_input.lower() for kw in ["下一題", "下一個", "再一題", "請再給一題", "再來", "下一"])

    def is_answer_related(user_input, question):
        abcd_set = {"a", "b", "c", "d"}
        user_input = user_input.lower().strip()
        if user_input in abcd_set:
            return True
        if re.search(r"(選|答案是|應該是)[\s]*[a-d]", user_input):
            return True
        keywords = ["printf", "int", "指標", "陣列", "return", "變數"]
        return any(kw in user_input for kw in keywords)

    def is_followup_question(user_input):
        keywords = ["為什麼", "是什麼", "代表", "差別", "怎麼", "如何", "什麼意思", "跟", "有什麼關係"]
        return any(kw in user_input.lower() for kw in keywords)

    if awaiting and last_q:
        if is_asking_for_answer(user_text):
            wait_msg = get_waiting_message("explain_answer")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
            prompt = f"請針對以下 C 語言問題給出簡單明確的解釋與答案:\n\n問題:「{last_q}」"
            threading.Thread(
                target=gpt_push_response,
                args=("explain_answer", user_id, prompt,
                      "你是一位 C 語言教學助理，請用簡單方式提供明確解答。",
                      line_bot_api)
            ).start()
            user_state[user_id].update({
                "awaiting_answer": False,
                "last_question": None,
                "responded": False,
                "irrelevant_count": 0
            })
            return

        elif wants_next_question(user_text):
            question = generate_active_question(level=level)
            wait_msg = get_waiting_message("next_question")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
            line_bot_api.push_message(user_id, TextSendMessage(text=f"Level {level} 新挑戰來囉！\n\n{question}\n\n你覺得答案是什麼？"))
            user_state[user_id].update({
                "last_question": question,
                "awaiting_answer": True,
                "responded": False,
                "irrelevant_count": 0
            })
            return

        elif is_answer_related(user_text, last_q):
            wait_msg = get_waiting_message("answer_feedback")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
            prompt = f"""以下是你先前問的 C 語言問題:
「{last_q}」

使用者回覆:「{user_text}」

請針對他的回答給出回饋（不給答案），可鼓勵、修正錯誤、引導思考。"""
            threading.Thread(
                target=gpt_push_response,
                args=("answer_feedback", user_id, prompt,
                      "你是一位 C 語言助教，請針對使用者的回答進行建設性回饋。",
                      line_bot_api)
            ).start()
            user_state[user_id]["responded"] = True
            user_state[user_id]["irrelevant_count"] = 0
            return

        elif is_followup_question(user_text):
            wait_msg = get_waiting_message("followup_concept")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
            followup_prompt = f"""你是一位 C 語言教學助教。
目前使用者正在延伸問與這題有關的概念:「{user_text}」
問題本身是:「{last_q}」
請用簡單清楚的方式回答他，不要提供原本問題的正確解答，也不要出新題。"""
            threading.Thread(
                target=gpt_push_response,
                args=("followup_concept", user_id, followup_prompt,
                      "你是一位 C 語言助教，請用鼓勵且清楚的方式解釋使用者延伸詢問的概念。",
                      line_bot_api)
            ).start()
            user_state[user_id]["irrelevant_count"] = 0
            return

        else:
            count = user_state[user_id].get("irrelevant_count", 0) + 1
            user_state[user_id]["irrelevant_count"] = count

            if user_state[user_id].get("responded") and count >= 2:
                question = generate_active_question(level=level)
                wait_msg = get_waiting_message("next_question")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
                line_bot_api.push_message(user_id, TextSendMessage(text=f"看起來這題你差不多了，來一題新的吧：\n\n{question}\n\n你覺得答案是什麼？"))
                user_state[user_id].update({
                    "last_question": question,
                    "awaiting_answer": True,
                    "responded": False,
                    "irrelevant_count": 0
                })
                return
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="我記得你還在這題喔～想聽答案可以問我「這題答案是什麼？」；想下一題可以說「下一題」！"))
                return

    else:
        question = generate_active_question(level=level)
        wait_msg = get_waiting_message("next_question")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=wait_msg))
        line_bot_api.push_message(user_id, TextSendMessage(text=f"來挑戰看看這題吧（Level {level}）：\n\n{question}\n\n你覺得答案是什麼？"))
        user_state[user_id] = {
            "mode": "active",
            "last_question": question,
            "awaiting_answer": True,
            "responded": False,
            "irrelevant_count": 0,
            "difficulty_level": level
        }
        return
