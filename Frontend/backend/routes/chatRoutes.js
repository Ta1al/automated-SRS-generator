const express = require('express');
const chatController = require('../controllers/chatController');
const { verifyToken } = require('../middleware/authMiddleware');
const { chatLimiter, sanitizeInput } = require('../middleware/securityMiddleware');

const router = express.Router();

// All chat routes require authentication and rate limiting
router.use(verifyToken);
router.use(chatLimiter);
router.use(sanitizeInput);

// Save chat message
router.post('/save', chatController.saveChatMessage);

// Get chat history
router.get('/history', chatController.getChatHistory);

// Delete single chat message
router.delete('/:chatId', chatController.deleteChatMessage);

// Clear all chat history
router.delete('/', chatController.clearChatHistory);

module.exports = router;
