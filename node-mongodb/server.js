require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');
const axios = require('axios');

const app = express();
app.use(bodyParser.json());

const PORT = process.env.PORT || 3000;

// ✅ 健康檢查
app.get('/health', (req, res) => {
    res.status(200).send('✅ I am alive');
});

// ✅ 使用者資料（模擬資料）
const users = [
    { user_id: "Uxxxxxx1", level: "beginner", day: 12 },
    { user_id: "Uxxxxxx2", level: "intermediate", day: 8 },
    { user_id: "Uxxxxxx3", level: "advanced", day: 20 }
];

// ✅ MongoDB Schema 與 Model
const messageSchema = new mongoose.Schema({
    user_id: { type: String, required: true },
    message_text: { type: String, default: "" },
    bot_response: { type: String, default: "" },
    message_type: { type: String, required: true },
    interaction_rounds: { type: Number, default: 0 },            // ✅ 加這個
    constructive_contribution: { type: Boolean, default: false }, // ✅ 加這個
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// ✅ 儲存訊息 API
app.post("/save_message", async (req, res) => {
    const { user_id, message_text, message_type, bot_response, interaction_rounds, constructive_contribution } = req.body;
    
    if (!user_id || (!message_text && !bot_response)) {
        console.log("❌ 缺少必要資料 (user_id + message_text 或 bot_response)");
        return res.status(400).json({ error: "Invalid data" });
    }

    try {
        const message = new Message({
            user_id,
            message_text,
            bot_response,
            message_type,
            interaction_rounds: interaction_rounds || 0, // 🔥 預設0
            constructive_contribution: constructive_contribution || false // 🔥 預設false
        });
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

// ✅ 每日挑戰 API
app.post("/daily_challenge", async (req, res) => {
    for (const user of users) {
        try {
            await axios.post("https://你的-python-server.onrender.com/send_daily_challenge", {
                user_id: user.user_id,
                user_level: user.level,
                day_count: user.day
            });
            console.log(`✅ 傳送給 ${user.user_id} 成功`);
        } catch (err) {
            console.error(`❌ 傳送給 ${user.user_id} 失敗:`, err.message);
        }
    }

    res.send("✅ 所有挑戰題已傳送");
});

// ✅ 啟動伺服器（等 MongoDB 成功才開始接請求）
const startServer = async () => {
    try {
        console.log("🔄 嘗試連線至 MongoDB...");
        await mongoose.connect(process.env.MONGO_URI, {
            useNewUrlParser: true,
            useUnifiedTopology: true
        });
        console.log("✅ MongoDB 已連線");

        app.listen(PORT, () => {
            console.log(`🚀 伺服器啟動成功，正在監聽 port ${PORT}`);
        });

        // 每 5 分鐘 ping MongoDB 一次
        setInterval(async () => {
            try {
                await mongoose.connection.db.admin().ping();
                console.log("✅ MongoDB ping 正常");
            } catch (err) {
                console.error("❌ MongoDB ping 失敗:", err);
            }
        }, 300000);
    } catch (err) {
        console.error("❌ MongoDB 連線失敗，無法啟動伺服器:", err);
        process.exit(1);
    }
};

startServer();
