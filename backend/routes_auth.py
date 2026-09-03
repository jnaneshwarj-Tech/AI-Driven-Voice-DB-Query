"""
routes_auth.py — Authentication routes including full OTP-based password reset.

OTP Reset Flow:
  1. POST /api/auth/forgot-password  → generate OTP, send email, return generic message
  2. POST /api/auth/verify-reset-otp → verify OTP, return short-lived reset_token
  3. POST /api/auth/reset-password   → verify reset_token, update password in MySQL

Security:
  - 6-digit cryptographically secure OTP (secrets module)
  - OTP stored as SHA-256 hash only (never plaintext)
  - 120-second expiry enforced on backend
  - Max 5 wrong attempts → OTP locked
  - 30-second resend cooldown
  - Max 5 OTP requests per email per hour
  - New OTP invalidates previous OTP
  - OTP single-use (marked used immediately on success)
  - reset_token stored as SHA-256 hash, 10-minute expiry, single-use
  - Password updated in transaction (rollback on failure)
  - Account enumeration protection (same response for known/unknown email)
  - No OTP or reset_token in logs
"""
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from auth import verify_password, create_access_token, get_password_hash, get_current_user
from database import db_conn, write_audit_log
from email_service import send_otp_email, EmailDeliveryError
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ── Pydantic models ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "Staff"

class ForgotPasswordRequest(BaseModel):
    username: str  # Now required
    email: EmailStr

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class ThemeRequest(BaseModel):
    theme: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    """Return hex SHA-256 digest of value."""
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_otp() -> str:
    """Return a cryptographically secure 6-digit OTP string."""
    return str(secrets.randbelow(900000) + 100000)


# ── Existing auth routes (unchanged) ──────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request = None):
    ip = request.client.host if request and request.client else ""

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s OR email=%s", (req.username, req.username))
        user = cur.fetchone()
        cur.close()

    if not user or not verify_password(req.password, user["password_hash"]):
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
    email_normalized = req.email.strip().lower()

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM users WHERE username=%s", (req.username,))
        if cur.fetchone():
            cur.close()
            raise HTTPException(400, "Username already registered")
        cur.execute("SELECT id FROM users WHERE LOWER(email)=%s", (email_normalized,))
        if cur.fetchone():
            cur.close()
            raise HTTPException(400, "An account with this email already exists.")
        role = "Staff" if req.role not in ["Admin", "Staff"] else req.role
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (req.username, email_normalized, get_password_hash(req.password), role)
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


# ── OTP Password Reset — Step 1: Request OTP ──────────────────────────────────

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request = None):
    """
    Step 1: User submits their username AND email.
    - Look up user by username
    - Verify the email matches the registered email for that username
    - Rate limit: max OTP_MAX_REQUESTS_PER_HOUR requests per email per hour
    - Resend cooldown: OTP_RESEND_COOLDOWN_SECONDS between requests
    - Generate cryptographically secure 6-digit OTP
    - Store SHA-256(OTP) in DB, mark previous OTPs invalid
    - Send OTP email (HTML + plain-text)
    - Return generic safe message (no OTP, no token, no email existence hint)
    
    SECURITY: Requires BOTH username and registered email to match before sending OTP.
    """
    ip = request.client.host if request and request.client else ""
    email_normalized = req.email.strip().lower()
    username_normalized = req.username.strip()

    # Generic message — account enumeration protection
    generic_msg = (
        "If the username and email match a registered account, "
        "a 6-digit OTP has been sent. Please check your inbox."
    )

    # ── User lookup by USERNAME ──────────────────────────────────────────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, username, email FROM users WHERE username=%s",
            (username_normalized,)
        )
        user = cur.fetchone()
        cur.close()

    # ── Verify username exists AND email matches ─────────────────────────────
    if not user:
        # Username doesn't exist - return generic message (don't reveal this)
        write_audit_log(
            action="PASSWORD_RESET_REQUESTED",
            username=username_normalized,
            role="",
            target_table="users",
            summary=f"Password reset requested for unknown username: {username_normalized}",
            success=False,
            ip_address=ip,
        )
        return {"message": generic_msg}
    
    if user["email"].lower() != email_normalized:
        # Username exists but email doesn't match - return generic message (don't reveal this)
        write_audit_log(
            action="PASSWORD_RESET_REQUESTED",
            username=user["username"],
            role="",
            target_table="users",
            summary=f"Password reset requested with mismatched email for user: {user['username']}",
            success=False,
            ip_address=ip,
        )
        return {"message": generic_msg}

    # ── Rate limiting ────────────────────────────────────────────────────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        one_hour_ago = datetime.now() - timedelta(hours=1)

        # Check total requests in last hour
        cur.execute(
            """SELECT COUNT(*) as cnt FROM password_reset_requests
               WHERE user_id=%s AND created_at >= %s""",
            (user["id"], one_hour_ago)
        )
        row = cur.fetchone()
        hourly_count = row["cnt"] if row else 0

        if hourly_count >= settings.OTP_MAX_REQUESTS_PER_HOUR:
            cur.close()
            logger.warning("[OTP] Rate limit hit for user_id=%s ip=%s", user["id"], ip)
            raise HTTPException(
                status_code=429,
                detail="Too many password reset requests. Please wait before trying again."
            )

        # Check resend cooldown (last request for this user)
        cooldown_cutoff = datetime.now() - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
        cur.execute(
            """SELECT created_at FROM password_reset_requests
               WHERE user_id=%s ORDER BY created_at DESC LIMIT 1""",
            (user["id"],)
        )
        last_req = cur.fetchone()
        cur.close()

    if last_req and last_req["created_at"] > cooldown_cutoff:
        remaining = (
            last_req["created_at"] + timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
            - datetime.now()
        )
        remaining_sec = max(1, int(remaining.total_seconds()))
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {remaining_sec} second(s) before requesting another OTP."
        )

    # ── Generate OTP ─────────────────────────────────────────────────────────
    raw_otp = _generate_otp()
    otp_hash = _sha256(raw_otp)
    now = datetime.now()
    expires_at = now + timedelta(seconds=settings.OTP_EXPIRY_SECONDS)

    # ── Invalidate all previous active OTPs for this user ────────────────────
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE password_reset_requests
               SET otp_used_at = NOW()
               WHERE user_id=%s AND otp_used_at IS NULL""",
            (user["id"],)
        )
        # Insert new OTP record
        cur.execute(
            """INSERT INTO password_reset_requests
               (user_id, otp_hash, otp_created_at, otp_expires_at, created_ip)
               VALUES (%s, %s, %s, %s, %s)""",
            (user["id"], otp_hash, now, expires_at, ip[:60])
        )
        conn.commit()
        cur.close()

    # ── Send email ───────────────────────────────────────────────────────────
    try:
        send_otp_email(
            to_email=user["email"],
            username=user["username"],
            otp=raw_otp,
        )
    except EmailDeliveryError as exc:
        logger.error("[OTP] Email delivery failed for user_id=%s: %s", user["id"], exc)
        write_audit_log(
            action="PASSWORD_RESET_REQUESTED",
            username=user["username"],
            role="",
            target_table="users",
            summary="OTP generated but email delivery failed",
            success=False,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to send the OTP right now. Please try again later."
        )

    write_audit_log(
        action="PASSWORD_RESET_REQUESTED",
        username=user["username"],
        role="",
        target_table="users",
        summary=f"OTP sent to registered email of user {user['username']}",
        success=True,
        ip_address=ip,
    )

    return {"message": generic_msg}


# ── OTP Password Reset — Step 2: Verify OTP ───────────────────────────────────

@router.post("/verify-reset-otp")
def verify_reset_otp(req: VerifyOtpRequest, request: Request = None):
    """
    Step 2: User submits the 6-digit OTP received by email.
    - Verify OTP hash matches stored hash
    - Check OTP not expired (backend is authoritative)
    - Check OTP not already used
    - Check attempt count <= OTP_MAX_ATTEMPTS
    - On success: mark OTP used, generate short-lived reset_token, return it
    - On failure: increment attempt_count, lock if exceeded
    """
    ip = request.client.host if request and request.client else ""
    email_normalized = req.email.strip().lower()
    otp_input = req.otp.strip()

    # Basic format check
    if not otp_input.isdigit() or len(otp_input) != 6:
        raise HTTPException(status_code=400, detail="Invalid OTP format. Please enter the 6-digit code.")

    # ── User lookup ──────────────────────────────────────────────────────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, username FROM users WHERE LOWER(email)=%s",
            (email_normalized,)
        )
        user = cur.fetchone()
        cur.close()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    # ── Find the latest active (non-used) OTP record for this user ───────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, otp_hash, otp_expires_at, otp_used_at, attempt_count
               FROM password_reset_requests
               WHERE user_id=%s AND otp_used_at IS NULL
               ORDER BY otp_created_at DESC
               LIMIT 1""",
            (user["id"],)
        )
        record = cur.fetchone()
        cur.close()

    if not record:
        raise HTTPException(status_code=400, detail="No active OTP found. Please request a new one.")

    record_id = record["id"]

    # ── Check attempt limit ──────────────────────────────────────────────────
    if record["attempt_count"] >= settings.OTP_MAX_ATTEMPTS:
        write_audit_log(
            action="OTP_VERIFY_BLOCKED",
            username=user["username"],
            role="",
            target_table="password_reset_requests",
            summary="OTP verification blocked: max attempts exceeded",
            success=False,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=400,
            detail="Too many incorrect attempts. Please request a new OTP."
        )

    # ── Check expiry (backend authoritative) ─────────────────────────────────
    if datetime.now() > record["otp_expires_at"]:
        write_audit_log(
            action="OTP_VERIFY_EXPIRED",
            username=user["username"],
            role="",
            target_table="password_reset_requests",
            summary="OTP verification failed: OTP expired",
            success=False,
            ip_address=ip,
        )
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new OTP.")

    # ── Verify OTP hash ──────────────────────────────────────────────────────
    submitted_hash = _sha256(otp_input)
    if submitted_hash != record["otp_hash"]:
        # Increment attempt count
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE password_reset_requests SET attempt_count = attempt_count + 1 WHERE id=%s",
                (record_id,)
            )
            conn.commit()
            cur.close()

        remaining = settings.OTP_MAX_ATTEMPTS - (record["attempt_count"] + 1)
        write_audit_log(
            action="OTP_VERIFY_FAILED",
            username=user["username"],
            role="",
            target_table="password_reset_requests",
            summary=f"Wrong OTP submitted. Remaining attempts: {remaining}",
            success=False,
            ip_address=ip,
        )

        if remaining <= 0:
            raise HTTPException(
                status_code=400,
                detail="Too many incorrect attempts. Please request a new OTP."
            )

        raise HTTPException(
            status_code=400,
            detail=f"Invalid OTP. {remaining} attempt(s) remaining."
        )

    # ── OTP correct — generate reset_token ───────────────────────────────────
    raw_reset_token = secrets.token_urlsafe(32)
    reset_token_hash = _sha256(raw_reset_token)
    reset_token_expires_at = datetime.now() + timedelta(minutes=settings.RESET_TOKEN_EXPIRY_MINUTES)

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE password_reset_requests
               SET otp_used_at = NOW(),
                   reset_token_hash = %s,
                   reset_token_expires_at = %s
               WHERE id=%s""",
            (reset_token_hash, reset_token_expires_at, record_id)
        )
        conn.commit()
        cur.close()

    write_audit_log(
        action="OTP_VERIFIED",
        username=user["username"],
        role="",
        target_table="password_reset_requests",
        summary=f"OTP verified successfully for user {user['username']}",
        success=True,
        ip_address=ip,
    )

    # Return the reset_token to frontend — this is safe (it's a temporary authorization token,
    # equivalent to a session, not the OTP itself; it's hashed in DB)
    return {
        "message": "OTP verified successfully.",
        "reset_token": raw_reset_token,
    }


# ── OTP Password Reset — Step 3: Reset Password ───────────────────────────────

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request = None):
    """
    Step 3: User submits new password with the reset_token from Step 2.
    - Verify reset_token hash is in DB, not used, not expired
    - Validate password requirements
    - Hash new password with bcrypt
    - Update users.password_hash in a transaction
    - Mark reset_token as used
    - Audit log
    """
    ip = request.client.host if request and request.client else ""

    # ── Frontend validation mirrored on backend ──────────────────────────────
    if not req.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be empty.")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    reset_token_hash = _sha256(req.reset_token)

    # ── Lookup reset token ───────────────────────────────────────────────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, user_id, reset_token_expires_at, reset_token_used_at
               FROM password_reset_requests
               WHERE reset_token_hash=%s""",
            (reset_token_hash,)
        )
        record = cur.fetchone()
        cur.close()

    if not record:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired password reset session. Please restart the reset process."
        )

    if record["reset_token_used_at"] is not None:
        raise HTTPException(
            status_code=400,
            detail="This reset session has already been used. Please request a new OTP."
        )

    if not record["reset_token_expires_at"] or datetime.now() > record["reset_token_expires_at"]:
        raise HTTPException(
            status_code=400,
            detail="Password reset session expired. Please request a new OTP."
        )

    user_id = record["user_id"]
    record_id = record["id"]

    # ── Look up the user ─────────────────────────────────────────────────────
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, role FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        cur.close()

    if not user:
        raise HTTPException(status_code=400, detail="User account not found.")

    # ── Transaction: update password + mark token used ───────────────────────
    new_hash = get_password_hash(req.new_password)
    try:
        with db_conn() as conn:
            conn.start_transaction()
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE id=%s",
                (new_hash, user_id)
            )
            cur.execute(
                "UPDATE password_reset_requests SET reset_token_used_at=NOW() WHERE id=%s",
                (record_id,)
            )
            conn.commit()
            cur.close()
    except Exception as exc:
        logger.error("[RESET] Transaction failed for user_id=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Password reset failed due to a server error. Please try again."
        )

    write_audit_log(
        action="PASSWORD_RESET_COMPLETED",
        username=user["username"],
        role=user.get("role", ""),
        target_table="users",
        summary=f"Password successfully reset for user {user['username']}",
        success=True,
        ip_address=ip,
    )

    return {"message": "Password reset successfully. You can now log in with your new password."}
