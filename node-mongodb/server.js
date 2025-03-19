require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');
const { Client, middleware } = require('@line/bot-sdk');

const app = express();
app.use(bodyParser.json());

// **LINE Bot 設定**
const lineConfig = {
    channelAccessToken: process.env.LINE_ACCESS_TOKEN,
    channelSecret: process.env.LINE_CHANNEL_SECRET
};
const lineClient = new Client(lineConfig);

// **MongoDB 連線**
mongoose.connect(process.env.MONGO_URI, { 
    useNewUrlParser: true, 
    useUnifiedTopology: true 
})
    .then(() => console.log("✅ MongoDB 連線成功"))
    .catch(err => {
        console.error("❌ MongoDB 連線失敗:", err);
        process.exit(1);
    });

// **定義 Schema**
const messageSchema = new mongoose.Schema({
    user_id: { type: String, required: true },
    message_text: { type: String, default: "" },
    message_type: { type: String, required: true },
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// **處理 LINE Webhook**
app.post('/webhook', middleware(lineConfig), async (req, res) => {
    try {
        const events = req.body.events;
        for (const event of events) {
            if (event.type === 'message' && event.message) {
                const newMessage = new Message({
                    user_id: event.source?.userId || "unknown",
                    message_text: event.message.text || "",
                    message_type: event.message.type,
                });

                await newMessage.save();
                console.log(`📩 訊息已儲存: ${event.message.text}`);

                // **回覆使用者**
                await lineClient.replyMessage(event.replyToken, {
                    type: 'text',
                    text: `你剛剛說: ${event.message.text}`
                });
            }
        }
        res.sendStatus(200);
    } catch (error) {
        console.error("❌ 處理 Webhook 失敗:", error);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));
