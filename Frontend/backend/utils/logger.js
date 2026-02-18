const fs = require('fs');
const path = require('path');

// Create logs directory if it doesn't exist
const logsDir = path.join(__dirname, '../logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir);
}

// Logger function
const logger = (level, message, error = null) => {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] [${level}] ${message}${error ? ` - ${error}` : ''}`;

  console.log(logMessage);

  // Also save to file
  const logFile = path.join(logsDir, `${new Date().toISOString().split('T')[0]}.log`);
  fs.appendFileSync(logFile, logMessage + '\n');
};

module.exports = {
  info: (message) => logger('INFO', message),
  error: (message, error) => logger('ERROR', message, error),
  warn: (message) => logger('WARN', message),
  debug: (message) => logger('DEBUG', message),
};
