const { pool } = require('../config/database');
const logger = require('../utils/logger');

// Save chat message (Only for logged-in users)
exports.saveChatMessage = async (req, res) => {
  try {
    const { message, response } = req.body;
    const userId = req.userId; // From JWT token

    // Validate inputs
    if (!message || message.trim() === '') {
      return res.status(400).json({
        success: false,
        message: 'Message cannot be empty',
      });
    }

    if (!response || response.trim() === '') {
      return res.status(400).json({
        success: false,
        message: 'Response cannot be empty',
      });
    }

    const connection = await pool.getConnection();

    // Insert chat message
    const [result] = await connection.query(
      'INSERT INTO chat_history (user_id, message, response) VALUES (?, ?, ?)',
      [userId, message, response]
    );

    connection.release();

    logger.info(`💬 Chat saved for user ${userId} (ID: ${result.insertId})`);

    res.status(201).json({
      success: true,
      message: 'Chat message saved successfully',
      data: {
        id: result.insertId,
        userId,
        message,
        response,
        createdAt: new Date(),
      },
    });
  } catch (error) {
    logger.error('Save chat error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error saving chat message',
    });
  }
};

// Get chat history (Only for logged-in users)
exports.getChatHistory = async (req, res) => {
  try {
    const userId = req.userId; // From JWT token
    const { limit = 50, offset = 0 } = req.query;

    const connection = await pool.getConnection();

    // Get total count
    const [[{ total }]] = await connection.query(
      'SELECT COUNT(*) as total FROM chat_history WHERE user_id = ?',
      [userId]
    );

    // Get chat history
    const [chatHistory] = await connection.query(
      'SELECT id, message, response, created_at as createdAt FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
      [userId, parseInt(limit), parseInt(offset)]
    );

    connection.release();

    logger.info(`📚 Chat history retrieved for user ${userId} (${chatHistory.length} messages)`);

    res.status(200).json({
      success: true,
      message: 'Chat history retrieved successfully',
      data: {
        total,
        limit: parseInt(limit),
        offset: parseInt(offset),
        chats: chatHistory,
      },
    });
  } catch (error) {
    logger.error('Get chat history error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error retrieving chat history',
    });
  }
};

// Delete chat message (Only user's own messages)
exports.deleteChatMessage = async (req, res) => {
  try {
    const { chatId } = req.params;
    const userId = req.userId;

    if (!chatId) {
      return res.status(400).json({
        success: false,
        message: 'Chat ID is required',
      });
    }

    const connection = await pool.getConnection();

    // Check if chat belongs to user
    const [chats] = await connection.query(
      'SELECT id FROM chat_history WHERE id = ? AND user_id = ?',
      [chatId, userId]
    );

    if (chats.length === 0) {
      connection.release();
      logger.warn(`Unauthorized delete attempt for chat ${chatId} by user ${userId}`);
      return res.status(403).json({
        success: false,
        message: 'You can only delete your own chat messages',
      });
    }

    // Delete the message
    await connection.query('DELETE FROM chat_history WHERE id = ?', [chatId]);

    connection.release();

    logger.info(`🗑️ Chat ${chatId} deleted by user ${userId}`);

    res.status(200).json({
      success: true,
      message: 'Chat message deleted successfully',
    });
  } catch (error) {
    logger.error('Delete chat error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error deleting chat message',
    });
  }
};

// Clear all chat history for user
exports.clearChatHistory = async (req, res) => {
  try {
    const userId = req.userId;

    const connection = await pool.getConnection();

    // Delete all messages for user
    const [result] = await connection.query(
      'DELETE FROM chat_history WHERE user_id = ?',
      [userId]
    );

    connection.release();

    logger.info(`🧹 All chat history cleared for user ${userId} (${result.affectedRows} messages)`);

    res.status(200).json({
      success: true,
      message: 'All chat history cleared successfully',
      deletedCount: result.affectedRows,
    });
  } catch (error) {
    logger.error('Clear chat history error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error clearing chat history',
    });
  }
};
