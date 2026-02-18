<<<<<<< HEAD
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
=======
# AI-Powered Automated SRS Generator

![Status](https://img.shields.io/badge/Status-Under%20Development-yellow)

## Abstract

Many software projects fail due to vague or incomplete requirements given by non-technical clients. Writing a Software Requirement Specification (SRS) requires expertise, which many clients and small teams lack.

Our proposed solution is an **AI-powered Automated SRS Generator**. Through a chat interface, clients can describe their project idea in plain English. The system uses NLP and AI to:

- Ask clarifying questions
- Suggest missing requirements
- Generate a complete **IEEE 830-compliant SRS**
- Produce **UML diagrams** (use-case, class, sequence)
- Provide basic **wireframes** of the system

This will save time, reduce miscommunication, and make requirement engineering accessible to non-technical stakeholders.

## Justification

Traditionally, System Analysts or Requirements Engineers gather client requirements and write the SRS with supporting diagrams. However, this is time-consuming, costly, and prone to human error.

Recent tools like Almware, Reqi's "Rex," and Blueprint.AI show early attempts to automate requirement documentation, but they lack interactive clarification, missing requirement suggestions, and visual model generation. Our project combines all these aspects into one assistant.

This project bridges the gap between clients and developers by acting like a junior Requirements Engineer. It adds academic value (NLP, AI, automation) and industrial value (time and cost savings in requirement engineering).

## Objectives

- Develop a **chat-based interface** where clients describe requirements
- Implement **AI-driven clarification** (chatbot asks follow-up questions)
- Add a **knowledge base/ML model** to suggest missing requirements
- Generate **IEEE 830-compliant SRS** documents
- Automatically create **UML diagrams** (use-case, class, sequence)
- Optionally generate basic **UI wireframes**
- Ensure usability, scalability, and security of the platform

## Project Scope

### In Scope
- Interactive AI-based requirement gathering
- Automated SRS generation (IEEE 830)
- UML diagrams (use-case, class, sequence)
- Wireframe prototypes
- Exportable reports (PDF/DOCX)

### Out of Scope
- Full system implementation for client projects
- Advanced UI/UX prototyping beyond basic wireframes
- Domain-specific deep knowledge bases (initially general best practices only)

## Tools and Technologies

- **Frontend:** React + Tailwind CSS (chat interface, diagram display)
- **Backend:** Python (Flask/FastAPI)
- **AI/NLP:** Hugging Face Transformers, spaCy, OpenAI API or open-source model
- **Database:** MongoDB Atlas
- **Diagram Generation:** PlantUML / Mermaid.js
- **Wireframes:** Mermaid wireframes
- **Deployment:** Docker + Cloud (AWS/Heroku/Vercel)
- **Collaboration:** GitHub, CI/CD pipelines

## Potential Impact

- **Academic:** Demonstrates AI + NLP in requirements engineering, publishable research
- **Industrial:** Saves time, reduces cost of hiring analysts, improves project success rate
- **Social:** Makes software development accessible for non-technical founders/startups

## Documentation

For detailed project specifications, please refer to the files in the `documentation/` folder:
- [FYP Proposal](documentation/FYP%20Proposal.pdf)
- [Software Requirements Specifications](documentation/Software%20Requirements%20Specifications.pdf)

## Data Normalization

Normalize the sample requirements and SRS templates into JSONL for RAG:

```bash
python scripts/normalize_data.py
```

Preview a few normalized records:

```bash
python scripts/preview_normalized.py --limit 5
```

## Clarification Loop (Demo)

Generate initial clarification questions from a user idea:

```bash
python scripts/clarification_demo.py --input "We want a web app that turns ideas into SRS documents"
```

## OpenRouter Clarification App

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the interactive CLI (dry run skips the API call):

```bash
python scripts/openrouter_app.py --dry-run
```

Stream the LLM response:

```bash
python scripts/openrouter_app.py --stream
```

Use embeddings-based RAG (OpenRouter embeddings model):

```bash
$env:OPENROUTER_EMBED_MODEL="openai/text-embedding-3-small"
python scripts/openrouter_app.py --rag embed
```

Precompute embeddings once (recommended for speed):

```bash
python scripts/build_embeddings.py
```

Then run with the precomputed index:

```bash
python scripts/openrouter_app.py --rag embed --use-precomputed
```

Set your OpenRouter key and run live:

```bash
$env:OPENROUTER_API_KEY="your-key-here"
python scripts/openrouter_app.py
```

Or place the key in a root `.env` file:

```bash
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_HTTP_REFERER=https://your-site.example
OPENROUTER_APP_TITLE=Your App Name
```

## License

This project is part of a Final Year Project.

---

**Submission Date:** October 2025
>>>>>>> 3e7b6f7ed1dc662d5e4cd77396820df2d19ca48a
