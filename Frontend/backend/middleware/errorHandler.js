const logger = require('../utils/logger');

// Centralized error handler
class AppError extends Error {
  constructor(message, statusCode) {
    super(message);
    this.statusCode = statusCode;
  }
}

// Error handling middleware
const errorHandler = (err, req, res, next) => {
  err.statusCode = err.statusCode || 500;
  err.message = err.message || 'Internal Server Error';

  // Log error
  logger.error(`${req.method} ${req.path}`, err.message);

  // Wrong MongoDB ID error
  if (err.name === 'CastError') {
    const message = `Resource not found. Invalid: ${err.path}`;
    err = new AppError(message, 400);
  }

  // JWT error
  if (err.name === 'JsonWebTokenError') {
    const message = 'JSON Web Token is invalid';
    err = new AppError(message, 401);
  }

  // JWT expired error
  if (err.name === 'TokenExpiredError') {
    const message = 'JSON Web Token is expired';
    err = new AppError(message, 401);
  }

  res.status(err.statusCode).json({
    success: false,
    message: err.message,
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack }),
  });
};

module.exports = {
  AppError,
  errorHandler,
};
