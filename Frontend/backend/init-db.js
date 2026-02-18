// z:\up dated Final_year_Project\backend\init-db.js
const db = require('./config/database');

async function initDB() {
  try {
    console.log('⏳ Connecting to Aiven Cloud Database...');
    
    // Users Table Create Karein
    await db.execute(`
      CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);
    
    console.log('✅ Users table created successfully in Cloud DB!');
    console.log('🚀 Ab aapka backend cloud database use kar raha hai.');
    process.exit(0);
  } catch (error) {
    console.error('❌ Error connecting to database:', error.message);
    process.exit(1);
  }
}

initDB();
