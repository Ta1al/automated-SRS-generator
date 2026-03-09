const mysql = require('mysql2/promise');
require('dotenv').config();

// Database connection pool create kar rahe hain
const pool = mysql.createPool({
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'chatbot_db',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
});

// Connection test karne ka function
const testConnection = async () => {
  try {
    const connection = await pool.getConnection();
    console.log('✅ Database connected successfully');
    connection.release();
    return true;
  } catch (error) {
    console.error('❌ Database connection failed:', error.message);
    throw error;
  }
};

// Dono cheezen export kar rahe hain
module.exports = {
  pool,
  testConnection
};
