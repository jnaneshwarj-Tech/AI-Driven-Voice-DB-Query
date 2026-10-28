# College Student Database ERP — Deployment & Operations Guide

## Government Engineering College Mosalehosahalli, Hassan
### Production LAN Architecture & Windows Desktop Distribution

---

## 1. System Architecture & Network Topology

The **GEC Student Database Management System** is architected for strict institutional data governance, high availability, and secure local area network (LAN) operation.

```
                              [ College LAN Boundary ]
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        │                                                                 │
  ┌─────▼───────────────┐     ┌─────────────────────┐     ┌───────────────▼─────┐
  │ Staff Windows PC 1  │     │ Staff Windows PC 2  │     │ Staff Windows PC N  │
  │ (Electron Desktop)  │     │ (Electron Desktop)  │     │ (Electron Desktop)  │
  │ Zero MySQL/Python   │     │ Zero MySQL/Python   │     │ Zero MySQL/Python   │
  └──────────┬──────────┘     └──────────┬──────────┘     └──────────┬──────────┘
             │                           │                           │
             │ HTTP/JSON                 │ HTTP/JSON                 │ HTTP/JSON
             └───────────────────┬───────┴───────────────────────────┘
                                 │ (Port 8000 / 443)
                                 ▼
                    ┌─────────────────────────┐
                    │ Central College Server  │
                    │ IP: 192.168.1.100       │
                    │                         │
                    │ ┌─────────────────────┐ │
                    │ │  FastAPI Backend    │ │
                    │ │  (Python 3.10+)     │ │
                    │ └──────────┬──────────┘ │
                    │            │ SQL        │
                    │            ▼ (Port 3306)│
                    │ ┌─────────────────────┐ │
                    │ │  MySQL 8.0 Server   │ │
                    │ │  (college_db)       │ │
                    │ └─────────────────────┘ │
                    └─────────────────────────┘
```

### Key Security & Operational Principles
1. **Zero Database on Staff Desktops**: Staff PCs run lightweight Electron desktop binaries. No MySQL client, no Python runtime, and no database credentials exist on client machines.
2. **Centralized Authority**: All database transactions, AST security audits, RBAC enforcement, file storage, and audit logs execute solely on the Central College Server.
3. **LAN Isolation**: The central MySQL database (Port 3306) listens strictly on `127.0.0.1` or the server's internal interface. It is NEVER exposed to client computers or the public Internet.
4. **Dynamic Central Configuration**: The desktop client reads `config.json` at launch. If the college server IP changes, IT administrators update one JSON file without rebuilding or reinstalling client software.

---

## 2. Developer Workstation Quickstart

### Prerequisites
- **Operating System**: Windows 10 / 11 (64-bit)
- **Python**: 3.10 or higher (added to PATH)
- **Node.js**: 18.x or 20.x LTS (with npm)
- **MySQL**: 8.0 (local instance or network reachable)
- **PowerShell**: Version 5.1 or PowerShell 7

### Step 1: Clone Repository
```powershell
git clone <repository-url>
cd major
```

### Step 2: Automated Environment Check
Verify all system prerequisites and directories:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-environment.ps1
```

### Step 3: One-Command Development Setup
Set up the Python virtual environment, install backend and frontend packages, and create configuration templates:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-dev.ps1
```

### Step 4: Configure Local Backend Secrets
Open `backend/.env` and update your local database credentials:
```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DB=student_db_staging
SECRET_KEY=generate_a_random_32_character_string_here
GEMINI_API_KEY=your_gemini_api_key_or_leave_dummy
```

### Step 5: Run Automated Tests
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-all.ps1
```

### Step 6: Start Development Servers
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1
```
- FastAPI Backend: `http://localhost:8000/docs`
- React Frontend (Vite): `http://localhost:5173`

To launch the desktop client with live Vite hot-reloading:
```powershell
npm run desktop:dev
```

---

## 3. Central College Server IT Administrator Deployment Guide

### A. Recommended Server Specifications
- **Operating System**: Windows Server 2019/2022 or Ubuntu Server 22.04 LTS
- **CPU**: 4 Cores or higher
- **RAM**: 8 GB minimum (16 GB recommended for MySQL buffer pool + AI processing)
- **Disk**: 100 GB SSD storage (accommodates student document uploads and automated backups)
- **Static IP**: Assign a dedicated static IPv4 address (e.g., `192.168.1.100`)

---

### B. MySQL Database Setup & Security Hardening

1. **Log in to MySQL as Root**:
   ```sql
   mysql -u root -p
   ```

2. **Create Database**:
   ```sql
   CREATE DATABASE IF NOT EXISTS college_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

3. **Initialize Schema & Seed Data**:
   ```powershell
   mysql -u root -p college_db < database/schema.sql
   ```

4. **Create Least-Privilege Application User**:
   Do **NOT** configure the application backend to connect as MySQL `root`. Create a dedicated service user restricted to the local host or internal network:
   ```sql
   CREATE USER 'gec_erp_user'@'localhost' IDENTIFIED BY 'PutStrongRandomPasswordHere!';
   GRANT SELECT, INSERT, UPDATE, DELETE ON college_db.* TO 'gec_erp_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
   *(Note: The ERP uses parameterized statements and application-level constraints; it never requires DROP, ALTER, or GRANT permissions for normal operation).*

---

### C. Server Backend Configuration & Startup

1. **Populate Production Configuration (`backend/.env`)**:
   ```env
   # Database Connection
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=gec_erp_user
   MYSQL_PASSWORD=PutStrongRandomPasswordHere!
   MYSQL_DB=college_db
   MYSQL_POOL_SIZE=20

   # Security & Authentication
   SECRET_KEY=PutStrongRandom64CharacterSecretKeyHere!
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=480

   # AI / LLM Configuration
   GEMINI_API_KEY=AIzaSy...your_gemini_key
   LLM_MODEL=gemini-2.5-flash

   # Email Service (VTU / Staff OTPs)
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=college.erp@gechassan.ac.in
   SMTP_PASSWORD=your_app_specific_password

   # Storage Paths (Ensure write permissions)
   UPLOAD_DIR=uploads
   BACKUP_DIR=storage/backups
   ```

2. **Deploy and Start the Backend Service**:
   Run the deployment script:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1 -BindHost 0.0.0.0 -Port 8000
   ```

3. **Configuring as a Persistent Windows Service (Optional & Recommended)**:
   Use [NSSM (Non-Sucking Service Manager)](https://nssm.cc/) to keep the backend running 24/7 and auto-restart on server reboot:
   ```powershell
   nssm install GECStudentDBService "C:\path\to\major\backend\.venv\Scripts\python.exe" "-m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4"
   nssm set GECStudentDBService AppDirectory "C:\path\to\major\backend"
   nssm start GECStudentDBService
   ```

---

### D. Windows Firewall Rules
Run in an elevated PowerShell prompt on the Central Server to allow traffic from the College LAN:
```powershell
New-NetFirewallRule -DisplayName "GEC Student DB ERP (Port 8000)" `
    -Direction Inbound `
    -LocalPort 8000 `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress 192.168.1.0/24
```
*Ensure MySQL port 3306 is explicitly NOT allowed through the firewall for external subnets.*

---

## 4. Windows Desktop Client Packaging & Staff PC Installation

### Step 1: Build the Desktop Application (On Developer/IT Machine)
Run the automated packaging script:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-desktop.ps1
```
This compiles the production React frontend with relative asset paths (`base: './'`) and packages the Electron container.

Generated artifacts are located in `desktop/release/`:
- **Unpacked Portable Folder**: `desktop/release/win-unpacked/`
- **Installer Executable**: `desktop/release/GEC Student Database Management Setup 1.0.0.exe`

### Step 2: Configure Central Server Address for Staff Computers
In `desktop/release/win-unpacked/config.json` (or created beside the executable on staff PCs):
```json
{
  "apiBaseUrl": "http://192.168.1.100:8000/api",
  "organizationName": "Government Engineering College Mosalehosahalli, Hassan",
  "enableDevTools": false
}
```

### Step 3: Distribute to Staff Workstations
- Copy the `win-unpacked` folder to a read-only IT Network Share:
  `\\fileserver\CollegeApps\GEC-Student-Database\`
- Or run the installer `GEC Student Database Management Setup 1.0.0.exe` on staff computers.
- Staff launch the application via desktop shortcut or `GEC Student Database Management.exe`.

---

## 5. Backup, Disaster Recovery & Rollback Procedures

### Daily Automated Database Backups
Schedule a Windows Task or Linux cron job to dump `college_db` daily at 01:00 AM:
```powershell
$date = Get-Date -Format "yyyyMMdd_HHmmss"
mysqldump -u gec_erp_user -p"YourPassword" college_db > "C:\path\to\major\storage\backups\college_db_$date.sql"
```

### Restoring from a Backup
In case of catastrophic hardware failure or accidental data modification:
```powershell
mysql -u root -p college_db < "C:\path\to\major\storage\backups\college_db_20261028_010000.sql"
```

### Application Rollback Procedure
1. Stop the backend service: `nssm stop GECStudentDBService`
2. Check out the previous stable Git commit or restore application directory from backup.
3. Verify configuration: `python -c "from config import settings; settings.validate_startup()"`
4. Restart service: `nssm start GECStudentDBService`

---

## 6. IT Administrator Operational Checklist

- [ ] Central MySQL 8.0 server installed and running.
- [ ] Schema initialized from `database/schema.sql`.
- [ ] Least-privilege MySQL service user created with strong password.
- [ ] Backend `.env` configured with production secrets and non-default `SECRET_KEY`.
- [ ] Firewall rule active for port 8000 (restricted to college LAN subnet).
- [ ] Port 3306 blocked from all external subnets.
- [ ] Daily backup task configured and verified.
- [ ] Desktop client `config.json` pointing to server LAN IP (`http://192.168.1.x:8000/api`).
- [ ] Desktop client tested and verified on a test staff PC.
