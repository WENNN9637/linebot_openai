from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai

app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')

# 紀錄使用者的學習模式
user_mode = {}
@app.route("/health", methods=['GET'])
def health_check():
    return "OK", 200  # 讓 Render 知道伺服器正常運行，不觸發 OpenAI API
    
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(403)
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 當用戶加入好友時，發送學習模式選單
@handler.add(FollowEvent)
def send_welcome(event):
    user_id = event.source.user_id
    user_mode[user_id] = "passive"  # 預設模式為被動模式
    send_mode_selection(user_id)

# 送出學習模式選擇的 Flex Message
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
    prompt = "請產生一個具有挑戰性的問題，適合讓學習者思考並回答。問題應該與學習、科技或邏輯思考相關。"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "你是一個智慧型學習助手，會主動提出有趣的問題來幫助使用者學習。"},
                  {"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

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
    prompt = f"使用者說：「{user_input}」，請根據這個內容引導使用者提供更具體的想法，例如詢問他們的觀點或細節。"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "你是一個引導式學習助手，會幫助使用者深入思考。"},
                  {"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()

    # 檢查是否是模式切換指令
    mode_map = {
        "mode_passive": "passive",
        "mode_active": "active",
        "mode_constructive": "constructive",
        "mode_interactive": "interactive"
    }

    if user_text in mode_map:
        user_mode[user_id] = mode_map[user_text]
        reply_text = f"已切換至『{user_text.replace('mode_', '').capitalize()}』模式"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        return

    # 取得使用者當前模式，預設為被動模式
    mode = user_mode.get(user_id, "passive")
    print(f"用戶 {user_id} 的目前模式：{mode}")

    # **被動模式 (等使用者問問題才回應)**
    if mode == "passive":
        response_text = generate_interactive_response(user_text)  # 無條件使用 AI 生成回應


    # **主動模式 (自動提問)**
    elif mode == "active":
        new_question = generate_active_question()
        response_text = f"來挑戰一下吧！\n\n{new_question}"

    # **建構模式 (引導使用者提供看法)**
    elif mode == "constructive":
        if len(user_text) < 10:  # 若使用者輸入太短，先引導
            response_text = generate_constructive_prompt(user_text)
        else:  # 若輸入足夠，進一步討論
            response_text = f"你剛剛提到：「{user_text}」，這很有趣！我們來深入討論一下，請問你的具體想法是什麼？"

    # **互動模式 (雙向對話)**
    elif mode == "interactive":
        response_text = generate_interactive_response(user_text)

    else:
        response_text = "未知模式，請重新選擇。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
