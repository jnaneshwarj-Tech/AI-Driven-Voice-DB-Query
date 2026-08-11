# 🚀 Quick Start Guide - AI Student ERP System

## ✅ System Status: READY

---

## 🎯 Start the System

### 1️⃣ Start Backend (Terminal 1)
```bash
cd backend
python main.py
```
✅ Server runs on: **http://localhost:8000**

### 2️⃣ Start Frontend (Terminal 2)
```bash
cd frontend
npm run dev
```
✅ App runs on: **http://localhost:5173**

---

## 🔐 Login

**Default Admin:**
- Username: `admin`
- Password: (check database or create via register)

**Default Staff:**
- Username: `staff01`
- Password: (check database or create via register)

---

## 💡 Key Features

### 🔍 AI Search (Main Tab)
```
Type: "show marks of manoj"
→ Live suggestions appear
→ Click suggestion
→ Results displayed
```

### 📁 Upload Files (Files Tab)
```
1. Click "Upload File"
2. Select Excel/CSV
3. AI maps columns automatically
4. Click "Update Database"
5. See affected records
```

### 📊 Analytics (Analytics Tab)
```
View:
- Semester trends
- Department performance
- CGPA distribution
- Top performers
```

### 🔄 Restore Deleted (Restore Tab)
```
1. See recently deleted students
2. Click "Restore" (5-minute window)
3. Student data fully restored
```

### 📜 Recent Activity (Activity Tab)
```
Track:
- Recent additions
- Recent deletions
- Recent updates
- Recent searches
```

---

## 🎨 Theme Toggle

Click the theme icon in sidebar:
- 🌞 Light Mode
- 🌙 Dark Mode
- 💻 System Auto

---

## 📝 Example Queries

```
✓ "show all students"
✓ "show marks of manoj"
✓ "list students with cgpa > 8"
✓ "find toppers in semester 5"
✓ "show students from CS department"
✓ "display failed students"
✓ "show average marks by department"
```

---

## 🛠️ Troubleshooting

### Backend won't start?
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Frontend won't start?
```bash
cd frontend
npm install
npm run dev
```

### LLM not responding?
✅ **FIXED** - Now using `gemini-flash-latest`
Check `backend/.env`:
```env
GEMINI_API_KEY=AIzaSyAeXRtRA22eclGjVJR_r33Z1qX8scUAS2E
GEMINI_MODEL=gemini-flash-latest
```

### Database connection error?
Check `backend/.env`:
```env
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=Manoj@123
MYSQL_DB=student_db
```

---

## 📊 API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login
- `POST /auth/theme` - Save theme preference

### Queries
- `POST /query/generate` - NLP → SQL
- `POST /query/execute` - Execute confirmed query
- `GET /query/history` - Recent queries
- `GET /query/suggest` - Name suggestions
- `GET /query/analytics` - Dashboard analytics

### Files
- `GET /files/list` - List uploaded files
- `POST /files/upload` - Upload file
- `POST /files/parse/{filename}` - Preview file
- `POST /files/update_db/{filename}` - Import to DB
- `DELETE /files/{filename}` - Delete file

### Export
- `POST /export/excel` - Export to Excel
- `POST /export/csv` - Export to CSV
- `POST /export/pdf` - Export to PDF

### Undo/Restore
- `GET /undo/deleted` - List deleted records
- `POST /undo/restore/{token}` - Restore record
- `GET /undo/activity` - Activity logs

---

## 🎯 Common Tasks

### Add New Student
```
1. Type: "add student john doe usn 4HG23CS100"
2. Confirm operation
3. See success notification
```

### Update Marks
```
1. Upload Excel file with marks
2. AI maps columns
3. Preview data
4. Click "Update Database"
```

### Generate Report
```
1. Run query
2. View results
3. Click "Print" icon
4. Professional PDF generated
```

### Delete Student (with Undo)
```
1. Type: "delete student with usn 4HG23CS100"
2. Confirm operation
3. Toast appears with UNDO button
4. Click UNDO within 5 minutes to restore
```

---

## 📱 UI Navigation

### Sidebar Tabs
- 🔍 **Query** - Main search interface
- 📁 **Files** - Upload & manage files
- 📊 **Analytics** - Charts & insights
- ✅ **Validation** - Data quality checks
- 🔄 **Restore** - Undo deleted records
- 📜 **Activity** - Recent operations

### Top Bar
- 👤 User profile
- 🌓 Theme toggle
- 🔔 Notifications
- 🚪 Logout

---

## ✅ System Health Check

Run these commands to verify:

```bash
# Test LLM connection
cd backend
python test_llm_connection.py
# Expected: ✅ TEST PASSED

# Check backend modules
python -c "import main; print('✓ Backend OK')"
# Expected: ✓ Backend OK

# Verify model config
python -c "from llm_service import llm_service; print('Model:', llm_service.model)"
# Expected: Model: gemini-flash-latest
```

---

## 📖 Documentation

- `SYSTEM_STATUS_REPORT.md` - Complete system status
- `GEMINI_MODEL_FIX.md` - LLM configuration details
- `CONTEXT_TRANSFER_COMPLETE.md` - Recent work summary
- `IMPLEMENTATION_PLAN.md` - Project roadmap

---

## 🎓 Tips & Tricks

### Smart Search
- Type partial names: "manj" → suggests "MANJUNATH H"
- System handles typos and variations
- Phonetic matching for Indian names

### Keyboard Shortcuts
- `Ctrl + K` - Focus search box (if implemented)
- `ESC` - Close modals
- Click outside dropdown to close

### Batch Operations
- Upload Excel with 100s of records
- AI maps columns automatically
- Preview before committing
- Full undo support

---

## 🆘 Support

If issues persist:
1. Check browser console (F12) for errors
2. Check backend terminal for logs
3. Verify `.env` configuration
4. Restart both servers
5. Clear browser cache/localStorage

---

## ✅ Quick Verification

**Everything working?**
- [ ] Backend running on port 8000
- [ ] Frontend running on port 5173
- [ ] Can login successfully
- [ ] Search returns results
- [ ] File upload works
- [ ] Analytics charts display
- [ ] Theme toggle works
- [ ] Undo/restore functional

**If all checked:** 🎉 **System is fully operational!**

---

**Last Updated:** August 4, 2026  
**Version:** 3.0.0  
**Status:** ✅ Production Ready

---

## 🚀 Ready to Go!

Your AI-powered Student ERP System is ready for use. Start both servers and navigate to http://localhost:5173 to begin!
