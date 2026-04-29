# AI-Driven Voice & Text Based Database Query Automation System

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

## Features Matrix

| Feature | Description | File |
|---------|-------------|------|
| **Schema Indexing & RAG** | Extracts metadata layout and dynamically filters to Relevant schemas only based on text input. | `backend/schema_indexer.py`, `backend/schema_retriever.py` |
| **SQL Optimizer Layer** | Detects `SELECT *` and forcibly translates them to exact explicitly declared schema columns. | `backend/query_optimizer.py` |
| **Security Validation Layer**| Rejects `DROP, ALTER, TRUNCATE` or `DELETE/UPDATE` without `WHERE`. Validates AST injection attacks natively via `sqlparse`. | `backend/query_security_validator.py` |
| **Audit Log Pipeline** | Logs every generated AI SQL, query runtime in seconds, and security breach attempts in MySQL. | `backend/query_engine.py` |
| **Export Formats** | Real-time downloading of DB results fetched by LLM dynamically returned precisely via StreamingResponse format (PDF, Excel, CSV). | `backend/routes.py` |
| **Delete Safety (Frontend)** | Double confirmation modals populating dynamically prior to final delete string submission over API framework. | `frontend/src/pages/Dashboard.js` |
| **Voice Query** | Harnesses native `webkitSpeechRecognition` to dictate natural language dynamically over the execute window context. | `frontend/src/pages/Dashboard.js` |

## Deployment Considerations
Codebase inherently uses Clean Architecture. Easy drop-ins available for Analytics Dashboards, Redis Cache caching layer before the LLM, or WebSockets implementation mapping long-duration queries.
