# AI-Driven Voice & Text Based Database Query Automation System For College

A production-ready full-stack application that translates natural language (voice or text) into optimized, secure MySQL queries using the Nvidia LLM API and RAG (Retrieval-Augmented Generation) for database schema understanding.

## Architecture Highlights
- **Backend**: Python FastAPI with MySQL connection pooling, AI query optimization, deep SQL Injection & query validation, and Pandas/ReportLab for data export.
- **Frontend**: React.js 18 + TailwindCSS, including Web Speech API voice capture, JWT-based authentication, interactive modals, and an audit history layout.
- **AI Core**: RAG pipeline where user queries are semantically mapped strictly to necessary table schemas -> prompt sent to NVIDIA LLM -> SELECT * operations pruned by Optimizer -> Security Validation block applied.

## Setup Instructions

### 1. Requirements & Database Setup (MySQL)
1. Install MySQL and ensure it is running on your system.
2. The system stores database credentials in the `backend/.env` file. You can configure your `mysql_password` inside it:
    ```env
    mysql_password=your_mysql_password
    ```

### 2. Backend Setup
1. Open a terminal and create/activate a Python virtual environment:
   ```bash
   cd backend
   python -m venv .venv

   # Activate on Windows:
   .venv\Scripts\activate

   # Activate on Mac/Linux:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your NVIDIA API key in the `backend/.env` file:
   ```env
   NVIDIA_API_KEY=your_api_key_here
   ```
4. **Initialize the Database:** Run the database initialization script to automatically create the `student_db` database, tables, and default users:
   ```bash
   python init_mysql.py
   ```
5. Run the backend server:
   ```bash
   python main.py
   ```
   *The backend will be available at `http://localhost:8000`. You can access the API documentation at `http://localhost:8000/docs`.*

### 3. Frontend Setup
1. Open a new terminal and navigate to the `frontend` directory.
2. Install Node.js dependencies:
   ```bash
   cd frontend
   npm install
   ```
3. Start the React (Vite) development server:
   ```bash
   npm run dev
   ```
4. Open your browser to the URL provided in the terminal (usually `http://localhost:5173`).
5. **Login Credentials:**
   * Role: **Admin** -> Username: `admin` | Password: `admin123`
   * Role: **Staff** -> Username: `staff` | Password: `staff123`

## Deployment Considerations
Codebase inherently uses Clean Architecture. Easy drop-ins available for Analytics Dashboards, Redis Cache caching layer before the LLM, or WebSockets implementation mapping long-duration queries.

---

# 📘 PROJECT REPORT: Phase-1
**Title:** AI & NLP Driven Smart Student Database Management System using MySQL
**Branding Institution:** VISVESVARAYA TECHNOLOGICAL UNIVERSITY & GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN (DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING)

---

## 1. Abstract
The **AI & NLP Driven Smart Student Database Management System** is a state-of-the-art enterprise academic ERP designed to bridge the operational gap between natural human interaction (text/voice) and relational MySQL database infrastructures. Utilizing advanced Natural Language Processing (NLP), a spelling-resilient 7-layer fuzzy-phonetic matching engine, and Retrieval-Augmented Generation (RAG) schema mappings, the platform instantly compiles voice or text instructions into secure, highly optimized MySQL queries. The system incorporates robust bulk spreadsheet ingestion, an automated semester progression algorithm mapping VTU USN patterns, and a 5-minute transaction rollback engine using point-in-time serialized JSON snapshots. The product ensures absolute security against AST injection and delivers professional branded reporting options, setting a new standard for modern academic administrative environments.

---

## 2. Introduction
In typical educational institutes, administration involves managing vast volumes of student records, grades, and historical logs. Standard ERPs are hampered by multi-layered menus, rigid filter constraints, and severe intolerance for spelling errors. This project solves this friction by providing a unified Natural Language Query interface that allows administrators to communicate with the database just as they would with a human assistant. Backed by FastAPI, React, and MySQL, the system delivers high responsiveness, strict transactional boundaries, and multi-format branded document outputs.

---

## 3. Problem Statement
Academic student administration faces significant roadblocks:
1. **Intolerance for Human Error:** Traditional SQL search tools (using exact string `LIKE '%name%'`) fail on typing mistakes, leading to false-negative results or redundant entry creation.
2. **Ambiguity Overwrites:** When multiple students share identical or highly similar names, legacy systems merge or overwrite fields, or show incorrect records, leading to severe data contamination.
3. **Complex Ingestion Layouts:** Bulk data imports from varied departments involve different Excel columns, requiring massive manual formatting to align with rigid database tables.
4. **Permanent Accidental Deletions:** Deleting student or academic mark rows in relational databases is immediately permanent, lacking any instant rollback capabilities short of restoring massive server backups.

---

## 4. Project Objectives
- **Lenient Spelling Suggestion & Strict Execution Pipeline:** Build a robust 7-layer phonetic fuzzy search engine (Levenshtein, Soundex, Trigram, Double Metaphone) that runs leniently (≥0.20 score) for real-time keystroke matching and strictly (≥0.70 score) for executing final query inputs.
- **Ambiguity Detection & Multi-Student Interception:** Block unauthorized auto-merges or ambiguous data display. When queries match multiple students, the frontend prompts the user to select the target record by USN.
- **Rule-Based AI Column Mapper & Wide-to-Long Excel Parser:** Automatically read CSV or Excel files, auto-detect the real header by scanning keywords, map arbitrary columns to canonical columns, and unpivot wide semester matrices (e.g. `sem_1_sgpa`, `sem_2_sgpa`) to normalized database tables.
- **Automatic VTU Semester Calculation:** Leverage regex parsing on Visvesvaraya Technological University (VTU) USNs to extract admission years, identify lateral entry statuses, determine estimated active semesters, and auto-flag graduated student records.
- **5-Minute Point-In-Time Undo Snapshot System:** Protect all academic records with a secure undo buffer. Any INSERT, UPDATE, DELETE, or bulk UPLOAD generates a pre-state serialized JSON dump that can be rolled back instantly via a secure UUID token.

---

## 5. Existing vs Proposed System

| Component / Metric | Existing System (Traditional ERP) | Proposed System (Smart AI ERP) |
|--------------------|-----------------------------------|--------------------------------|
| **Search Paradigm** | Rigid substring searches (`LIKE`); completely fails on typo discrepancies. | 7-layer NLP pipeline (Levenshtein, Trigram, Soundex, Double Metaphone). |
| **Data Ingestion** | Rigid spreadsheet imports. Mismatched columns crash database insertion. | Smart AI Column Mapper; automatically unpivots wide semester columns. |
| **Data Safety** | Operations are permanent. Deletes require full DB restoration to recover. | 5-minute Point-in-Time recovery window powered by JSON snapshots. |
| **Reporting Layout** | Generates generic, unformatted tables without branding or metadata. | Unified branded export model with signatures, institutional headers, and university logo. |
| **Ambiguity Handling**| Shows first match or merges distinct rows arbitrarily. | Intercepts matches, showing USN-specific selection cards to prevent contamination. |

---

## 6. System Architecture & Working Pipeline
The operational pipeline represents a continuous, highly secured loop:
1. **User Request Intake:** The system receives natural language text or voice queries via React or Web Speech API.
2. **Intent Analysis & Extraction:** The query engine identifies target name tokens, checks query intent (academic, personal, or full), and filters the relevant context.
3. **RAG Schema Retrieval & SQL Compilation:** Schema layouts are retrieved and injected into prompt templates. The NVIDIA LLM API converts the instructions into highly optimized SQL.
4. **Security Auditing & AST Pruning:** The SQL query goes through the SQL Security Validator (parsing abstract syntax trees via `sqlparse`). SQL injection patterns or destructive statements (e.g., `DELETE` or `UPDATE` lacking a `WHERE` clause) are blocked, and security logs are recorded.
5. **MySQL Pool Execution:** Valid queries are executed against the MySQL database. If zero matching rows are returned, the engine triggers the 7-layer phonetic/fuzzy matching fallback.
6. **Ambiguity Check & Multi-Match Resolution:** If the query matches multiple distinct students, the system returns a selection list for the user to resolve by USN.
7. **Interactive Display & Branded Export:** Secure results are rendered via React components, and users can export identical branded PDFs, Excel sheets, and CSVs with integrated user signature blocks.

---

## 7. Technical Modules Description
- **7-Layer Fuzzy Search Core:** Calculates phonetic codes (Double Metaphone, Soundex) and spelling distances (Levenshtein, Jaro-Winkler, Character Trigram) to construct real-time leniency and strict query thresholds.
- **RAG & SQL Generation Engine:** Evaluates tables dynamically, maps natural language predicates to database structures, and generates optimized queries.
- **AST Security Validator:** Operates as a security barrier. Analyzes SQL commands to detect injection, unauthorized queries, and ensures every transaction is safe.
- **Smart Excel Ingestor & Wide-to-Long Parser:** Automates bulk imports by scanning for header rows, resolving column name aliases, and normalizing nested academic matrices.
- **Unified Branded Reporting System:** Implements a single Report Model shared across PDF, Excel, and CSV templates, ensuring matching records, institutional logos, and computer-filled preparer signatures.
- **JSON Transaction Undo Pipeline:** Backs up academic state prior to any destructive operation, storing it in the database as a JSON string to enable instant rollback.

---

## 8. Database Schema Design (MySQL)
The database structure is designed to enforce relational integrity and facilitate instantaneous point-in-time recovery:
- `users`: Stores system credentials, password hashes (bcrypt), active role (Admin or Staff), and personalized UI theme configurations.
- `students`: Central registry storing personal student information (USN, name, DOB, blood group, address, father name, current semester, academic status) protected by a UNIQUE INDEX on `usn`.
- `marks`: Stores semester academic performance linked to USN via FOREIGN KEY cascading, protected by a unique composite constraint (`usn`, `semester`) to prevent duplicate grade entries.
- `global_undo_snapshots`: High-speed transaction table tracking `undo_token` (UUID), `snapshot_data` (serialized JSON of pre-state rows), performed by, status, and creation timestamps.
- `query_history`: Keeps an audit trail of user queries, generated SQL strings, execution time, and execution status.
- `security_logs`: Captures unauthorized commands, blocked SQL injections, and suspicious activities for administrative audit review.

---

## 9. 7-Layer NLP Search Engine Logic
Typos and phonetic naming mistakes are resolved through a robust 7-layer pipeline:
1. **Exact Match:** Direct case-sensitive string matching. Returns a 100% confidence match.
2. **Normalized Exact:** Performs lowercase, unicode stripping, and trims punctuation.
3. **Prefix Match:** Checks if any database student name token starts with the search input.
4. **Substring Match:** Scans for search input within database name tokens.
5. **Phonetic Encoding:** Runs **Soundex** and **Double Metaphone** algorithms to generate phonetic keys, ensuring names that sound similar but are spelled differently (e.g., 'Sudheer' and 'Sudhir') match.
6. **Character Trigram Similarity:** Computes character n-grams and determines similarity index ($2 \times \text{intersection} / \text{union}$).
7. **String Distance Calculation:** Computes **Levenshtein Distance** and **Jaro-Winkler** metrics to determine structural similarity.

---

## 10. Smart Semester Progression Logic
VTU USNs (e.g., `1GC21CS035`) are parsed with a specialized regex `^(\d)([A-Za-z]{2})(\d{2})([A-Za-z]{2})(\d{2,3})$`:
- **Course Duration:** First digit represents course duration in years (e.g. 4 for B.E.).
- **Admission Year:** Group 3 extracts short year (e.g. `21` -> 2021).
- **Student Type:** Roll number (Group 5) determines entry mode. Numbers $\ge 400$ designate Lateral Entry, and numbers $< 400$ regular entry.
- **Progression Calculation:** The system calculates estimated semesters by comparing admission year to the current date:
  $$\text{years\_diff} = \text{current\_year} - \text{admission\_year}$$
  $$\text{sem} = \begin{cases} \text{years\_diff} \times 2 + 1 & \text{if current month is July--December (ODD)} \\ \text{years\_diff} \times 2 & \text{if current month is January--June (EVEN)} \end{cases}$$
  Lateral Entry students automatically receive a $+2$ semester shift.
- **Graduation Status:** If computed semester is greater than $\text{duration} \times 2$, academic status updates to `GRADUATED`. Otherwise, active status maps to `ACTIVE`.

---

## 11. File Ingestion & AI Mapping
Excel/CSV bulk ingestion is managed through a strict, zero-loss pipeline:
1. **Header Row Identification:** Scans the first 20 rows of uploaded spreadsheets using known keywords (e.g., 'usn', 'roll_no', 'name') to locate the exact starting header.
2. **Rule-Based AI Column Mapper:** Resolves column aliases using a comprehensive, blocklist-protected dictionary. For example, 'Reg Number' maps to 'usn', and 'Fathers Name' to 'father_name'.
3. **Wide-Format Unpivoting:** Unpivots wide sheets (columns: sem_1_sgpa, sem_2_sgpa) into standardized normalized rows (Semester, SGPA).
4. **USN Validation & Merge:** Validates USNs using standard regex. If valid, records are merged (upserted); duplicate rows are identified and flagged.

---

## 12. Undo & Point-in-Time Recovery
To guarantee complete transactional safety, a 5-minute Point-In-Time recovery window is enforced:
- **Deletion/Update Interception:** Prior to executing any destructive command, the system runs a select query to fetch all target rows.
- **Snapshot Generation:** Stores the full student profiles and academic marks as a serialized JSON dump in the `global_undo_snapshots` table, returning a unique UUID token.
- **Recovery Execution:** Upon post-requesting the token to `/api/undo/restore/{token}`, the system deletes the newly modified data, reads the JSON snapshot, and re-inserts the exact original values.

---

## 13. UI/UX Architecture
The frontend is constructed using modular React component design:
- **Dashboard Workspace:** Provides a single-page reactive shell hosting a collapsible sidebar and unified search hub.
- **Live Suggestion Panel:** A highly interactive dropdown showing spelling matches with badges (EXACT, FUZZY, PHONETIC).
- **Interactive Data Tables:** Generates responsive paginated grids with column sorting and search filtering.
- **Activity Feed & Rollback Panel:** Allows administrators to review security logs and trigger instant undo rollbacks in real time.

---

## 14. Results & Implemented Features
The Phase-1 implementation succeeds in delivering all core modules:
✔ Verified 7-layer fuzzy phonetic search engine resolving severe typos.
✔ Operational async text and voice-dictated query generation pipeline.
✔ Zero-loss spreadsheet ingestion engine with automatic unpivoting.
✔ Strict security validation blocking malicious AST injection patterns.
✔ Verified 5-minute Point-In-Time Undo Recovery with JSON snapshots.
✔ Institutional branded PDF, Excel, and CSV export modules.

---

## 15. Remaining Issues & Future Scope
Current limitations and developmental plans for Phase-2 include:
- **Current Limitations:** Local MySQL service configuration dependencies (requires manual administrative startup); single-instance file upload cache (susceptible to cache expiration on server restart).
- **Future Scope:** Integration of vector embedding semantic search using Milvus/ChromaDB to handle complex intent mappings; implementation of Redis-based query caching to bypass LLM generation for identical queries; integration of automated WebSockets for multi-user real-time notification feeds.

---

## 16. Conclusion
Phase-1 of the AI & NLP Driven Student Database Management System successfully establishes a robust, highly responsive, and secure foundation. By combining advanced natural language translation with professional institutional reporting and transaction rollback capabilities, the system reduces administrative workload, prevents data loss, and delivers an exceptionally smooth, premium user experience. The architectural designs and modules verified in this phase will serve as a solid launchpad for advanced AI integrations in future iterations.

