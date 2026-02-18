const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { pool } = require('../config/database');
const { validateUsername, validateEmail, validatePassword } = require('../middleware/validation');
const logger = require('../utils/logger');

// Signup Controller
exports.signup = async (req, res) => {
  try {
    let { username, email, password, confirmPassword } = req.body;

    // Normalize inputs: trim and lowercase for consistency
    username = username ? username.trim().toLowerCase() : '';
    email = email ? email.trim().toLowerCase() : '';
    password = password ? password.trim() : '';
    confirmPassword = confirmPassword ? confirmPassword.trim() : '';

    // 1. Validate all inputs are provided
    if (!username || !email || !password || !confirmPassword) {
      return res.status(400).json({
        success: false,
        message: 'Please provide all required fields: username, email, password, confirmPassword',
      });
    }

    // 2. Validate username format
    const usernameValidation = validateUsername(username);
    if (!usernameValidation.valid) {
      return res.status(400).json({
        success: false,
        message: usernameValidation.message,
      });
    }

    // 3. Validate email format
    const emailValidation = validateEmail(email);
    if (!emailValidation.valid) {
      return res.status(400).json({
        success: false,
        message: emailValidation.message,
      });
    }

    // 4. Validate password (password is case-sensitive)
    const passwordValidation = validatePassword(password);
    if (!passwordValidation.valid) {
      return res.status(400).json({
        success: false,
        message: passwordValidation.message,
      });
    }

    // 5. Check if passwords match
    if (password !== confirmPassword) {
      return res.status(400).json({
        success: false,
        message: 'Passwords do not match',
      });
    }

    // Get connection
    const connection = await pool.getConnection();

    // 6. Check if username already exists (case-insensitive)
    const [existingUsername] = await connection.query(
      'SELECT id FROM users WHERE LOWER(username) = ?',
      [username]
    );

    if (existingUsername.length > 0) {
      connection.release();
      logger.warn(`Signup attempt with existing username: ${username}`);
      return res.status(400).json({
        success: false,
        message: 'Username already taken. Please choose another username.',
      });
    }

    // 7. Check if email already exists
    const [existingEmail] = await connection.query(
      'SELECT id FROM users WHERE email = ?',
      [email]
    );

    if (existingEmail.length > 0) {
      connection.release();
      logger.warn(`Signup attempt with existing email: ${email}`);
      return res.status(400).json({
        success: false,
        message: 'Email already registered. Please use another email or try login.',
      });
    }

    // 8. Hash password
    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash(password, salt);

    // 9. Create user
    const [result] = await connection.query(
      'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
      [username, email, hashedPassword]
    );

    connection.release();

    // 10. Create JWT Token
    const token = jwt.sign(
      { userId: result.insertId, username },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRE }
    );

    logger.info(`✅ New user registered: ${username} (ID: ${result.insertId})`);

    res.status(201).json({
      success: true,
      message: 'User registered successfully',
      token,
      user: {
        id: result.insertId,
        username,
        email,
      },
    });
  } catch (error) {
    logger.error('Signup error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error during signup. Please try again.',
    });
  }
};

// Login Controller
exports.login = async (req, res) => {
  try {
    let { username, password } = req.body;
    
    // Normalize inputs: trim and lowercase for consistency
    username = username ? username.trim().toLowerCase() : '';
    password = password ? password.trim() : '';

    // 1. Validate inputs
    if (!username || !password) {
      return res.status(400).json({
        success: false,
        message: 'Please provide username and password',
      });
    }

    // Get connection
    const connection = await pool.getConnection();

    // 2. Check if user exists (case-insensitive)
    const [users] = await connection.query(
      'SELECT id, username, email, password FROM users WHERE LOWER(username) = ?',
      [username]
    );

    if (users.length === 0) {
      connection.release();
      logger.warn(`Login attempt with non-existent username: ${username}`);
      return res.status(401).json({
        success: false,
        message: 'Invalid username or password',
      });
    }

    const user = users[0];

    // 3. Compare passwords
    const passwordMatch = await bcrypt.compare(password, user.password);

    if (!passwordMatch) {
      connection.release();
      logger.warn(`Failed login attempt for user: ${username}`);
      return res.status(401).json({
        success: false,
        message: 'Invalid username or password',
      });
    }

    connection.release();

    // 4. Create JWT Token
    const token = jwt.sign(
      { userId: user.id, username: user.username },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRE }
    );

    logger.info(`✅ User logged in: ${username} (ID: ${user.id})`);

    // 5. Return response
    res.status(200).json({
      success: true,
      message: 'Login successful',
      token,
      user: {
        id: user.id,
        username: user.username,
        email: user.email,
      },
    });
  } catch (error) {
    logger.error('Login error', error.message);
    res.status(500).json({
      success: false,
      message: 'Error during login. Please try again.',
    });
  }
};
