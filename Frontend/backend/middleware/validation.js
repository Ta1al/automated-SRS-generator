// Username Validation Rules
const validateUsername = (username) => {
  // Rules:
  // 1. Must be 3-20 characters long
  // 2. Can only contain letters, numbers, and underscores
  // 3. Cannot start with a number
  // 4. Cannot contain spaces
  // Username will be lowercased for storage

  const usernameRegex = /^[a-z_][a-z0-9_]{2,19}$/;

  if (!username) {
    return {
      valid: false,
      message: 'Username is required',
    };
  }

  if (username.length < 3) {
    return {
      valid: false,
      message: 'Username must be at least 3 characters long',
    };
  }

  if (username.length > 20) {
    return {
      valid: false,
      message: 'Username cannot exceed 20 characters',
    };
  }

  if (!usernameRegex.test(username)) {
    return {
      valid: false,
      message: 'Username can only contain letters, numbers, and underscores. Must start with a letter or underscore.',
    };
  }

  return {
    valid: true,
    message: 'Username is valid',
  };
};

// Email Validation
const validateEmail = (email) => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!email) {
    return {
      valid: false,
      message: 'Email is required',
    };
  }

  if (!emailRegex.test(email)) {
    return {
      valid: false,
      message: 'Please provide a valid email address',
    };
  }

  return {
    valid: true,
    message: 'Email is valid',
  };
};

// Password Validation Rules
const validatePassword = (password) => {
  // Rules:
  // 1. Must be at least 6 characters
  // 2. Must contain at least one uppercase letter
  // 3. Must contain at least one lowercase letter
  // 4. Must contain at least one number
  // 5. Must contain at least one special character

  if (!password) {
    return {
      valid: false,
      message: 'Password is required',
    };
  }

  if (password.length < 6) {
    return {
      valid: false,
      message: 'Password must be at least 6 characters long',
    };
  }

  if (!/[A-Z]/.test(password)) {
    return {
      valid: false,
      message: 'Password must contain at least one uppercase letter',
    };
  }

  if (!/[a-z]/.test(password)) {
    return {
      valid: false,
      message: 'Password must contain at least one lowercase letter',
    };
  }

  if (!/[0-9]/.test(password)) {
    return {
      valid: false,
      message: 'Password must contain at least one number',
    };
  }

  if (!/[!@#$%^&*]/.test(password)) {
    return {
      valid: false,
      message: 'Password must contain at least one special character (!@#$%^&*)',
    };
  }

  return {
    valid: true,
    message: 'Password is valid',
  };
};

module.exports = {
  validateUsername,
  validateEmail,
  validatePassword,
};
