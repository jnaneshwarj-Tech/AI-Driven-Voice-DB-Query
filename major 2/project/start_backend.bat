@echo off
echo Starting FastAPI backend on http://localhost:8001
echo API Docs: http://localhost:8001/docs
echo.
cd backend
set OPENAI_API_KEY=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
python app.py
pause
