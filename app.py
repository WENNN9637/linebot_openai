from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os, time, openai

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')

# 紀錄使用者的模式（模擬資料庫）
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

# 回應 Flex Message 按鈕
@handler.add(FollowEvent)
def send_welcome(event):
    user_id = event.source.user_id
    user_mode[user_id] = "Passive"
    send_mode_selection(user_id)

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
                     "action": {"type": "postback", "label": "互動式 (Interactive)", "data": "mode:Interactive"}},
                    {"type": "button", "style": "primary", "color": "#FFB74D",
                     "action": {"type": "postback", "label": "建構式 (Constructive)", "data": "mode:Constructive"}},
                    {"type": "button", "style": "primary", "color": "#42A5F5",
                     "action": {"type": "postback", "label": "主動式 (Active)", "data": "mode:Active"}},
                    {"type": "button", "style": "primary", "color": "#9E9E9E",
                     "action": {"type": "postback", "label": "被動式 (Passive)", "data": "mode:Passive"}}
                ]
            }
        }
    )
    line_bot_api.push_message(user_id, flex_message)

# 處理按鈕回應
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    if data.startswith("mode:"):
        mode = data.split(":")[1]
        user_mode[user_id] = mode
        line_bot_api.reply_message(event.reply_token, TextSendMessage(f"已切換至 {mode} 模式！"))

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    mode = user_mode.get(user_id, "Passive")
    user_text = event.message.text
    
    if mode == "Passive":
        response_text = "這是基本資訊：\n" + user_text[:50]
    elif mode == "Active":
        response_text = "這是你的問題，我有個問題給你：\n" + user_text + "\n\n你覺得這跟現實生活有關嗎？"
    elif mode == "Constructive":
        response_text = "請先說說你的想法？\n" + user_text + "\n\n然後我們可以一起討論！"
    else:  # Interactive
        response_text = "我們來對話！\n\n你問：" + user_text + "\n\n你覺得這個問題有什麼不同的解法？"
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
