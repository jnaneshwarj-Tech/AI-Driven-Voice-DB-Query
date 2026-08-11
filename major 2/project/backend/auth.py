import os
import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from db import get_connection

SECRET_KEY = os.getenv("JWT_SECRET", "student_dbms_secret_2024_xK9#mP")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

bearer_scheme = HTTPBearer()

# ── DB setup ────────────────────────────────────────────────────────────────

def _table_exists(cursor, table_name: str) -> bool:
    try:
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        return cursor.fetchone() is not None
    except Exception:
        return False

def init_users_table():
    conn = get_connection()
    cursor = conn.cursor()

    if _table_exists(cursor, "users"):
        cursor.execute("SHOW COLUMNS FROM users")
        cols = {r[0] for r in cursor.fetchall()}
        if "password" not in cols:
            cursor.execute("RENAME TABLE users TO users_old_backup")
            conn.commit()
            print("[Auth] Renamed old users table to users_old_backup")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role ENUM('admin','staff') DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

# ── JWT ──────────────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str, role: str, name: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "name": name,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token.")

# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    return decode_token(credentials.credentials)

def require_staff(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "staff":
        raise HTTPException(403, "Admins are not allowed to modify data.")
    return user

def require_any(user: dict = Depends(get_current_user)) -> dict:
    return user

# ── User DB operations ────────────────────────────────────────────────────────

def register_user(name: str, email: str, password: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        raise HTTPException(400, "Email already registered.")
    hashed = hash_password(password)
    cursor.execute(
        "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, 'staff')",
        (name, email, hashed)
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return {"id": user_id, "name": name, "email": email, "role": "staff"}

def login_user(email: str, password: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if not user or not verify_password(password, user["password"]):
        raise HTTPException(401, "Invalid email or password.")
    token = create_token(user["id"], user["email"], user["role"], user["name"])
    return {
        "token": token,
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
    }
