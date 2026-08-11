from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from auth import verify_password, create_access_token, get_password_hash, get_current_user
from database import db_conn, write_audit_log

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "Staff"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request = None):
    ip = request.client.host if request and request.client else ""

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s OR email=%s", (req.username, req.username))
        user = cur.fetchone()
        cur.close()

    if not user or not verify_password(req.password, user["password_hash"]):
        # Log failed login attempt
        write_audit_log(
            action="LOGIN_FAILED",
            username=req.username,
            role="",
            target_table="users",
            summary=f"Failed login attempt for username: {req.username}",
            success=False,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user["username"], "role": user["role"]})

    # Log successful login
    write_audit_log(
        action="LOGIN_SUCCESS",
        username=user["username"],
        role=user["role"],
        target_table="users",
        summary=f"User {user['username']} ({user['role']}) logged in",
        success=True,
        ip_address=ip,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "role": user["role"],
            "email": user["email"],
            "theme": user.get("theme", "system"),
        },
    }

@router.post("/register")
def register(req: RegisterRequest):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM users WHERE username=%s", (req.username,))
        if cur.fetchone():
            cur.close()
            raise HTTPException(400, "Username already registered")
        cur.execute("SELECT id FROM users WHERE email=%s", (req.email,))
        if cur.fetchone():
            cur.close()
            raise HTTPException(400, "Email already registered")
        role = "Staff" if req.role not in ["Admin", "Staff"] else req.role
        cur.execute(
            "INSERT INTO users (username,email,password_hash,role) VALUES (%s,%s,%s,%s)",
            (req.username, req.email, get_password_hash(req.password), role)
        )
        conn.commit()
        cur.close()

    write_audit_log(
        action="USER_REGISTERED",
        username=req.username,
        role=role,
        target_table="users",
        summary=f"New user registered: {req.username} ({role})",
    )
    return {"message": "User registered successfully"}

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "email": current_user["email"],
        "theme": current_user.get("theme", "system"),
    }

class ThemeRequest(BaseModel):
    theme: str

@router.post("/theme")
def update_theme(req: ThemeRequest, current_user: dict = Depends(get_current_user)):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET theme=%s WHERE username=%s",
            (req.theme, current_user["username"])
        )
        conn.commit()
        cur.close()
    return {"success": True, "theme": req.theme}

@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    """Record logout in audit log. Token invalidation is client-side."""
    write_audit_log(
        action="LOGOUT",
        username=current_user["username"],
        role=current_user["role"],
        target_table="users",
        summary=f"User {current_user['username']} logged out",
    )
    return {"success": True, "message": "Logged out successfully."}
