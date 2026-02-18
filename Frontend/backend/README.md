# 🤖 Chatbot Backend - Node.js + MySQL

Complete backend solution with Authentication and Chat History Management

## 📋 Features

✅ **User Signup with Validation**
- Username validation (3-20 chars, letters/numbers/underscores only)
- Email validation
- Password strength requirements (uppercase, lowercase, numbers, special chars)
- Duplicate username/email checking

✅ **Secure Login**
- JWT-based authentication
- Bcrypt password hashing
- Token expiry management

✅ **Chat History Management**
- Save chat messages (only for logged-in users)
- Retrieve chat history
- Delete individual messages
- Clear all history

---

## 🔧 Installation & Setup

### 1️⃣ Prerequisites
- Node.js (v14+)
- MySQL Server running locally
- npm or yarn

### 2️⃣ Environment Setup

Update `.env` file with your MySQL credentials:

```env
PORT=5000
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=chatbot_db
JWT_SECRET=your_secure_jwt_secret_key_here
JWT_EXPIRE=7d
NODE_ENV=development
```

### 3️⃣ Database Setup

1. Open MySQL CLI or MySQL Workbench
2. Run the SQL commands from `database.sql`:

```sql
-- Copy all content from database.sql and execute
```

Or via command line:
```bash
mysql -u root -p < database.sql
```

### 4️⃣ Start Backend Server

```bash
npm start
```

Server will run on: **http://localhost:5000**

---

## 🔌 API Endpoints

### Authentication Endpoints

#### 📝 **Signup**
```
POST /api/auth/signup
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "confirmPassword": "SecurePass123!"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "User registered successfully",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com"
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "message": "Username already taken. Please choose another username."
}
```

---

#### 🔑 **Login**
```
POST /api/auth/login
Content-Type: application/json

{
  "username": "john_doe",
  "password": "SecurePass123!"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Login successful",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com"
  }
}
```

---

### Chat History Endpoints

#### 💾 **Save Chat Message**
```
POST /api/chat/save
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "message": "What is Node.js?",
  "response": "Node.js is a JavaScript runtime built on Chrome's V8..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Chat message saved successfully",
  "data": {
    "id": 1,
    "userId": 1,
    "message": "What is Node.js?",
    "response": "Node.js is a JavaScript runtime...",
    "createdAt": "2024-01-27T10:30:00Z"
  }
}
```

---

#### 📚 **Get Chat History**
```
GET /api/chat/history?limit=50&offset=0
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "success": true,
  "message": "Chat history retrieved successfully",
  "data": {
    "total": 25,
    "limit": 50,
    "offset": 0,
    "chats": [
      {
        "id": 1,
        "message": "What is Node.js?",
        "response": "Node.js is a JavaScript runtime...",
        "createdAt": "2024-01-27T10:30:00Z"
      }
    ]
  }
}
```

---

#### 🗑️ **Delete Single Chat Message**
```
DELETE /api/chat/:chatId
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "success": true,
  "message": "Chat message deleted successfully"
}
```

---

#### 🧹 **Clear All Chat History**
```
DELETE /api/chat/
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "success": true,
  "message": "All chat history cleared successfully",
  "deletedCount": 25
}
```

---

## ✅ Username Validation Rules

The username must follow these rules:

- **Length:** 3-20 characters
- **Characters:** Letters (a-z, A-Z), numbers (0-9), underscores (_) only
- **Start:** Must start with a letter or underscore
- **Examples:**
  - ✅ Valid: `john_doe`, `user123`, `_admin`
  - ❌ Invalid: `jo`, `123user` (starts with number), `john-doe` (hyphen not allowed)

---

## 🔐 Password Validation Rules

Password must have:

- **Minimum 6 characters**
- **At least 1 Uppercase letter** (A-Z)
- **At least 1 Lowercase letter** (a-z)
- **At least 1 Number** (0-9)
- **At least 1 Special Character** (!@#$%^&*)

Example: `SecurePass123!`

---

## 🔒 JWT Token Usage

Include the JWT token in all authenticated requests:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Token expires in **7 days** by default (configurable in `.env`)

---

## 📁 Project Structure

```
backend/
├── config/
│   └── database.js           # MySQL connection pool
├── controllers/
│   ├── authController.js     # Signup/Login logic
│   └── chatController.js     # Chat history logic
├── middleware/
│   ├── authMiddleware.js     # JWT verification
│   └── validation.js         # Input validation rules
├── routes/
│   ├── authRoutes.js         # Auth endpoints
│   └── chatRoutes.js         # Chat endpoints
├── .env                      # Environment variables
├── database.sql              # Database schema
├── server.js                 # Main server file
└── package.json
```

---

## 🚀 Features Breakdown

### Signup Process
1. User submits username, email, password
2. Validates username format (3-20 chars, alphanumeric + underscore)
3. Validates email format
4. Validates password strength
5. Checks for duplicate username/email
6. Hashes password with bcrypt
7. Creates user in database
8. Returns JWT token

### Login Process
1. User submits username & password
2. Finds user in database
3. Compares password with bcrypt
4. Issues JWT token on success
5. Token valid for 7 days

### Chat History (Login Required)
- Users WITHOUT login: Chat not saved
- Users WITH login: All chat saved automatically
- Can retrieve, delete, or clear history anytime

---

## 📝 Error Handling

All API responses follow this format:

**Success:**
```json
{
  "success": true,
  "message": "...",
  "data": {...}
}
```

**Error:**
```json
{
  "success": false,
  "message": "Error description"
}
```

---

## 🧪 Testing with cURL

### Test Signup
```bash
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
    "confirmPassword": "TestPass123!"
  }'
```

### Test Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!"
  }'
```

### Test Save Chat (Replace TOKEN with actual JWT)
```bash
curl -X POST http://localhost:5000/api/chat/save \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello",
    "response": "Hi there!"
  }'
```

---

## 🔄 Integration with Frontend

### In Your React/Next.js App:

```javascript
// Signup
const signupResponse = await fetch('/api/auth/signup', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, email, password, confirmPassword })
});
const { token } = await signupResponse.json();
localStorage.setItem('authToken', token);

// Login
const loginResponse = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password })
});
const { token } = await loginResponse.json();
localStorage.setItem('authToken', token);

// Save Chat (logged-in users only)
const token = localStorage.getItem('authToken');
if (token) {
  await fetch('/api/chat/save', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message, response })
  });
}

// Get Chat History
const historyResponse = await fetch('/api/chat/history', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const { data } = await historyResponse.json();
```

---

## 🐛 Troubleshooting

**Q: "Database connection failed"**
- A: Check MySQL is running and credentials in `.env` are correct

**Q: "Invalid token" error**
- A: Token may be expired. User needs to login again

**Q: "Cannot find module"**
- A: Run `npm install` to install dependencies

**Q: Port already in use**
- A: Change PORT in `.env` or kill process on that port

---

## 📞 Support

For issues or questions, check:
- Database schema in `database.sql`
- API examples in this README
- Controller files for business logic

---

**Happy Coding! 🎉**
