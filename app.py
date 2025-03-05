from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import *

#======python的函數庫==========
import tempfile, os
import datetime
import openai
import time
import traceback
#======python的函數庫==========

app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')
# Channel Access Token
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
# Channel Secret
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
# OPENAI API Key初始化設定
openai.api_key = os.getenv('OPENAI_API_KEY')

last_call_time = 0  # 記錄上次 API 調用時間
API_COOLDOWN = 5  # 設定 5 秒冷卻時間
def is_c_language(text):
    c_keywords = ["#include", "int ", "void ", "printf(", "scanf(", "return", "malloc", "free", "sizeof", "struct ", "typedef ", "->", "::", "main()"]
    return any(keyword in text for keyword in c_keywords)
def GPT_response(text):
    global last_call_time
    # 設定最短間隔，避免連續請求
    if time.time() - last_call_time < API_COOLDOWN:
        return "請稍後再試！"
    
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(text) else "gpt-4o"
    
    response = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": "你只能使用繁體中文或英文回答。"},
            {"role": "user", "content": text}
        ],
        max_tokens=500,
        timeout=30
    )
        
    last_call_time = time.time()  # 更新最後請求時間
    return response["choices"][0]["message"]["content"].strip()


"""
def GPT_response(text):
    # 如果是 C 語言問題，就用微調模型，否則用 GPT-4o
    model = "ft:gpt-4o-2024-08-06:personal::B5sbnkYa" if is_c_language(text) else "gpt-4o"
    
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": text}],
        max_tokens=500,
        timeout=30
    )
    
    return response["choices"][0]["message"]["content"].strip()

def GPT_response(text):
    # 接收回應
    response = openai.ChatCompletion.create(
        model="gpt-4o", 
        messages=[
            {"role": "user", "content": text},
        ],
        max_tokens=500,
        timeout=30
    )
    
    # 重組回應
    answer = response["choices"][0]["message"]["content"]
    return answer
"""
@app.route("/health", methods=['GET'])
def health_check():
    return "OK", 200  # 讓 Render 知道伺服器正常運行，不觸發 OpenAI API
    
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(403)  # 直接拒絕非 LINE 來源的請求
    
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'



# 處理訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text

    # 記錄用戶的最後請求時間，避免連續觸發
    user_id = event.source.user_id
    global last_call_time

    # 5 秒內的重複請求直接忽略
    if time.time() - last_call_time < 5:
        line_bot_api.reply_message(event.reply_token, TextSendMessage("請稍後再試！"))
        return
    
    try:
        GPT_answer = GPT_response(msg)
        print(GPT_answer)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(GPT_answer))
        last_call_time = time.time()  # 更新最後請求時間
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage("系統錯誤，請稍後再試！"))

@handler.add(PostbackEvent)
def handle_message(event):
    print(event.postback.data)


@handler.add(MemberJoinedEvent)
def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    line_bot_api.reply_message(event.reply_token, message)
        
        
import os
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
