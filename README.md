# AI-Driven Voice & Text Based Database Query Automation System for College

<div align="center">

![Project Status](https://img.shields.io/badge/Status-Production%20Ready-success)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![React](https://img.shields.io/badge/React-18-61DAFB)
![MySQL](https://img.shields.io/badge/MySQL-Database-4479A1)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)

</div>

A professional AI-powered database assistant for academic and enterprise environments. The system accepts natural-language text or voice input, converts it into secure SQL, validates the generated query, and returns structured data from a MySQL database.

## Overview
This project is designed to remove the friction between humans and databases. Instead of writing SQL manually, users can ask questions in natural language or speak to the system, and the platform translates that request into optimized, safe database queries.

It is built for:
- academic record management
- student database querying
- staff/admin operations
- AI-assisted reporting and export
- secure enterprise-style query processing

## Key Features
- Voice and text query support
- AI-assisted SQL generation from user intent
- Schema-aware query building using database metadata
- SQL validation and injection protection
- Fuzzy matching for typos and name variations
- Bulk CSV/Excel upload and data ingestion support
- Role-based admin and staff access
- Query history and activity tracking
- Undo/restore support for changed records
- Branded PDF/Excel/CSV report export
- Kannada transliteration for English-typed Kannada queries
- Kannada and English mixed-input handling
- Forgot-password flow with OTP verification and reset tokens

## Technology Stack
- Frontend: React, Vite, Tailwind CSS
- Backend: Python, FastAPI
- Database: MySQL
- AI Layer: NVIDIA LLM integration with schema-aware prompting
- Security: SQL validation and query safety checks

## Architecture
The system follows a clean layered structure:

1. Frontend layer
   - user dashboard
   - voice/text input
   - authentication and workflow UI
2. Backend layer
   - API handling
   - query orchestration
   - schema and validation logic
3. AI layer
   - converts natural language to SQL
   - contextual understanding using schema metadata
4. Database layer
   - stores student, mark, audit, and undo information
5. Security layer
   - blocks unsafe or malicious SQL patterns

## Project Structure
```text
major/
├── backend/         # FastAPI backend, database logic, APIs, and AI integration
├── frontend/        # React frontend and UI components
├── database/        # database setup and schema support
├── src/             # shared source modules
├── public/          # public frontend assets
├── package.json     # frontend package metadata
├── package-lock.json
├── .gitignore       # generated files ignored by Git
├── README.md        # project overview and setup guide
└── ...
```

## Prerequisites
- Python 3.10+
- Node.js 18+
- MySQL server running locally
- NVIDIA API key for AI query generation

## Setup Instructions

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Create a `.env` file inside the `backend` folder:
```env
mysql_password=your_mysql_password
NVIDIA_API_KEY=your_api_key_here
```
Initialize the database and start the backend:
```bash
python init_mysql.py
python main.py
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 3. Access the App
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

## Default Login Credentials
- Admin: `admin` / `admin123`
- Staff: `staff` / `staff123`

## Use Cases
- natural language student record lookup
- voice-based database queries
- CSV/Excel bulk import and validation
- query generation without manual SQL writing
- academic reporting and export

## Project Status
The README is the single source of truth for project implementation and progress.

### Implemented
- Natural-language text and voice queries converted into schema-aware SQL
- SQL safety validation, injection protection, fuzzy matching, and query history
- CSV/Excel upload, validation, bulk ingestion, undo/restore, and report export
- Role-based authentication for admin and staff users
- Forgot-password workflow using email OTP verification and short-lived reset tokens
- Kannada transliteration using the Google Input Tools API with local fallback handling
- Kannada input support for complete phrases, mixed English/Kannada text, and pauses between words
- MySQL schema initialization and automatic database-column support

### Planned
- Add automated end-to-end coverage for voice queries, Kannada input, uploads, and password reset
- Add production deployment configuration and secrets-management guidance
- Add screenshots, a maintained architecture diagram, and a short demonstration video
- Improve observability with structured backend logs and user-facing error diagnostics

### Project Presentation
This project is suitable for GitHub portfolio presentation, internship and placement evaluation, academic demonstrations, and real-world AI/database application showcases.

