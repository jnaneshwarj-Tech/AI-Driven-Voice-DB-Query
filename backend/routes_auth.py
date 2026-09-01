import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from auth import verify_password, create_access_token, get_password_hash, get_current_user
from database import db_conn, write_audit_log
from email_service import send_reset_password_email
from config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "Staff"

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

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

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request = None):
    ip = request.client.host if request and request.client else ""
    generic_msg = "If an account exists for this email, a password reset link has been sent."

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, email FROM users WHERE email=%s", (req.email,))
        user = cur.fetchone()

        if not user:
            cur.close()
            write_audit_log(
                action="FORGOT_PASSWORD_REQUEST",
                username=req.email,
                role="",
                target_table="users",
                summary=f"Password reset requested for unknown email: {req.email}",
                success=False,
                ip_address=ip,
            )
            raise HTTPException(status_code=400, detail="No account found with this email address. Please check your registered email.")

        # Generate cryptographically secure random token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now() + timedelta(minutes=20)

        # Invalidate previous unused tokens for this user
        cur.execute(
            "UPDATE password_reset_tokens SET used=1 WHERE user_id=%s AND used=0",
            (user["id"],)
        )

        # Store new token
        cur.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user["id"], token_hash, expires_at)
        )
        conn.commit()
        cur.close()

    reset_link = f"{settings.FRONTEND_URL}/reset-password/{raw_token}"
    send_reset_password_email(req.email, reset_link)

    write_audit_log(
        action="FORGOT_PASSWORD_LINK_SENT",
        username=user["username"],
        role="",
        target_table="users",
        summary=f"Password reset token generated for user {user['username']}",
        success=True,
        ip_address=ip,
    )

    return {
        "message": "Account verified! Click the button below to reset your password.",
        "reset_url": reset_link,
        "token": raw_token,
    }

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request = None):
    ip = request.client.host if request and request.client else ""

    if not req.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be empty.")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    token_hash = hashlib.sha256(req.token.encode()).hexdigest()

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM password_reset_tokens WHERE token_hash=%s AND used=0 AND expires_at > NOW()",
            (token_hash,)
        )
        token_record = cur.fetchone()

        if not token_record:
            cur.close()
            raise HTTPException(
                status_code=400,
                detail="Invalid, expired, or already-used reset token."
            )

        user_id = token_record["user_id"]
        cur.execute("SELECT id, username, email, role FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()

        if not user:
            cur.close()
            raise HTTPException(status_code=400, detail="Associated user account not found.")

        # Update user's password
        new_hash = get_password_hash(req.new_password)
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, user_id))

        # Invalidate the token
        cur.execute("UPDATE password_reset_tokens SET used=1 WHERE id=%s", (token_record["id"],))

        conn.commit()
        cur.close()

    write_audit_log(
        action="PASSWORD_RESET_SUCCESS",
        username=user["username"],
        role=user.get("role", ""),
        target_table="users",
        summary=f"Password successfully reset for user {user['username']}",
        success=True,
        ip_address=ip,
    )

    return {"message": "Password reset successfully. You can now log in with your new password."}

