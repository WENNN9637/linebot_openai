require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json());

mongoose.connect(process.env.MONGO_URI, { 
    useNewUrlParser: true, 
    useUnifiedTopology: true,
    keepAlive: true,        // ✅ 保持連線
    keepAliveInitialDelay: 300000 // ✅ 每 5 分鐘發送 Keep-Alive
})
    .then(() => console.log("✅ MongoDB 連線成功"))
    .catch(err => {
        console.error("❌ MongoDB 連線失敗:", err);
        process.exit(1);
    });

mongoose.connection.once('open', () => {
    console.log("✅ 連線的資料庫:", mongoose.connection.name);
    console.log("✅ 連線的 Collections:", Object.keys(mongoose.connection.collections));
});

// **定義 Schema**
const messageSchema = new mongoose.Schema({
    user_id: { type: String, required: true },
    message_text: { type: String, default: "" },
    message_type: { type: String, required: true },
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// **API 來儲存訊息（Python Web Service 會呼叫這個 API）**
app.post('/save_message', async (req, res) => {
    try {
        console.log("📥 收到請求:", req.body); // ✅ 確保有收到請求

        const { user_id, message_text, message_type } = req.body;
        if (!user_id || !message_type) {
            return res.status(400).json({ error: "缺少必要欄位" });
        }

        const newMessage = new Message({
            user_id,
            message_text,
            message_type
        });

        await newMessage.save();
        console.log(`📩 訊息已成功存入 MongoDB:`, newMessage);

        res.status(200).json({ status: "success", message: "Message saved" });
    } catch (error) {
        console.error("❌ 儲存訊息失敗:", error);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));
