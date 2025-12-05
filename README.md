# FaceAuth - Premium Facial Recognition Attendance System

![Status](https://img.shields.io/badge/Status-Active-success)
![Stack](https://img.shields.io/badge/Stack-React%20%7C%20FastAPI%20%7C%20PostgreSQL-blue)

A state-of-the-art attendance system powered by advanced facial recognition, featuring a decoupled architecture with a premium Glassmorphism UI and a robust Python backend.

## 🚀 Features

### Frontend (React + Vite)
- **Premium UI**: Modern Glassmorphism design with dark mode aesthetics.
- **Real-time Dashboard**: Live camera feeds streaming via WebSockets.
- **Interactive Management**: 
  - Employee management with photo registration (6 angles).
  - Attendance logs with date filtering and Excel export.
  - Camera RTSP URL configuration.
- **Security**: JWT-based authentication and protected routes.

### Backend (FastAPI + Python)
- **High Performance**: Asynchronous API built with FastAPI.
- **Face Recognition**: Powered by `insightface` and `FAISS` for millisecond-level identification.
- **Vector Database**: Uses PostgreSQL `pgvector` for storing and searching face embeddings.
- **Live Streaming**: Efficient frame processing and WebSocket broadcasting.

## 🛠️ Architecture

The project is structured into two main applications:

```
├── backend/            # Python FastAPI Server
│   ├── api.py          # Main Application Entry
│   ├── services.py     # Core Logic (Face Rec, DB, Auth)
│   ├── setup_db.py     # Database Schema Initialization
│   └── ...
└── frontend/           # React Application
    ├── src/
    │   ├── pages/      # Dashboard, Employees, Login...
    │   ├── components/ # Reusable UI Components
    │   └── ...
    └── ...
```

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL (with `vector` extension recommended)

### 1. Backend Setup

```bash
cd backend

# Install Dependencies
pip install -r requirements.txt

# Configure Environment
# Edit .env file if needed (default: localhost:5432, user: oasys)

# Initialize Database
python3 setup_db.py

# Create Admin User
python3 admin.py

# Run Server
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup

```bash
cd frontend

# Install Dependencies
npm install

# Run Development Server
npm run dev
```

### 3. Usage
Open `http://localhost:5173` in your browser.
- Login with the admin credentials you created.
- Configure your camera RTSP URLs in the **Cameras** section.
- Start monitoring attendance on the **Dashboard**.

## 📝 License
Personal Project - All Rights Reserved.
