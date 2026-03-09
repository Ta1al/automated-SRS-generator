require('dotenv').config();
const { pool } = require('./config/database');

async function viewAllUsers() {
  try {
    console.log('\n📋 Fetching all registered users...\n');
    
    const connection = await pool.getConnection();
    const [users] = await connection.query(
      'SELECT id, username, email, created_at FROM users ORDER BY created_at DESC'
    );
    connection.release();

    if (users.length === 0) {
      console.log('⚠️  No users found in the database.\n');
      process.exit(0);
    }

    // Print header
    console.log('┌─────┬──────────────────────┬──────────────────────────────┬────────────────────────────────┐');
    console.log('│ ID  │ Username             │ Email                        │ Signup Date                    │');
    console.log('├─────┼──────────────────────┼──────────────────────────────┼────────────────────────────────┤');

    // Add rows
    users.forEach((user) => {
      const date = new Date(user.created_at).toLocaleString();
      const id = String(user.id).padEnd(3);
      const username = String(user.username).padEnd(20);
      const email = String(user.email).padEnd(28);
      const dateStr = String(date).padEnd(30);
      
      console.log(`│ ${id} │ ${username} │ ${email} │ ${dateStr} │`);
    });

    console.log('└─────┴──────────────────────┴──────────────────────────────┴────────────────────────────────┘');
    console.log(`\n✅ Total Users: ${users.length}\n`);

    process.exit(0);
  } catch (error) {
    console.error('❌ Error fetching users:', error.message);
    process.exit(1);
  }
}

viewAllUsers();
