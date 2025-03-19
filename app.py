from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, openai

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')

# 紀錄使用者的學習模式
user_mode = {}

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
    user_mode[user_id] = "passive"  # ✅ 設定新用戶的預設模式
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
                     "action": {"type": "postback", "label": "互動式 (Interactive)", "data": "mode_interactive"}},
                    {"type": "button", "style": "primary", "color": "#FFB74D",
                     "action": {"type": "postback", "label": "建構式 (Constructive)", "data": "mode_constructive"}},
                    {"type": "button", "style": "primary", "color": "#42A5F5",
                     "action": {"type": "postback", "label": "主動式 (Active)", "data": "mode_active"}},
                    {"type": "button", "style": "primary", "color": "#9E9E9E",
                     "action": {"type": "postback", "label": "被動式 (Passive)", "data": "mode_passive"}}
                ]
            }
        }
    )
    line_bot_api.push_message(user_id, flex_message)

# ✅ 新增處理 Postback 事件的函數
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data  # 取得按鈕的 data 值

    mode_map = {
        "mode_passive": "passive",
        "mode_active": "active",
        "mode_constructive": "constructive",
        "mode_interactive": "interactive"
    }

    if data in mode_map:
        user_mode[user_id] = mode_map[data]  # ✅ 更新該使用者的模式
        reply_text = f"✅ 已切換至『{data.replace('mode_', '').capitalize()} 模式』"
    else:
        reply_text = "⚠️ 未知的模式，請重新選擇。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))

# ✅ 使用者發送訊息時的回應
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()  # 取得使用者輸入的文字並去掉前後空格

    # ✅ 確保 `user_mode[user_id]` 有值，否則預設為 "passive"
    mode = user_mode.get(user_id, "passive")
    print(f"🛠 用戶 {user_id} 的目前模式：{mode}")  # ✅ 確認模式是否讀取成功

    # ✅ 根據不同模式回應不同的訊息
    if mode == "passive":
        response_text = "📌 這是基本資訊：\n" + user_text[:50]

    elif mode == "active":
        response_text = f"🤔 這是你的問題，我有個問題給你：\n{user_text}\n\n你覺得這跟現實生活有關嗎？"

    elif mode == "constructive":
        response_text = f"💡 這是 C 語言相關知識：\n{user_text}\n\n我們可以進一步探討這段程式碼！"

    elif mode == "interactive":
        response_text = f"🗣️ 我們來對話！\n\n你問：{user_text}\n\n你覺得這個問題有什麼不同的解法？"

    else:
        response_text = "⚠️ 未知模式，請重新選擇。"

    # ✅ 傳送回應
    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
