# AutoSRS.ai — Setup Guide (Roman English)

## Quick summary
Yeh guide batata hai kaise dusre laptop par project chalana hai (backend Node.js + MySQL, frontend Next.js).

---

## 1) Zaroori cheezen (Prerequisites)
- Node.js (LTS) aur npm
  ```powershell
  node --version
  npm --version
  ```
- MySQL Server
  ```powershell
  mysql --version
  ```
- (Optional) Git

---

## 2) Project copy/clone karna
- Git use kar ke:
  ```powershell
  git clone <your-repo-url> "D:\AutoSRS"
  cd "D:\AutoSRS"
  ```
- Agar ZIP copy hai to extract karo aur folder open karo.

---

## 3) MySQL setup (database banana)
- MySQL CLI open karo:
  ```powershell
  mysql -u root -p
  ```
- Phir SQL commands chalao:
  ```sql
  CREATE DATABASE chatbot_db;
  USE chatbot_db;

  CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  exit;
  ```

---

## 4) Backend configuration
- `backend/.env.example` already project mein hai. Copy karo aur values set karo:
  ```powershell
  cd backend
  Copy-Item .env.example .env
  notepad .env
  ```
- `.env` mein kam se kam yeh set karo:
  - `DB_PASSWORD` (MySQL password)
  - `JWT_SECRET` (koi strong secret)
  - `CORS_ORIGIN` (development ke liye `*` chal jaega)

Example `.env`:
```
PORT=5000
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_NAME=chatbot_db
JWT_SECRET=change_this_to_a_strong_secret
JWT_EXPIRE=7d
NODE_ENV=development
CORS_ORIGIN=*
```

---

## 5) Dependencies install karna
- Backend dependencies:
  ```powershell
  cd D:\path\to\project\backend
  npm install
  ```
- Frontend dependencies (project root):
  ```powershell
  cd D:\path\to\project
  npm install
  ```

---

## 6) Servers chalana (2 terminals recommended)
Terminal A (Backend):
```powershell
cd D:\path\to\project\backend
npm start
```
Terminal B (Frontend):
```powershell
cd D:\path\to\project
npm run dev
```
- Backend default: `http://localhost:5000`
- Frontend default: `http://localhost:3000` (agar port busy ho to console alag port show karega)

---

## 7) Quick tests (verify)
- Backend health check (browser ya curl):
  ```text
  http://localhost:5000/api/health
  ```
- Frontend open karo:
  ```text
  http://localhost:3000
  ```
- Signup test karo: `http://localhost:3000/signup`

---

## 8) Useful terminal commands
- View all users (backend):
  ```powershell
  cd D:\path\to\project\backend
  node viewUsers.js
  ```
- Kill all node processes (agar ports blocked ho):
  ```powershell
  Get-Process -Name node | Stop-Process -Force
  ```
- Remove Next build cache (agar lock error aaye):
  ```powershell
  Remove-Item "D:\path\to\project\.next" -Recurse -Force -ErrorAction SilentlyContinue
  ```

---

## 9) Common problems & solutions
- MySQL connection error (ECONNREFUSED): ensure MySQL service start hai.
  ```powershell
  net start MySQL80
  ```
- Port in use (EADDRINUSE): kill existing node process ya change port.
- CORS problems: `.env` mein `CORS_ORIGIN` set karo aur backend restart karo.

---

## 10) Optional: One-line copy steps (quick)
1. Clone project
```powershell
git clone <repo-url> "D:\AutoSRS"; cd "D:\AutoSRS"
```
2. Backend setup + run
```powershell
cd backend; Copy-Item .env.example .env; # Edit .env manually
npm install; npm start
```
3. Frontend run (new terminal)
```powershell
cd D:\AutoSRS; npm install; npm run dev
```

---



---

*File created: SETUP_GUIDE_ROMAN.md*