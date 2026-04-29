from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from auth import hash_password, verify_password, create_token
from database_connection import execute_query, execute_write

router = APIRouter(prefix="/api/auth", tags=["Auth"])

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str  # Admin | Staff

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/register")
def register(req: RegisterRequest):
    if req.role not in ("Admin", "Staff"):
        raise HTTPException(400, "Role must be Admin or Staff.")
    existing = execute_query("SELECT id FROM users WHERE username=%s OR email=%s", (req.username, req.email))
    if existing:
        raise HTTPException(400, "Username or email already exists.")
    hashed = hash_password(req.password)
    execute_write(
        "INSERT INTO users (username, email, password, role) VALUES (%s,%s,%s,%s)",
        (req.username, req.email, hashed, req.role)
    )
    return {"success": True, "message": "Registered successfully. Please login."}

@router.post("/login")
def login(req: LoginRequest):
    rows = execute_query("SELECT * FROM users WHERE username=%s", (req.username,))
    if not rows:
        raise HTTPException(401, "Invalid username or password.")
    user = rows[0]
    if not verify_password(req.password, user['password']):
        raise HTTPException(401, "Invalid username or password.")
    token = create_token({"sub": user['username'], "role": user['role']})
    return {"access_token": token, "token_type": "bearer", "role": user['role'], "username": user['username']}
