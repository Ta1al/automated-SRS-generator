# 🚀 AutoSRS.AI - Complete Authentication System

A production-ready authentication system built with **Next.js 16** (Frontend), **Node.js + Express** (Backend), and **MySQL** (Database).

---

## ✨ Features

### Authentication & Security
- ✅ User signup with strong validation
- ✅ Secure user login with JWT tokens
- ✅ Password hashing with bcryptjs
- ✅ Rate limiting (prevent brute force attacks)
- ✅ Input validation for usernames and passwords
- ✅ Protected routes requiring authentication

### Frontend (Next.js + React)
- ✅ Beautiful signup & login pages with animations
- ✅ Protected generator page (requires login)
- ✅ Dynamic navbar (shows login/signup or logout)
- ✅ Global auth state with AuthContext
- ✅ JWT token persistence in localStorage
- ✅ Responsive UI design

### Backend (Node.js + Express)
- ✅ REST API endpoints for auth
- ✅ Security headers with Helmet
- ✅ CORS configuration
- ✅ Request logging
- ✅ Comprehensive error handling

### Database (MySQL)
- ✅ Users table with encrypted passwords
- ✅ Chat history table
- ✅ Proper indexes for performance
- ✅ Foreign key relationships

---

## 🚀 Quick Start (Windows)

### Option 1: Automatic Setup (Easiest)

**Double-click this file in your project root:**
```
QUICK_START.bat
```

This will:
1. Start MySQL automatically
2. Create database and tables
3. Install all dependencies
4. Start backend server on port 5000

Then open a **new terminal** and run:
```
RUN_FRONTEND.bat
```

**Open browser:** http://localhost:3000

---

### Option 2: Manual Setup (5 minutes)

**Terminal 1 - Start MySQL:**
```bash
net start MySQL80
```

**Terminal 2 - Start Backend:**
```bash
cd backend
npm install
npm start
```

**Terminal 3 - Start Frontend:**
```bash
npm install
npm run dev
```

**Open browser:** http://localhost:3000

---

## 🧪 Quick Test

1. Go to http://localhost:3000
2. Click **"Sign Up"**
3. Enter test credentials:
   - Username: `testuser`
   - Email: `test@example.com`
   - Password: `TestPass@123`
4. Click **"Create Account"**
5. You should see username in navbar ✅

---

## 📁 Project Structure

```
D:\up dated Final_year_Project\
├── app/                    # Next.js pages
│   ├── layout.js          # Root layout
│   ├── page.js            # Home page
│   ├── signup/            # Signup page
│   ├── login/             # Login page
│   └── generator/         # Protected page
│
├── components/            # React components
│   ├── AnimatedBackground.jsx
│   └── Navbar.jsx
│
├── context/               # Auth context
│   ├── AuthContext.jsx
│   └── withAuth.jsx
│
├── backend/               # Backend server
│   ├── server.js          # Main server
│   ├── config/            # Database config
│   ├── controllers/       # Route handlers
│   ├── routes/            # API routes
│   ├── middleware/        # Custom middleware
│   └── database.sql       # Database setup
│
├── QUICK_START.bat        # Run this first
├── RUN_FRONTEND.bat       # Frontend startup
└── README.md              # This file
```

---

## 🔌 API Endpoints

### Authentication

#### **Sign Up**
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

#### **Login**
```
POST /api/auth/login
Content-Type: application/json

{
  "username": "john_doe",
  "password": "SecurePass123!"
}
```

#### **Logout**
```
POST /api/auth/logout
```

---

## ⚙️ Configuration

### Database Credentials
Edit `.env` file in the backend folder:
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

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 16, React 19 |
| Backend | Node.js, Express.js |
| Database | MySQL 9.6 |
| Authentication | JWT (JSON Web Tokens) |
| Password Hashing | bcryptjs |
| Security | Helmet, CORS, Rate Limiting |

---

## 📝 Password Requirements

For signup, passwords must have:
- ✅ At least 1 uppercase letter
- ✅ At least 1 lowercase letter
- ✅ At least 1 number
- ✅ At least 1 special character (@, #, $, %, &, !)
- ✅ Minimum 8 characters

---

## 🚨 Troubleshooting

### MySQL Not Starting
```bash
# Run Command Prompt as Administrator
net start MySQL80
```

### Port Already in Use
- **Backend:** Change port in `.env` (PORT=5000)
- **Frontend:** Next.js will use 3001 if 3000 is taken

### Database Connection Error
1. Ensure MySQL service is running
2. Check `.env` credentials match your MySQL setup
3. Verify database exists: `mysql -u root -p chatbot_db`

### npm Dependencies Missing
```bash
npm install
npm install --legacy-peer-deps
```

---

## 📚 Key Files Reference

| File | Purpose |
|------|---------|
| backend/server.js | Main backend server |
| backend/controllers/authController.js | Auth logic |
| app/layout.js | Frontend layout wrapper |
| context/AuthContext.jsx | Global auth state |
| backend/config/database.js | Database connection |

---

## 📞 Support

For detailed system architecture, see ARCHITECTURE.md

For detailed setup guide, check the batch files:
- QUICK_START.bat
- backend/RUN_BACKEND.bat
- RUN_FRONTEND.bat

---

## ✅ Status

- ✅ Authentication System: Complete
- ✅ Database Setup: Complete
- ✅ API Endpoints: Complete
- ✅ Frontend UI: Complete
- ✅ Security Features: Complete
- ✅ Documentation: Complete

**Ready for production use!**
