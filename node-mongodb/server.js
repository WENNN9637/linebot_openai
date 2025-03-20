require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json());

// **連接 MongoDB**
mongoose.connect(process.env.MONGO_URI, { 
    useNewUrlParser: true, 
    useUnifiedTopology: true,
    keepAlive: true,
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
    message_text: { type: String, default: "" }, // ✅ 儲存使用者輸入
    bot_response: { type: String, default: "" }, // ✅ 儲存機器人回應
    message_type: { type: String, required: true },
    timestamp: { type: Date, default: Date.now }
});
const Message = mongoose.model("Message", messageSchema);

// **API：儲存使用者訊息**
app.post("/save_message", async (req, res) => {
    console.log("📥 收到的 message_data:", req.body);

    const { user_id, user_text, bot_response } = req.body;

    if (!user_id || !user_text) {
        console.log("❌ 缺少 user_id 或 user_text");
        return res.status(400).json({ error: "Invalid data" });
    }

    try {
        const message = new Message({
            user_id: user_id,
            message_text: user_text,
            bot_response: bot_response || "",
            message_type: "text",
            timestamp: new Date()
        });
        await message.save();
        console.log("✅ 成功存入 MongoDB");
        res.json({ status: "success", message: "Message saved" });
    } catch (err) {
        console.error("❌ MongoDB 存入錯誤:", err);
        res.status(500).json({ error: "Database error" });
    }
});

// **API：取得使用者的歷史訊息**
app.get("/get_history", async (req, res) => {
    const { user_id } = req.query;
    if (!user_id) {
        return res.status(400).json({ error: "缺少 user_id" });
    }

    try {
        const messages = await Message.find({ user_id })  // ✅ 修正 MongoDB 查詢
            .sort({ timestamp: -1 })  // 取最新的對話
            .limit(10);

        res.json({ messages });
    } catch (err) {
        console.error("❌ 取得對話紀錄錯誤:", err);
        res.status(500).json({ error: "伺服器錯誤" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));





/*
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
app.post("/save_message", async (req, res) => {
    console.log("📥 收到的 message_data:", req.body); // 🔍 檢查傳入的 JSON

    if (!req.body.user_id || !req.body.message_text) {
        console.log("❌ 缺少 user_id 或 message_text");
        return res.status(400).json({ error: "Invalid data" });
    }

    try {
        const message = new Message({
            user_id: req.body.user_id,
            message_text: req.body.message_text,
            message_type: req.body.message_type,
            timestamp: new Date()
        });
        await message.save();
        console.log("✅ 成功存入 MongoDB");
        res.json({ status: "success", message: "Message saved" });
    } catch (err) {
        console.error("❌ MongoDB 存入錯誤:", err);
        res.status(500).json({ error: "Database error" });
    }
});

app.get("/get_history", async (req, res) => {
    const { user_id } = req.query;
    if (!user_id) {
        return res.status(400).json({ error: "缺少 user_id" });
    }

    try {
        const messages = await db.collection("messages")
            .find({ user_id })
            .sort({ _id: -1 }) // 取最新的對話
            .limit(10)
            .toArray();

        res.json({ messages });
    } catch (err) {
        console.error("❌ 取得對話紀錄錯誤:", err);
        res.status(500).json({ error: "伺服器錯誤" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));
*/
