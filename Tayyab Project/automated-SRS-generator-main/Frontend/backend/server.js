const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const morgan = require('morgan');
require('dotenv').config();
const { testConnection } = require('./config/database');
const logger = require('./utils/logger');

// Import routes
const authRoutes = require('./routes/authRoutes');
const chatRoutes = require('./routes/chatRoutes');

// Import middleware
const { errorHandler } = require('./middleware/errorHandler');

// Initialize express app
const app = express();

// ============ SECURITY MIDDLEWARE ============
// Helmet - Set security HTTP headers
app.use(helmet());

// CORS - Cross-Origin Resource Sharing
app.use(cors({
  origin: process.env.CORS_ORIGIN || '*',
  credentials: true,
  optionsSuccessStatus: 200,
}));

// Compression - Compress responses
app.use(compression());

// Morgan - HTTP request logger
app.use(morgan(':remote-addr - :remote-user [:date[clf]] ":method :url HTTP/:http-version" :status :res[content-length] ":referrer" ":user-agent" - :response-time ms'));

// ============ BODY PARSING MIDDLEWARE ============
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// ============ REQUEST LOGGING ============
app.use((req, res, next) => {
  logger.info(`📨 ${req.method} ${req.path}`);
  next();
});

// ============ API ROUTES ============
app.use('/api/auth', authRoutes);
app.use('/api/chat', chatRoutes);

// ============ HEALTH CHECK ============
app.get('/api/health', (req, res) => {
  res.status(200).json({
    success: true,
    message: 'Server is running',
    environment: process.env.NODE_ENV || 'development',
    timestamp: new Date(),
  });
});

// ============ API VERSION INFO ============
app.get('/api', (req, res) => {
  res.status(200).json({
    success: true,
    message: 'Chatbot API v1.0',
    version: '1.0.0',
    endpoints: {
      auth: '/api/auth',
      chat: '/api/chat',
      health: '/api/health',
    },
  });
});

// ============ 404 HANDLER ============
app.use((req, res) => {
  logger.warn(`404 Not Found: ${req.method} ${req.path}`);
  res.status(404).json({
    success: false,
    message: 'Route not found',
    path: req.path,
  });
});

// ============ ERROR HANDLING MIDDLEWARE ============
app.use(errorHandler);

// ============ SERVER STARTUP ============
const PORT = process.env.PORT || 5000;

const startServer = async () => {
  try {
    // Test database connection
    await testConnection();

    app.listen(PORT, () => {
      logger.info(`
╔════════════════════════════════════════╗
║  🚀 Chatbot Backend Server Running     ║
║  📍 Port: ${PORT}                        ║
║  🔗 http://localhost:${PORT}              ║
║  🔐 Environment: ${process.env.NODE_ENV || 'development'}     ║
║  📝 API Docs: /api                      ║
╚════════════════════════════════════════╝
      `);
    });
  } catch (error) {
    logger.error('Failed to start server', error.message);
    process.exit(1);
  }
};

startServer();

module.exports = app;
