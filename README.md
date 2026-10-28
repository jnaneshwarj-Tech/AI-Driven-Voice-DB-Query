# AI-Driven Voice & Text-Based Student Database Management System

<div align="center">

![System Status](https://img.shields.io/badge/System%20Status-Production%20Ready-brightgreen?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.10+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![MySQL](https://img.shields.io/badge/Database-MySQL%208.0-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![Kannada Support](https://img.shields.io/badge/Multilingual-Native%20Kannada%20%2B%20English-FF9933?style=for-the-badge)
![Security](https://img.shields.io/badge/Security-AST%20SQL%20Guard%20%2B%20RBAC-red?style=for-the-badge)

</div>

---

## 📋 Table of Contents
1. [Project Overview](#-project-overview)
2. [Key Capabilities & Features](#-key-capabilities--features)
3. [End-to-End System Architecture](#-end-to-end-system-architecture)
4. [Kannada & Multilingual Query Engine](#-kannada--multilingual-query-engine)
5. [Student Lifecycle Management (VTU-Aligned)](#-student-lifecycle-management-vtu-aligned)
6. [Security, RBAC & Email OTP Recovery](#-security-rbac--email-otp-recovery)
7. [Reporting, Analytics & Visualizations](#-reporting-analytics--visualizations)
8. [File Architecture & Code Map (Where to Find & Edit Code)](#-file-architecture--code-map)
   - [Backend Modules & Responsibilities](#backend-architecture--file-guide)
   - [Frontend Modules & Responsibilities](#frontend-architecture--file-guide)
9. [Database Schema Reference](#-database-schema-reference)
10. [Installation & Setup Guide](#-installation--setup-guide)
11. [Configuration & Environment Variables](#-configuration--environment-variables)
12. [Verification & Testing](#-verification--testing)

---

## 📌 Project Overview
The **AI-Driven Voice & Text-Based Student Database Management System** is an enterprise-grade platform created for universities and colleges. It bridges human language and relational databases, allowing administrators, faculty, and office staff to interact with academic data using natural spoken or typed language in both **English and Kannada (ಕನ್ನಡ)**.

Instead of writing complex SQL joins, users simply type or speak queries such as:
- *"Show all 5th semester students with CGPA above 8.5"*
- *"ಕಂಪ್ಯೂಟರ್ ಸೈನ್ಸ್ ವಿದ್ಯಾರ್ಥಿಗಳ ಪಟ್ಟಿ ತೋರಿಸಿ"* (Show computer science students)
- *"3rd sem male students from Bangalore with father name Rudrappa"*
- *"Update attendance for USN 1MS21CS001 to 88%"*

The platform automatically parses intent, resolves typos using fuzzy matching, generates schema-compliant SQL, validates security constraints via Abstract Syntax Tree (AST) analysis, executes the query against MySQL, and renders structured data tables, analytical charts, or printable PDF documents.

---

## 🚀 Key Capabilities & Features

### 🎙️ 1. Multilingual Voice & Natural Language Querying
- **Voice-to-Text & Speech Recognition**: Integrated Web Speech API supporting real-time speech input in English (`en-IN`) and Kannada (`kn-IN`).
- **Phonetic Kannada Input**: Real-time transliteration engine allowing users to type Kannada phonetically using English characters (e.g., typing *"vidyarthigalu"* produces *"ವಿದ್ಯಾರ್ಥಿಗಳು"*).
- **Hybrid Intent Resolution**: Multi-stage parsing combining deterministic rule sets with Google Gemini LLM fallback.
- **7-Layer Levenshtein Fuzzy Search**: Auto-corrects misspelled student names, father names, locations, and departments.

### 🎓 2. Complete Academic Lifecycle Management
- **VTU Scheme Alignment**: Built-in tracking of VTU regulations, maximum duration rules, and semester progressions.
- **11 Lifecycle States**: `Active`, `Temporary Discontinuation`, `Detained (Attendance)`, `Detained (Backlogs)`, `Readmission Pending`, `Rejoined-Active`, `Transferred-Out`, `Transferred-In`, `Dropped Out`, `Rusticated/Suspended`, `Graduated`.
- **Identity & USN Continuity**: When students rejoin under a new USN or scheme, previous USNs are linked via `student_identity_links` without merging or deleting historical records.
- **Audited History**: All status transitions append to `student_lifecycle_events` with timestamps, reason codes, and authorized actor IDs.

### 🛡️ 3. Security, Access Guard & Password Recovery
- **AST SQL Injection Guard**: Uses `sqlparse` syntax tree analysis to block unauthorized DDL (`DROP`, `ALTER`, `TRUNCATE`), malicious subqueries, and unauthorized writes.
- **Role-Based Access Control (RBAC)**:
  - `Admin`: Full control over system configuration, user management, backups, and destructive actions.
  - `Staff`: Read and write operational permissions (querying, uploading files, creating readmission requests, updating grades).
  - `Viewer`: Read-only access with automatic masking of sensitive columns (Aadhar, phone, email).
- **SMTP OTP Password Reset**: 3-step OTP password recovery (Email verification $\to$ 6-digit OTP delivery $\to$ Password update) with rate limiting and exponential backoff.

### 📊 4. Reporting, Analytics & Visualization
- **Print-Ready PDF Reports**: Automated PDF generation featuring college branding, student profiles, semester grade transcripts, and fee summaries.
- **Interactive Dashboards**: Dynamic bar graphs, SGPA distribution curves, and branch statistics powered by Recharts.
- **Multi-Format Export**: Single-click export of any query or filtered view to Excel (`.xlsx`), CSV, or PDF.

### 📂 5. Ingestion, Bulk Upload & 1-Click Undo
- **Smart Column Mapper**: Accepts raw Excel (`.xlsx`, `.xls`) or CSV sheets and maps varying column headers (e.g., *"Reg No"*, *"USN"*, *"RollNumber"*) to canonical database fields.
- **Transaction-Safe Rollback**: Destructive updates and bulk file imports generate undo checkpoints allowing immediate restoration of previous state.
- **Automated Daily Backups**: Background APScheduler triggers automated daily database dumps to `backend/backups/`.

---

## 🏛️ End-to-End System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          PRESENTATION LAYER                            │
│  React 18 · Vite · TailwindCSS · Web Speech API · Kannada Transliterate │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST (Axios)
┌───────────────────────────────────▼────────────────────────────────────┐
│                       FASTAPI BACKEND GATEWAY                          │
│                                                                        │
│   ┌───────────────────────┐             ┌──────────────────────────┐   │
│   │   Auth & Security     │             │  Multi-Language Engine   │   │
│   │  JWT · RBAC · Argon2  │             │  kannada_processor.py    │   │
│   └──────────┬────────────┘             └────────────┬─────────────┘   │
│              │                                       │                 │
│   ┌──────────▼───────────────────────────────────────▼─────────────┐   │
│   │              Query & Intent Orchestration Engine               │   │
│   │     routes_query.py · intent_fields.py · canonical_fields.py   │   │
│   └──────────┬───────────────────────────────────────┬─────────────┘   │
│              │                                       │                 │
│   ┌──────────▼────────────┐             ┌────────────▼─────────────┐   │
│   │ Deterministic Builder │             │  RAG + Gemini Fallback   │   │
│   │  rag_sql_generator.py │             │       llm_service.py     │   │
│   └──────────┬────────────┘             └────────────┬─────────────┘   │
│              │                                       │                 │
│   ┌──────────▼───────────────────────────────────────▼─────────────┐   │
│   │                  AST SQL Security Validator                    │   │
│   │                 query_security_validator.py                    │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
└───────────────────────────────────┼────────────────────────────────────┘
                                    │ Connection Pool (mysql-connector)
┌───────────────────────────────────▼────────────────────────────────────┐
│                           DATABASE LAYER                               │
│  MySQL 8.0: students · marks · users · lifecycle_events · audit_logs   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🌐 Kannada & Multilingual Query Engine

The multilingual engine allows native Kannada speakers and bilingual staff to query the database seamlessly.

### How it Works:
1. **Frontend Language Toggle**: Users can switch query mode between **English**, **ಕನ್ನಡ (Kannada)**, or **Bilingual**.
2. **Phonetic Transliteration (`kannadaTransliteration.js`)**: Converts typed English phonetics into Kannada script on the fly using Google Input Tools API with offline fallback tables.
3. **Voice Recognition**: Web Speech recognition automatically switches between `en-IN` and `kn-IN` based on user selection.
4. **Backend Keyword Normalization (`kannada_processor.py`)**:
   - Maintains a 200+ keyword dictionary mapping Kannada academic terms to canonical schema fields:
     - `ವಿದ್ಯಾರ್ಥಿಗಳು` $\to$ `students`
     - `ಫಲಿತಾಂಶ / ಅಂಕಗಳು` $\to$ `marks / results`
     - `ಉತ್ತೀರ್ಣ` $\to$ `passed`
     - `ಅನುತ್ತೀರ್ಣ` $\to$ `failed`
     - `೩ನೇ ಸೆಮಿಸ್ಟರ್` / `3ನೇ ಸೆಮಿಸ್ಟರ್` $\to$ `3rd semester`
   - Preserves proper nouns (student names, college locations) so exact search is unaffected.
5. **Bilingual Presentation**: Results return with localized headers and Kannada metric summaries.

---

## 🔄 Student Lifecycle Management (VTU-Aligned)

The lifecycle engine implements university-standard academic continuity rules without corrupting historical student data:

```
                  ┌───────────────┐
                  │    Active     │
                  └──┬───┬─────┬──┘
                     │   │     │
       ┌─────────────┘   │     └─────────────┐
       ▼                 ▼                   ▼
┌──────────────┐ ┌───────────────┐ ┌───────────────────┐
│  Temporary   │ │   Detained    │ │  Transferred-Out  │
│Discontinue   │ │(Att./Backlog) │ └───────────────────┘
└──────┬───────┘ └───────┬───────┘
       │                 │
       └─────────┬───────┘
                 ▼
       ┌───────────────────┐
       │Readmission Pending│
       └─────────┬─────────┘
                 │ (Admin Approval)
                 ▼
       ┌───────────────────┐
       │  Rejoined-Active  │ (Linked via student_identity_links)
       └───────────────────┘
```

- **Zero Data Loss**: Status changes never delete past marks, attendance records, or fee transactions.
- **USN Identity Linking**: Preserves relationships when a readmitted student is assigned a new USN.
- **Audit Logs**: Every transition records `previous_status`, `new_status`, `reason`, `authorized_by`, and `timestamp`.

---

## 🔒 Security, RBAC & Email OTP Recovery

### AST SQL Safety & Guard
Every query passes through `query_security_validator.py`:
- Parses raw SQL into an Abstract Syntax Tree using `sqlparse`.
- Rejects any query containing prohibited DDL or administrative statements (`DROP`, `ALTER`, `GRANT`, `REVOKE`, `TRUNCATE`).
- Prevents unbounded `DELETE` or `UPDATE` statements by enforcing explicit `WHERE` clauses.

### 3-Step OTP Password Reset Flow
```
Step 1: Enter Username/Email ──▶ Generate 6-Digit Cryptographic OTP (Expires in 120s)
                                          │ (Sent via SMTP or logged in dev)
Step 2: Enter OTP            ──▶ Backend Validates Hash & Generates Single-Use Reset Token
Step 3: Set New Password     ──▶ Token Consumed, Password Hashed with bcrypt
```

---

## 📊 Reporting, Analytics & Visualizations

- **PDF Generator (`report_service.py`)**: Generates formatted, printable PDF documents containing college headers, student particulars, semester-wise grade tables, and signatures.
- **Interactive Visualizations (`ResultChart.jsx`, `AnalyticsDashboard.jsx`)**: Renders SGPA vs CGPA bar charts, category breakdowns, and performance curves.
- **Dynamic GPA Table (`GpaTable.jsx`)**: Formats GPA results with conditional color tagging (distinction, first class, backlog alert).

---

## 📁 File Architecture & Code Map

Use this guide whenever you want to locate, understand, or modify any feature in the codebase.

### Backend Architecture & File Guide
All backend services run under the `backend/` directory using Python and FastAPI.

| File Path | Description & Features Inside | When & Why to Edit |
|---|---|---|
| [`backend/main.py`](file:///c:/Users/manoj/Desktop/major/backend/main.py) | Application entry point. Initializes FastAPI, CORS middleware, database pools, APScheduler, and registers all API routers. | Modify when registering new routers, changing server ports, or configuring global middleware. |
| [`backend/config.py`](file:///c:/Users/manoj/Desktop/major/backend/config.py) | Configuration manager. Reads environment variables (`.env`) for MySQL, JWT secret, Gemini API key, and SMTP credentials. | Edit to add new environment variables or change default settings. |
| [`backend/database.py`](file:///c:/Users/manoj/Desktop/major/backend/database.py) | Core MySQL database layer. Manages connection pooling, index creation, auto-migration (`_add_col_if_missing`), transactions, and safe execution. | Edit if changing MySQL connection parameters or adding startup migration rules. |
| [`backend/canonical_fields.py`](file:///c:/Users/manoj/Desktop/major/backend/canonical_fields.py) | Canonical field mapping dictionary. Maps all variations and aliases of student attributes (e.g., `reg_no` $\to$ `usn`) and column definitions. | Edit when adding new columns to the student schema or defining new column aliases. |
| [`backend/intent_fields.py`](file:///c:/Users/manoj/Desktop/major/backend/intent_fields.py) | Maps user intent categories to target schema fields and SQL expressions. | Edit when training the natural language engine on new query patterns. |
| [`backend/kannada_processor.py`](file:///c:/Users/manoj/Desktop/major/backend/kannada_processor.py) | Kannada language NLP processor. Contains 200+ academic keyword mappings, ordinal translation (3ನೇ $\to$ 3rd), and normalization logic. | Edit when adding new Kannada words, transliteration rules, or localized labels. |
| [`backend/rag_sql_generator.py`](file:///c:/Users/manoj/Desktop/major/backend/rag_sql_generator.py) | Deterministic SQL builder & RAG engine. Translates parsed intent into optimized MySQL queries, joins, and aggregates. | Edit when adding new complex SQL query patterns or calculation rules. |
| [`backend/llm_service.py`](file:///c:/Users/manoj/Desktop/major/backend/llm_service.py) | Google Gemini LLM API integration. Handles schema-aware prompting for queries that exceed deterministic rules. | Edit if switching AI models, adjusting temperature, or modifying LLM prompts. |
| [`backend/query_security_validator.py`](file:///c:/Users/manoj/Desktop/major/backend/query_security_validator.py) | AST-based SQL security validator. Analyzes syntax trees with `sqlparse` to block injection, DDL, and unauthorized updates. | Edit when refining security rules or adding allowed SQL functions. |
| [`backend/fuzzy_search.py`](file:///c:/Users/manoj/Desktop/major/backend/fuzzy_search.py) | 7-layer Levenshtein fuzzy matching engine. Resolves typos in student names, father names, and departments. | Edit if adjusting fuzzy match thresholds or scoring algorithms. |
| [`backend/lifecycle.py`](file:///c:/Users/manoj/Desktop/major/backend/lifecycle.py) | Student lifecycle state machine. Implements 11 status codes, VTU scheme rules, identity linking, and transition validations. | Edit when changing lifecycle rules or university regulations. |
| [`backend/email_service.py`](file:///c:/Users/manoj/Desktop/major/backend/email_service.py) | SMTP email dispatcher. Handles 6-digit OTP generation, validation, expiration, and templated HTML delivery. | Edit when changing email templates, OTP expiration times, or SMTP logic. |
| [`backend/report_service.py`](file:///c:/Users/manoj/Desktop/major/backend/report_service.py) | PDF generation service using ReportLab. Builds styled, printable student profiles and grade transcripts. | Edit when customizing PDF layout, college logos, or report headers. |
| [`backend/file_parser.py`](file:///c:/Users/manoj/Desktop/major/backend/file_parser.py) | Multi-format file ingestion engine. Parses Excel (`.xlsx`, `.xls`), CSV, and JSON student records. | Edit when adding support for new upload formats or validation rules. |
| [`backend/ai_column_mapper.py`](file:///c:/Users/manoj/Desktop/major/backend/ai_column_mapper.py) | Smart column mapper for file uploads. Matches uploaded file headers to canonical DB columns. | Edit when adding new recognized column header synonyms. |
| [`backend/scheduler.py`](file:///c:/Users/manoj/Desktop/major/backend/scheduler.py) | APScheduler background scheduler. Runs automated daily database backups at midnight. | Edit when changing backup frequency or adding scheduled tasks. |
| [`backend/routes_auth.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_auth.py) | Authentication endpoints (`/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/verify-otp`, `/auth/reset-password`). | Edit when modifying authentication workflows or session handling. |
| [`backend/routes_query.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_query.py) | Core query execution endpoint (`/query`). Coordinates NLP normalization, SQL generation, security validation, and response formatting. | Edit when adding query pre-processing or response formatting. |
| [`backend/routes_lifecycle.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_lifecycle.py) | Lifecycle management endpoints (`/api/lifecycle/*`). Manages status changes, readmission requests, and identity links. | Edit when exposing new lifecycle actions or eligibility endpoints. |
| [`backend/routes_files.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_files.py) | File upload and management endpoints (`/files/*`). Handles bulk data imports and preview tables. | Edit when changing upload limits or file handling flows. |
| [`backend/routes_export.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_export.py) | Data export endpoints (`/export/pdf`, `/export/excel`, `/export/csv`). | Edit when modifying export parameters or report downloads. |
| [`backend/routes_backup.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_backup.py) | Database backup & restore endpoints (`/backup/*`). Manages manual backup creation and point-in-time restoration. | Edit when changing backup storage or restoration rules. |
| [`backend/routes_undo.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_undo.py) | Rollback & Undo endpoints (`/undo/*`). Restores database state after bulk edits or updates. | Edit when altering rollback transaction mechanics. |
| [`backend/routes_update.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_update.py) | Record update endpoints (`/update/*`). Handles single-field edits and bulk student profile updates. | Edit when modifying field update validations. |
| [`backend/routes_monitor.py`](file:///c:/Users/manoj/Desktop/major/backend/routes_monitor.py) | System health and diagnostic monitoring endpoints (`/monitor/*`). | Edit when adding new health checks or metric endpoints. |

---

### Frontend Architecture & File Guide
The web interface is built with React 18, Vite, and TailwindCSS located in `frontend/`.

| File Path | Description & Features Inside | When & Why to Edit |
|---|---|---|
| [`frontend/src/App.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/App.jsx) | Root React component and router setup. Configures routes for `/login`, `/register`, `/forgot-password`, `/reset-password`, and `/dashboard`. | Edit when adding new client routes or modifying page navigation guards. |
| [`frontend/src/main.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/main.jsx) | React application DOM mount point and global context wrappers. | Edit when adding global state providers or wrapping root context. |
| [`frontend/src/index.css`](file:///c:/Users/manoj/Desktop/major/frontend/src/index.css) | Global stylesheet with Tailwind CSS directives and custom animations. | Edit when modifying global typography, scrollbars, or theme styling. |
| [`frontend/src/pages/Dashboard.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/pages/Dashboard.jsx) | Main application hub. Houses the voice microphone, natural language search bar, language selector, data tables, charts, and activity feeds. | Edit when altering dashboard layout, search bar behavior, or top-level UI panels. |
| [`frontend/src/pages/Login.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/pages/Login.jsx) | Login and authentication portal. Contains login form, role switching, and integrated forgot-password OTP modal. | Edit when changing login UI, branding, or credentials flow. |
| [`frontend/src/pages/Register.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/pages/Register.jsx) | User registration screen for creating new Admin/Staff accounts. | Edit when adding new user registration fields. |
| [`frontend/src/pages/ResetPassword.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/pages/ResetPassword.jsx) | Direct token password reset page (fallback for link-based password recovery). | Edit when customizing direct link password recovery. |
| [`frontend/src/components/LanguageSelector.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/LanguageSelector.jsx) | Language selection dropdown (English / ಕನ್ನಡ / Bilingual) with state persistence. | Edit when adding additional supported languages or changing selector styles. |
| [`frontend/src/components/LifecycleDashboard.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/LifecycleDashboard.jsx) | Academic lifecycle management panel. Displays student statuses, readmission review queues, and identity links. | Edit when customizing lifecycle UI workflows or action modals. |
| [`frontend/src/components/CombinedStudentView.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/CombinedStudentView.jsx) | Detailed 360° student modal. Displays personal particulars, semester marks, fee records, and lifecycle history. | Edit when adding new student profile tabs or changing record layout. |
| [`frontend/src/components/FileExplorer.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/FileExplorer.jsx) | Upload manager and preview component. Handles drag-and-drop CSV/Excel imports with column mapping previews. | Edit when modifying file upload UI or column mapping confirmation dialogs. |
| [`frontend/src/components/GpaTable.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/GpaTable.jsx) | Formatted table component for semester SGPA and cumulative CGPA. | Edit when changing table styling, sorting, or GPA badge colors. |
| [`frontend/src/components/ResultChart.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/ResultChart.jsx) | Interactive chart component rendering analytics with Recharts. | Edit when adding new chart types or customizing visual data trends. |
| [`frontend/src/components/BackupRestore.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/BackupRestore.jsx) | Backup and restore UI modal for triggering manual database dumps and restoring snapshots. | Edit when modifying backup interface options or download controls. |
| [`frontend/src/components/StudentEditor.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/StudentEditor.jsx) | Inline record editor allowing Staff and Admin to edit student information safely. | Edit when changing form fields or validation checks during record editing. |
| [`frontend/src/components/PrintReport.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/components/PrintReport.jsx) | Printable view component optimized for browser print dialogs. | Edit when modifying printable CSS stylesheets. |
| [`frontend/src/utils/kannadaTransliteration.js`](file:///c:/Users/manoj/Desktop/major/frontend/src/utils/kannadaTransliteration.js) | Phonetic transliteration engine. Converts Roman/English keystrokes into Kannada script with 200+ offline word maps. | Edit when adding new Kannada phonetic mapping rules or common words. |
| [`frontend/src/utils/simpleKannadaInput.js`](file:///c:/Users/manoj/Desktop/major/frontend/src/utils/simpleKannadaInput.js) | Offline fallback keyboard map for direct Kannada Unicode characters. | Edit when tuning character composition logic. |
| [`frontend/src/services/api.js`](file:///c:/Users/manoj/Desktop/major/frontend/src/services/api.js) | Axios API client instance with interceptors for JWT token injection and automatic 401 handling. | Edit when changing base API URLs or adding global request headers. |
| [`frontend/src/context/ThemeContext.jsx`](file:///c:/Users/manoj/Desktop/major/frontend/src/context/ThemeContext.jsx) | Theme provider managing light and dark mode preferences. | Edit when adding custom color themes or theme settings. |

---

## 🗄️ Database Schema Reference

The database runs on **MySQL 8.0**. Below are the primary tables:

1. **`students`**: Core entity table storing personal details (`usn`, `name`, `gender`, `dob`, `blood_group`, `father_name`, `mother_name`, `phone`, `email`, `address`, `current_sem`, `status`, `lifecycle_status`, etc.).
2. **`marks`**: Academic performance records (`usn`, `semester`, `sgpa`, `cgpa`, `year`, `exam_month_year`).
3. **`users`**: System accounts (`id`, `username`, `email`, `password_hash`, `role`).
4. **`password_reset_requests`**: OTP verification tracking (`id`, `user_id`, `otp_hash`, `otp_expires_at`, `attempt_count`, `reset_token_hash`).
5. **`student_lifecycle_events`**: Append-only lifecycle event logs (`event_id`, `usn`, `event_type`, `previous_status`, `new_status`, `reason`, `authorized_by`).
6. **`student_identity_links`**: Links previous and new USNs for readmitted students (`link_id`, `primary_usn`, `related_usn`, `relation_type`).
7. **`query_history`**: Audit trail of executed natural language queries and generated SQL.
8. **`audit_logs`**: Records modifications, updates, and rollbacks.

---

## 💻 Installation & Setup Guide

### Prerequisites
- **Python**: Version 3.10 or higher
- **Node.js**: Version 18.0 or higher (with npm)
- **MySQL**: MySQL Server 8.0 or higher

### 1. Database Setup
Ensure MySQL is running, then create the database schema:
```bash
# Connect to your MySQL instance
mysql -u root -p < database/schema.sql
```

### 2. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create and activate a Python virtual environment
python -m venv .venv

# Windows activation:
.venv\Scripts\activate

# Linux/macOS activation:
# source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt

# Configure your environment file
copy .env.example .env
# (Edit .env with your MySQL password and optional Gemini API key)

# Start the backend server
uvicorn main:app --reload --port 8000
```
Backend API will be accessible at: `http://localhost:8000`

### 3. Frontend Setup
In a new terminal window:
```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Start the Vite development server
npm run dev
```
Frontend application will be accessible at: `http://localhost:5173`

---

## ⚙️ Configuration & Environment Variables

Copy `.env.example` in `backend/` to `.env` and provide your credentials:

```ini
# MySQL Database Connection
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=student_db
MYSQL_POOL_SIZE=20

# JWT Authentication
SECRET_KEY=generate_a_secure_random_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# Google Gemini API (For AI SQL Generation Fallback)
GEMINI_API_KEY=your_gemini_api_key_here

# SMTP Email Configuration (For Password Reset OTP)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_college_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_college_email@gmail.com

# Server Settings
APP_HOST=0.0.0.0
APP_PORT=8000
DEV_RELOAD=1
```

---

## 🧪 Verification & Testing

The repository includes a comprehensive unit and integration test suite located in `backend/tests/`:

```bash
# Run the complete test suite
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

### Test Coverage Highlights:
- **`test_query_security_validator.py`**: Validates AST SQL injection protection and DDL rejection.
- **`test_lifecycle.py`**: Verifies VTU lifecycle state machine transitions and audit logging.
- **`test_sprint1.py`**: Tests authentication, query engine, and database integrity.
- **`test_master_phase2_language.py`**: Verifies Kannada phonetic normalization and keyword resolution.
- **`test_master_phase7_security.py`**: Ensures role-based authorization rules.
- **`test_export_verification.py`**: Tests PDF, Excel, and CSV export generation.

---

## 💻 Windows Desktop Application & Automated Tooling

The platform includes an **Electron Windows Desktop Client** tailored for staff workstations connected to the College LAN with zero MySQL, Python, or database configuration required on client machines.

For full infrastructure architecture, firewall rules, least-privilege MySQL provisioning, and service installation, see [DEPLOYMENT.md](file:///c:/Users/manoj/Desktop/major/DEPLOYMENT.md).

### Quick PowerShell Scripts

| Script | Purpose | Command |
|---|---|---|
| **Environment Check** | Verifies Python 3.10+, Node.js, venv, and directories | `powershell -ExecutionPolicy Bypass -File .\scripts\check-environment.ps1` |
| **Dev Environment Setup** | Initializes venv, installs all pip and npm packages | `powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev.ps1` |
| **Run Dev Servers** | Starts backend (port 8000) and frontend (port 5173) | `powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1` |
| **Desktop Dev Mode** | Launches desktop Electron app with Vite hot-reload | `npm run desktop:dev` |
| **Desktop Packager** | Compiles frontend and builds Windows desktop app | `powershell -ExecutionPolicy Bypass -File .\scripts\build-desktop.ps1` |
| **Master Test Suite** | Runs configuration audit, build check, and test battery | `powershell -ExecutionPolicy Bypass -File .\scripts\test-all.ps1` |
| **Production Backend Deploy** | Audits host and starts production Uvicorn service | `powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1 -BindHost 0.0.0.0` |

### Desktop Configuration (`config.json`)
The desktop client dynamically reads `config.json` next to its executable on launch to connect to the central server:
```json
{
  "apiBaseUrl": "http://192.168.1.100:8000/api",
  "organizationName": "Government Engineering College Mosalehosahalli, Hassan",
  "enableDevTools": false
}
```

---

## 📄 License
This project is developed for college academic administration and student data management. All rights reserved.
