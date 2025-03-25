require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json());

// ✅ 健康檢查
app.get('/health', (req, res) => {
    res.status(200).send('✅ I am alive');
});

// ✅ 自動重連 MongoDB
const connectWithRetry = () => {
    console.log("🔄 嘗試連線至 MongoDB...");
    mongoose.connect(process.env.MONGO_URI, {
        useNewUrlParser: true,
        useUnifiedTopology: true,
        keepAlive: true,
        keepAliveInitialDelay: 300000 // 5分鐘後開始 keep-alive
    }).then(() => {
        console.log("✅ MongoDB 連線成功");
    }).catch(err => {
        console.error("❌ MongoDB 連線失敗，5 秒後重試:", err);
        setTimeout(connectWithRetry, 5000);
    });
};

connectWithRetry();

mongoose.connection.once('open', () => {
    console.log("✅ 連線的資料庫:", mongoose.connection.name);
    console.log("✅ 連線的 Collections:", Object.keys(mongoose.connection.collections));
});

// ✅ 定時 ping 防止連線斷開
setInterval(async () => {
    try {
        await mongoose.connection.db.admin().ping();
        console.log("✅ MongoDB 連線正常");
    } catch (err) {
        console.error("❌ MongoDB Ping 失敗，可能已斷線:", err);
        connectWithRetry(); // 嘗試重連
    }
}, 300000); // 每 5 分鐘一次

// ✅ 定義 Schema 與 Model
const messageSchema = new mongoose.Schema({
    user_id: { type: String, required: true },
    message_text: { type: String, default: "" },
    bot_response: { type: String, default: "" },
    message_type: { type: String, required: true },
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// ✅ 每次請求時確認 MongoDB 連線狀態
const ensureDbConnected = async () => {
    if (mongoose.connection.readyState !== 1) {
        console.warn("⚠️ MongoDB 尚未連線，重新連接中...");
        await mongoose.connect(process.env.MONGO_URI, {
            useNewUrlParser: true,
            useUnifiedTopology: true
        });
    }
};

// ✅ 儲存訊息 API
app.post("/save_message", async (req, res) => {
    await ensureDbConnected(); // <-- 新增

    console.log("📥 收到的 message_data:", req.body);
    const { user_id, message_text, message_type, bot_response } = req.body;

    if (!user_id || (!message_text && !bot_response)) {
        console.log("❌ 缺少必要資料 (user_id + message_text 或 bot_response)");
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

// ✅ 取得歷史訊息 API
app.get("/get_history", async (req, res) => {
    await ensureDbConnected(); // <-- 新增

    const { user_id } = req.query;
    if (!user_id) {
        return res.status(400).json({ error: "缺少 user_id" });
    }

    try {
        const messages = await Message.find({ user_id }).sort({ timestamp: 1 }).limit(20);
        res.json({ messages });
    } catch (err) {
        console.error("❌ 取得對話紀錄錯誤:", err);
        res.status(500).json({ error: "伺服器錯誤" });
    }
});

// ✅ 啟動伺服器
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log)
