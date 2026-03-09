const express = require('express');
const router = express.Router();
const { processChat, getHistory, generateSRS, saveChat } = require('../controllers/chatController');
const { protect } = require('../middleware/authMiddleware'); // Authentication middleware

// Public route (agar bina login ke chat karni ho) ya Protected
router.post('/', processChat); 

// Protected routes (Login zaroori hai)
router.get('/history', protect, getHistory);
router.post('/save', protect, saveChat);
router.post('/generate', generateSRS); // SRS generate karne ke liye

module.exports = router;
