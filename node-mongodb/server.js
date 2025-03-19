require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json());

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

// **API 來儲存訊息（Python Web Service 會呼叫這個 API）**
app.post('/save_message', async (req, res) => {
    try {
        const { user_id, message_text, message_type } = req.body;

        const newMessage = new Message({
            user_id,
            message_text,
            message_type
        });

        await newMessage.save();
        console.log(`📩 訊息已儲存: ${message_text}`);

        res.status(200).json({ status: "success", message: "Message saved" });
    } catch (error) {
        console.error("❌ 儲存訊息失敗:", error);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

// **啟動伺服器**
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 伺服器運行於 http://localhost:${PORT}`));
