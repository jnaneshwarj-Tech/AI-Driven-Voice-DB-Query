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

## Consolidated Implementation Record
All implementation notes, fixes, setup instructions, test cases, and progress updates are maintained in this README. No separate feature-update files are required.

### Kannada Input Processing
1. The user selects Kannada mode or uses the native Windows Kannada keyboard.
2. English phonetic text is collected without interrupting normal typing.
3. A space key or short idle delay triggers conversion of the pending word or phrase.
4. Complete phrases are sent to Google Input Tools so transliteration keeps word context.
5. Kannada text, numbers, names, USNs, and mixed English/Kannada content are preserved correctly.
6. A local dictionary handles common words immediately when the API is unavailable.
7. Transliteration requests are locked and debounced to prevent overlapping responses and cursor jumps.
8. Protected entities are excluded from translation before the backend sends the query to the AI service.

### Translation Services
The system uses two complementary translators:

- **Frontend phonetic transliteration:** `frontend/src/utils/googleTransliterate.js` calls the Google Input Tools endpoint with the Kannada input code `kn-t-i0-und`. It returns Kannada suggestions for Roman/English phonetic typing while preserving already-Kannada text and technical terms.
- **Frontend local fallback:** `frontend/src/utils/kannadaTransliteration.js` contains Kannada character mappings, common-word mappings, protected English terms, and fallback conversion when a remote suggestion is unavailable.
- **Backend semantic translation:** `backend/translation_service.py` converts Kannada Unicode queries into English meaning before the existing SQL pipeline. It calls Google's translation endpoint with Kannada as the source and English as the target.
- **Backend fallback:** If the translation service fails, `kannada_processor.normalize_query()` performs keyword normalization so the query can still reach intent detection.
- **Entity protection:** USNs, numbers, marks, years, semesters, names, and technical terms such as `CGPA`, `SGPA`, `CSE`, and `EMAIL` are replaced with placeholders before translation and restored afterward.
- **Language modes:** Query requests support `english`, `kannada`, and `mixed`; response language can independently be selected as English or Kannada.

Translation is therefore not a single word replacement. Typing conversion happens in the browser for a natural input experience, while semantic translation happens in the backend so the AI query pipeline receives understandable intent without corrupting database values.

### File Attachments and Data Import
Staff users can attach files from the dashboard through `POST /api/files/upload`. Supported formats are:

- CSV, XLSX, and XLS for student and academic data
- JSON and TXT for structured or text-based imports
- PDF, PNG, JPG, and JPEG for supported document/image workflows

The upload process works in two stages:

1. The backend validates the file type and non-empty content, stores the original content in the upload cache, records metadata in `uploaded_files`, and marks it `pending`.
2. The user chooses **Update Database**. The parser maps varied headers to canonical fields, validates values, classifies every row, and imports the result in one transaction.

Every parsed row receives a visible outcome: `NEW`, `UPDATED`, `UNCHANGED`, `DUPLICATE`, `INVALID`, or `REJECTED`. Large files are processed in chunks, database changes are audited, cache entries are cleared when necessary, and transaction rollback prevents partial imports.

### Personal, Academic, and Complete Profiles
Natural-language intent detection keeps student information focused:

- **Personal queries** return identity and profile fields such as name, USN, date of birth, parents, blood group, address, phone, email, Aadhaar, gender, category, and status.
- **Academic queries** return semester, SGPA, CGPA, marks, grades, year, and performance information.
- **Complete profile queries** recognize phrases such as “full information”, “entire profile”, “everything about”, or “academic and personal”, then merge personal data, academic rows, and graduation information.
- **Full or mixed queries** return the complete available result when the request does not belong to one exclusive category.
- **Ambiguous names** can produce a selection suggestion when multiple USNs match a similar search term.

The frontend presents the result in separate personal and academic views, while the backend keeps the query and response pipeline unified.

### Kannada Fix History
- Fixed the original first-word-only behavior by changing word-by-word API calls to complete-phrase requests.
- Added space-key conversion so the previous word is translated immediately after a space.
- Added smart delay detection so pauses between words no longer cancel conversion.
- Reduced unnecessary request latency and added a local fallback dictionary.
- Added mixed-language handling so already-Kannada text and English identifiers are not skipped or corrupted.
- Added browser-console and backend-console diagnostics for API, timer, dictionary, and fallback states.

### Kannada Testing Checklist
- Hard-refresh the frontend after a transliteration change.
- Select Kannada input mode and type a phonetic word such as `namaskara`.
- Confirm the word with Space and verify it becomes Kannada.
- Test multiple words with a pause between them, a complete sentence, numbers, names, and mixed English/Kannada text.
- Verify that the query reaches the backend, SQL generation still succeeds, and database identifiers remain unchanged.
- If Google conversion is unavailable, verify that local dictionary words still convert and ordinary English remains usable.

### Password Reset Implementation
- Registration rejects duplicate email addresses and login uses secure password hashing.
- Forgot-password requests return the same public response whether or not an account exists.
- OTPs are generated securely, expire after a short period, allow limited attempts, and lock after repeated failures.
- OTP resend requests use a cooldown and hourly rate limit.
- Successful OTP verification creates a short-lived, single-use reset token.
- New passwords are validated, hashed, and stored without exposing credentials in logs or responses.
- SMTP configuration supports Gmail and other providers; development mode supports local testing.
- The database migration adds the OTP, reset-token, attempt-count, expiry, and cooldown fields required by the flow.

### OTP and Email Generation
The password-reset process is implemented by `backend/routes_auth.py` and `backend/email_service.py`:

1. The user submits a username and registered email to `POST /api/auth/forgot-password`.
2. The backend verifies both values, applies hourly request limits and resend cooldowns, and creates a cryptographically secure six-digit OTP using Python's `secrets` module.
3. Only a SHA-256 hash of the OTP is stored in MySQL. The plaintext OTP is never stored in the database or included in the API response.
4. `email_service.py` generates a multipart email containing both a plain-text version and a branded HTML version with the application name, OTP, expiry notice, and safety instructions.
5. SMTP sends the message using TLS and the configured `MAIL_FROM_NAME`, `MAIL_FROM`, server, port, username, and password.
6. In development mode, when SMTP credentials are absent, the OTP is printed to the backend console instead of being sent externally.
7. `POST /api/auth/verify-reset-otp` validates expiry, attempt count, and the stored hash, then returns a short-lived reset token.
8. `POST /api/auth/reset-password` validates the token, updates the hashed password in a transaction, and makes the token single-use.

The default security controls are a 120-second OTP expiry, 5 failed-attempt limit, 30-second resend cooldown, 5 requests per email per hour, and 10-minute reset-token expiry. Generic responses prevent account enumeration.

### Query and Upload Implementation
- The frontend sends text or voice intent to the backend through one query workflow.
- The backend reads schema metadata, canonicalizes field names, and builds context for the AI model.
- The generated SQL passes security validation before any database operation is allowed.
- Query results include structured rows, history, and audit information for dashboard actions and exports.
- CSV and Excel files are parsed, validated, mapped to the active schema, and inserted in chunks.
- Upload changes support undo windows, duplicate handling, and backup/restore operations.

### Troubleshooting Summary
- Restart the frontend after source changes and use a hard browser refresh to clear Vite assets.
- Check the browser console for transliteration timer/API messages and the backend console for translation/query errors.
- Confirm the Google Input Tools endpoint is reachable; the local dictionary remains the fallback path.
- Confirm the database migration has been executed before testing password reset.
- Keep API keys, SMTP passwords, JWT secrets, and database passwords in `.env`; never commit them.

## Project Structure
```text
major/
├── backend/         # FastAPI backend, database logic, APIs, and AI integration
├── frontend/        # React frontend and UI components
├── database/        # database setup and schema support
├── src/             # shared source modules
├── public/          # public frontend assets
├── README.md        # primary project guide, workflow, and implementation status
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

