const jwt = require('jsonwebtoken');
const { pool } = require('../config/database');

const protect = async (req, res, next) => {
  let token;

  if (
    req.headers.authorization &&
    req.headers.authorization.startsWith('Bearer')
  ) {
    try {
      // Get token from header
      token = req.headers.authorization.split(' ')[1];

      // Verify token
      const decoded = jwt.verify(token, process.env.JWT_SECRET);

      // Get user from the token
      const [rows] = await pool.execute('SELECT id, username, email FROM users WHERE id = ?', [decoded.userId]);

      if (rows.length === 0) {
        return res.status(401).json({ success: false, message: 'Not authorized, user not found' });
      }

      req.user = rows[0];
      next();
    } catch (error) {
      console.error(error);
      return res.status(401).json({ success: false, message: 'Not authorized, token failed' });
    }
  }

  if (!token) {
    return res.status(401).json({ success: false, message: 'Not authorized, no token' });
  }
};

module.exports = { protect };
