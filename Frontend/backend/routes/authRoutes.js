const express = require('express');
const authController = require('../controllers/authController');
const { loginLimiter, signupLimiter, sanitizeInput, validateAuthInput } = require('../middleware/securityMiddleware');

const router = express.Router();

// Signup route with security middleware
router.post('/signup', signupLimiter, sanitizeInput, validateAuthInput, authController.signup);

// Login route with security middleware
router.post('/login', loginLimiter, sanitizeInput, validateAuthInput, authController.login);

module.exports = router;
