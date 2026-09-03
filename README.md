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

## End-to-End Workflow
```text
User signs in
   |
   v
User enters text, speaks a query, or types Kannada phonetically
   |
   v
Frontend normalizes input and sends it to the FastAPI backend
   |
   v
Backend loads the database schema and builds AI context
   |
   v
AI service generates SQL from the user's intent
   |
   v
Security validator checks the SQL before execution
   |
   v
Query engine executes approved read/write operations in MySQL
   |
   v
Results, history, audit details, and export actions return to the dashboard
```

## Major Implementation
| Area | Implementation | Main locations |
| --- | --- | --- |
| Authentication | JWT login, role checks, password reset, email OTP, and reset-token expiry | `backend/auth.py`, `backend/routes_auth.py`, `frontend/src/pages/ForgotPassword.jsx` |
| AI query engine | Schema-aware prompting, SQL generation, query execution, and result formatting | `backend/llm_service.py`, `backend/query_engine.py`, `backend/rag_sql_generator.py` |
| Query security | Validation of generated SQL and protection against unsafe or destructive input | `backend/query_security_validator.py` |
| Database management | MySQL connection, schema initialization, dynamic columns, and canonical field mapping | `backend/database.py`, `backend/auto_schema_manager.py`, `database/schema.sql` |
| Data ingestion | CSV/Excel parsing, validation, bulk inserts, and duplicate handling | `backend/file_parser.py`, `backend/routes_files.py` |
| Kannada input | Phrase transliteration, mixed-language handling, space/pause processing, Google API integration, and local fallback | `frontend/src/utils/`, `frontend/src/pages/Dashboard.jsx`, `backend/kannada_processor.py` |
| Recovery and reporting | Backup/restore, undo windows, audit history, and PDF/Excel/CSV exports | `backend/routes_backup.py`, `backend/routes_export.py`, `backend/graduation_manager.py` |

### Kannada Implementation Details
- English phonetic input is converted to Kannada while the user types.
- Complete phrases are sent with context, so later words are not lost.
- Space-key conversion, smart delay detection, mixed Kannada/English text, numbers, names, and database identifiers are supported.
- Google Input Tools provides transliteration, with a local dictionary fallback when the service is unavailable.
- Kannada voice input, backend semantic translation, language selection, fuzzy search, and response-language modes use the same query pipeline.
- Entity values such as USNs, names, table names, and column names are protected during translation.

### Authentication and Password Reset Details
- Registration and login use hashed passwords, JWT access tokens, and role-based permissions.
- Password reset requests do not reveal whether an email address exists.
- OTPs have expiry, resend cooldowns, request rate limits, maximum-attempt locking, and one-account-per-email enforcement.
- Reset tokens are short-lived, single-use, and issued only after successful OTP verification.
- SMTP settings support Gmail and other providers; development mode can be used for local testing.

### Query and Data Safety Details
- User intent is converted to SQL only after schema context is collected.
- Generated SQL is validated before execution to block unsafe statements and injection patterns.
- Uploads are parsed in batches, validated against the active schema, and recorded for audit and undo operations.
- Fuzzy matching helps resolve spelling variations without changing protected identifiers.

## Supporting Documentation
The README is the primary project guide and consolidated implementation reference. Detailed implementation notes and setup records are retained here for troubleshooting and handover:

- [Context and phrase transliteration fix](CONTEXT_UPDATE_KANNADA_FIX.md)
- [Kannada transliteration debugging](DEBUG_KANNADA.md)
- [English-to-Kannada typing guide](ENGLISH_TO_KANNADA_TYPING.md)
- [Final Kannada transliteration fix](FINAL_KANNADA_FIX.md)
- [Google transliteration integration](GOOGLE_OFFICIAL_API.md)
- [Kannada implementation](KANNADA_IMPLEMENTATION_COMPLETE.md)
- [Kannada keyboard setup](KANNADA_KEYBOARD_SETUP.md)
- [Kannada transliteration fix](KANNADA_TRANSLITERATION_FIX.md)
- [Password reset system](PASSWORD_RESET_SYSTEM_COMPLETE.md)
- [Quick Kannada start](QUICK_START_KANNADA.md)
- [Simple Kannada input solution](SIMPLE_SOLUTION.md)
- [Smart space detection](SMART_SPACE_DETECTION.md)
- [Space-key transliteration](SPACE_KEY_TRANSLITERATION.md)
- [Kannada testing guide](TEST_KANNADA_NOW.md)

## Project Structure
```text
major/
├── backend/         # FastAPI backend, database logic, APIs, and AI integration
├── frontend/        # React frontend and UI components
├── database/        # database setup and schema support
├── src/             # shared source modules
├── public/          # public frontend assets
├── README.md        # primary project guide, workflow, and implementation status
├── *KANNADA*.md     # retained Kannada implementation and troubleshooting notes
├── *PASSWORD*.md    # retained password-reset implementation notes
├── package.json     # frontend package metadata
├── package-lock.json
├── .gitignore       # generated files ignored by Git
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
The README is the primary source of truth for project implementation and progress. Supporting documents preserve detailed setup and troubleshooting context.

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

