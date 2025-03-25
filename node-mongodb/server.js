require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json());

app.get('/health', (req, res) => {
    res.status(200).send('✅ I am alive');
});

// ✅ 連接 MongoDB（啟用 Keep-Alive）
mongoose.connect(process.env.MONGO_URI, { 
    useNewUrlParser: true, 
    useUnifiedTopology: true,
    keepAlive: true,
    keepAliveInitialDelay: 300000 // ✅ 5 分鐘後開始 Keep-Alive
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

// ✅ 定期發送 `ping()`，防止 MongoDB 斷線
setInterval(async () => {
    try {
        await mongoose.connection.db.admin().ping();
        console.log("✅ MongoDB 連線正常");
    } catch (err) {
        console.error("❌ MongoDB Ping 失敗，可能已斷線:", err);
    }
}, 300000); // 每 5 分鐘發送一次 Ping

// **定義 Schema**
const messageSchema = new mongoose.Schema({
    user_id: { type: String, required: true },
    message_text: { type: String, default: "" },
    bot_response: { type: String, default: "" },
    message_type: { type: String, required: true },
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// **儲存訊息 API**
app.post("/save_message", async (req, res) => {
    console.log("📥 收到的 message_data:", req.body);

    const { user_id, message_text, message_type, bot_response } = req.body;

    if (!user_id || !message_text || !bot_response) {
        console.log("❌ 缺少必要資料 (user_id, message_text, 或 bot_response)");
        return res.status(400).json({ error: "Invalid data" });
    }

    try {
        const message = new Message({ user_id, message_text, bot_response, message_type });
        await message.save();
        console.log("✅ 成功存入 MongoDB");
        res.json({ status: "success", message: "Message saved" });
    } catch (err) {
        console.error("❌ MongoDB 存入錯誤:", err);
        res.status(500).json({ error: "Database error" });
    }
});

// **取得歷史訊息 API**
app.get("/get_history", async (req, res) => {
    const { user_id } = req.query;
    if (!user_id) {
        return res.status(400).json({ error: "缺少 user_id" });
    }

    try {
        const messages = await Message.find({ user_id }).sort({ timestamp: 1 }).limit(20); // 多一點上下文更好
        res.json({ messages });
    } catch (err) {
        console.error("❌ 取得對話紀錄錯誤:", err);
        res.status(500).json({ error: "伺服器錯誤" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));
