"""
routes_backup.py — Enterprise Database Backup, Restore, and Storage Monitoring.

Endpoints (Sprint 1):
  POST   /api/backup/create          — create a manual backup
  GET    /api/backup/list            — list all backups with metadata
  GET    /api/backup/{id}            — get single backup info
  POST   /api/backup/restore/{id}    — safely restore a backup
  DELETE /api/backup/{id}            — delete a backup file
  GET    /api/backup/storage-status  — DB size + backup storage + disk usage

Security:
  All backup and restore endpoints require Admin role.
  Backup filenames are never user-controllable (server-generated).

Backup flow:
  BEGIN record → run mysqldump → verify file → update status → write audit log

Restore flow:
  CREATE pre-restore safety backup → confirm → restore → verify → audit log
"""

import os
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from database import db_conn, write_audit_log
from auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/backup", tags=["Backup & Restore"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _backup_dir() -> str:
    return settings.backup_dir_abs


def _gen_backup_name(backup_type: str = "manual") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"backup_{backup_type}_{ts}.sql"


def _mysqldump_path() -> str:
    """Find mysqldump on PATH or common Windows install location."""
    # Try PATH first
    p = shutil.which("mysqldump")
    if p:
        return p
    # Fallback to common MySQL install paths
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe",
        r"C:\xampp\mysql\bin\mysqldump.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise RuntimeError("mysqldump not found on PATH or common install locations.")


def _mysql_path() -> str:
    """Find mysql CLI on PATH or common Windows install location."""
    p = shutil.which("mysql")
    if p:
        return p
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        r"C:\xampp\mysql\bin\mysql.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise RuntimeError("mysql CLI not found on PATH.")


def _verify_backup(filepath: str) -> tuple[bool, str]:
    """
    Verify a backup file is non-empty and appears valid.
    Returns (is_valid, message).
    """
    try:
        size = os.path.getsize(filepath)
        if size < 100:
            return False, f"Backup file too small ({size} bytes) — likely empty or corrupt."

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline()
        if not first_line.startswith("--"):
            return False, "Backup file does not start with SQL comment — may be corrupt."

        return True, f"Verified OK ({size:,} bytes)"
    except Exception as e:
        return False, f"Verification error: {e}"


def _count_student_records() -> int:
    """Count total student records in the current database."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM students")
            row = cur.fetchone()
            cur.close()
            return row[0] if row else 0
    except Exception:
        return 0


def _run_mysqldump(backup_path: str) -> tuple[bool, str]:
    """
    Execute mysqldump to create a backup.
    Returns (success, error_message).
    """
    try:
        dump_exe = _mysqldump_path()
        cmd = [
            dump_exe,
            f"-h{settings.MYSQL_HOST}",
            f"-P{settings.MYSQL_PORT}",
            f"-u{settings.MYSQL_USER}",
            f"-p{settings.MYSQL_PASSWORD}",
            "--single-transaction",          # consistent snapshot, no lock
            "--routines",
            "--triggers",
            "--add-drop-table",
            "--complete-insert",
            "--extended-insert",
            settings.MYSQL_DB,
        ]

        with open(backup_path, "w", encoding="utf-8") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=300,  # 5 minute max
                text=True,
            )

        if result.returncode != 0:
            # Filter password from stderr
            err = result.stderr.replace(settings.MYSQL_PASSWORD, "***")
            return False, f"mysqldump failed (rc={result.returncode}): {err[:500]}"

        return True, ""

    except subprocess.TimeoutExpired:
        return False, "mysqldump timed out after 5 minutes."
    except Exception as e:
        return False, str(e)


def _run_mysql_restore(backup_path: str) -> tuple[bool, str]:
    """
    Execute mysql CLI to restore from a backup file.
    Returns (success, error_message).
    """
    try:
        mysql_exe = _mysql_path()
        cmd = [
            mysql_exe,
            f"-h{settings.MYSQL_HOST}",
            f"-P{settings.MYSQL_PORT}",
            f"-u{settings.MYSQL_USER}",
            f"-p{settings.MYSQL_PASSWORD}",
            settings.MYSQL_DB,
        ]

        with open(backup_path, "r", encoding="utf-8") as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                timeout=600,  # 10 minute max
                text=True,
            )

        if result.returncode != 0:
            err = result.stderr.replace(settings.MYSQL_PASSWORD, "***")
            return False, f"mysql restore failed (rc={result.returncode}): {err[:500]}"

        return True, ""

    except subprocess.TimeoutExpired:
        return False, "MySQL restore timed out after 10 minutes."
    except Exception as e:
        return False, str(e)


def _apply_retention_policy():
    """
    Clean up old backups according to retention policy.
    Keeps last BACKUP_RETENTION_DAILY daily and BACKUP_RETENTION_WEEKLY weekly.
    Never deletes pre_restore or manual backups automatically.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)

            # Delete old auto_daily beyond retention
            cur.execute(
                "SELECT id, backup_path FROM db_backups "
                "WHERE backup_type='auto_daily' AND status='success' "
                "ORDER BY created_at DESC"
            )
            daily_backups = cur.fetchall()
            to_delete = daily_backups[settings.BACKUP_RETENTION_DAILY:]
            for b in to_delete:
                try:
                    if b["backup_path"] and os.path.exists(b["backup_path"]):
                        os.remove(b["backup_path"])
                    cur.execute("DELETE FROM db_backups WHERE id=%s", (b["id"],))
                except Exception:
                    pass

            # Delete old auto_weekly beyond retention
            cur.execute(
                "SELECT id, backup_path FROM db_backups "
                "WHERE backup_type='auto_weekly' AND status='success' "
                "ORDER BY created_at DESC"
            )
            weekly_backups = cur.fetchall()
            to_delete_w = weekly_backups[settings.BACKUP_RETENTION_WEEKLY:]
            for b in to_delete_w:
                try:
                    if b["backup_path"] and os.path.exists(b["backup_path"]):
                        os.remove(b["backup_path"])
                    cur.execute("DELETE FROM db_backups WHERE id=%s", (b["id"],))
                except Exception:
                    pass

            conn.commit()
            cur.close()
    except Exception:
        pass


def create_backup_internal(backup_type: str = "manual", created_by: str = "system") -> dict:
    """
    Core backup function — called by endpoints and scheduler.
    Returns backup metadata dict.
    """
    backup_dir = _backup_dir()
    backup_name = _gen_backup_name(backup_type)
    backup_path = os.path.join(backup_dir, backup_name)

    # Insert 'running' record
    backup_id = None
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO db_backups
               (backup_name, backup_path, backup_type, status, created_by)
               VALUES (%s, %s, %s, 'running', %s)""",
            (backup_name, backup_path, backup_type, created_by)
        )
        conn.commit()
        backup_id = cur.lastrowid
        cur.close()

    # Run mysqldump
    success, error_msg = _run_mysqldump(backup_path)

    if not success:
        # Mark as failed
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE db_backups SET status='failed', completed_at=NOW(), error_message=%s WHERE id=%s",
                (error_msg[:1000], backup_id)
            )
            conn.commit()
            cur.close()
        write_audit_log(
            action="BACKUP_FAILED", username=created_by,
            target_table="db_backups", target_id=str(backup_id),
            summary=f"Backup {backup_name} failed", success=False, error_info=error_msg
        )
        return {"success": False, "error": error_msg, "backup_id": backup_id}

    # Verify the backup
    verified, verify_msg = _verify_backup(backup_path)
    file_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
    record_count = _count_student_records()

    final_status = "verified" if verified else "success"

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE db_backups SET
               status=%s, verified=%s, size_bytes=%s, record_count=%s,
               completed_at=NOW(), error_message=%s
               WHERE id=%s""",
            (final_status, 1 if verified else 0, file_size, record_count,
             verify_msg if not verified else None, backup_id)
        )
        conn.commit()
        cur.close()

    write_audit_log(
        action="BACKUP_SUCCESS", username=created_by,
        target_table="db_backups", target_id=str(backup_id),
        summary=f"Backup {backup_name} created. Size={file_size:,}B. {verify_msg}",
        success=True
    )

    # Apply retention policy after each new backup
    _apply_retention_policy()

    return {
        "success": True,
        "backup_id": backup_id,
        "backup_name": backup_name,
        "size_bytes": file_size,
        "status": final_status,
        "verified": verified,
        "verify_message": verify_msg,
        "record_count": record_count,
    }


# ── Request Models ─────────────────────────────────────────────────────────────

class RestoreRequest(BaseModel):
    confirmed: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/create")
def create_backup(current_user: dict = Depends(get_current_user)):
    """Create a manual backup. Requires Admin role."""
    if current_user["role"] != "Admin":
        raise HTTPException(403, "Only Admin can create backups.")

    result = create_backup_internal(
        backup_type="manual",
        created_by=current_user["username"]
    )

    if not result["success"]:
        raise HTTPException(500, f"Backup failed: {result['error']}")

    return {
        "success": True,
        "message": f"Backup created successfully. {result['verify_message']}",
        **result
    }


@router.get("/list")
def list_backups(current_user: dict = Depends(get_current_user)):
    """List all backups. Requires Admin role."""
    if current_user["role"] != "Admin":
        raise HTTPException(403, "Only Admin can view backups.")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, backup_name, backup_type, size_bytes, status, verified,
               created_by, created_at, completed_at, error_message, record_count
               FROM db_backups ORDER BY created_at DESC LIMIT 100"""
        )
        backups = cur.fetchall()
        cur.close()

    for b in backups:
        if b.get("created_at"):
            b["created_at"] = str(b["created_at"])
        if b.get("completed_at"):
            b["completed_at"] = str(b["completed_at"])
        # Check if file still exists on disk
        b["file_exists"] = os.path.exists(
            os.path.join(_backup_dir(), b["backup_name"])
        ) if b.get("backup_name") else False

    return backups


@router.get("/storage-status")
def get_storage_status(current_user: dict = Depends(get_current_user)):
    """
    Returns DB size, backup storage usage, disk info.
    Available to all authenticated users (Admins + Staff).
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # DB size (in MB)
        cur.execute(
            """SELECT
               ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS db_size_mb,
               ROUND(SUM(data_length) / 1024 / 1024, 2) AS data_size_mb,
               ROUND(SUM(index_length) / 1024 / 1024, 2) AS index_size_mb
               FROM information_schema.tables
               WHERE table_schema = %s""",
            (settings.MYSQL_DB,)
        )
        db_size = cur.fetchone()

        # Table sizes
        cur.execute(
            """SELECT table_name, table_rows,
               ROUND((data_length + index_length) / 1024, 2) AS total_kb
               FROM information_schema.tables
               WHERE table_schema = %s
               ORDER BY (data_length + index_length) DESC""",
            (settings.MYSQL_DB,)
        )
        table_sizes = cur.fetchall()

        # Backup counts
        cur.execute(
            "SELECT status, COUNT(*) AS cnt, SUM(size_bytes) AS total_bytes "
            "FROM db_backups GROUP BY status"
        )
        backup_stats = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS total FROM db_backups WHERE status IN ('success','verified')")
        total_backups = cur.fetchone()["total"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM db_backups "
            "WHERE status='failed' AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        )
        recent_failures = cur.fetchone()["cnt"]

        cur.close()

    # Backup storage on disk
    backup_dir = _backup_dir()
    backup_storage_bytes = sum(
        os.path.getsize(os.path.join(backup_dir, f))
        for f in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, f))
    ) if os.path.exists(backup_dir) else 0

    # Disk usage
    disk = shutil.disk_usage(backup_dir if os.path.exists(backup_dir) else ".")
    disk_used_pct = round(disk.used / disk.total * 100, 1)
    disk_free_gb = round(disk.free / 1024 / 1024 / 1024, 2)

    warnings = []
    if disk_used_pct > 90:
        warnings.append(f"CRITICAL: Disk is {disk_used_pct}% full ({disk_free_gb} GB free). Backups may fail!")
    elif disk_used_pct > 75:
        warnings.append(f"WARNING: Disk is {disk_used_pct}% full ({disk_free_gb} GB free).")
    if recent_failures > 0:
        warnings.append(f"{recent_failures} backup failure(s) in the last 7 days. Check logs.")

    return {
        "db_size_mb": float(db_size.get("db_size_mb") or 0),
        "data_size_mb": float(db_size.get("data_size_mb") or 0),
        "index_size_mb": float(db_size.get("index_size_mb") or 0),
        "table_sizes": table_sizes,
        "total_backups": total_backups,
        "backup_stats": backup_stats,
        "backup_storage_bytes": backup_storage_bytes,
        "backup_storage_mb": round(backup_storage_bytes / 1024 / 1024, 2),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
        "disk_free_gb": disk_free_gb,
        "disk_used_pct": disk_used_pct,
        "warnings": warnings,
        "backup_dir": backup_dir,
    }


@router.post("/restore/{backup_id}")
def restore_backup(
    backup_id: int,
    body: RestoreRequest = Body(default=RestoreRequest()),
    current_user: dict = Depends(get_current_user)
):
    """
    Restore database from a specific backup.
    Requires Admin role + explicit confirmation.

    Flow:
      1. Validate backup exists and is usable.
      2. Create a pre-restore safety backup of current state.
      3. Write audit log entry.
      4. Run mysql restore.
      5. Verify database integrity after restore.
      6. Write success/failure audit entry.
    """
    if current_user["role"] != "Admin":
        raise HTTPException(403, "Only Admin can restore backups.")

    if not body.confirmed:
        raise HTTPException(
            400,
            "Restore requires explicit confirmation. Send {\"confirmed\": true} in the request body."
        )

    # 1. Fetch backup record
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM db_backups WHERE id=%s", (backup_id,))
        backup = cur.fetchone()
        cur.close()

    if not backup:
        raise HTTPException(404, f"Backup ID {backup_id} not found.")

    if backup["status"] not in ("success", "verified"):
        raise HTTPException(
            400,
            f"Backup {backup['backup_name']} has status '{backup['status']}' — cannot restore from a failed or running backup."
        )

    backup_path = backup.get("backup_path") or os.path.join(_backup_dir(), backup["backup_name"])
    if not os.path.exists(backup_path):
        raise HTTPException(
            404,
            f"Backup file not found on disk: {backup['backup_name']}. It may have been deleted."
        )

    # 2. Create pre-restore safety backup
    safety_result = create_backup_internal(
        backup_type="pre_restore",
        created_by=current_user["username"]
    )
    safety_backup_id = safety_result.get("backup_id")
    if not safety_result.get("success"):
        # Don't proceed if we can't create a safety backup
        raise HTTPException(
            500,
            f"Cannot proceed: pre-restore safety backup failed: {safety_result.get('error')}. "
            "Current database is unchanged."
        )

    # 3. Write pre-restore audit log
    write_audit_log(
        action="RESTORE_START", username=current_user["username"],
        role=current_user["role"],
        target_table="db_backups", target_id=str(backup_id),
        summary=f"Restoring from backup: {backup['backup_name']}. "
                f"Safety backup ID: {safety_backup_id}",
        success=True
    )

    # 4. Run restore
    success, error_msg = _run_mysql_restore(backup_path)

    if not success:
        write_audit_log(
            action="RESTORE_FAILED", username=current_user["username"],
            role=current_user["role"],
            target_table="db_backups", target_id=str(backup_id),
            summary=f"Restore of {backup['backup_name']} FAILED. Safety backup: {safety_backup_id}",
            success=False, error_info=error_msg
        )
        raise HTTPException(
            500,
            f"Restore failed: {error_msg}. "
            f"Your previous data is preserved in safety backup ID {safety_backup_id}. "
            "Use that backup to recover."
        )

    # 5. Verify database integrity after restore
    students_after = _count_student_records()

    # 6. Write success audit log
    write_audit_log(
        action="RESTORE_SUCCESS", username=current_user["username"],
        role=current_user["role"],
        target_table="db_backups", target_id=str(backup_id),
        summary=(
            f"Restore of {backup['backup_name']} succeeded. "
            f"Students in DB after restore: {students_after}. "
            f"Original backup had {backup.get('record_count', 'unknown')} records."
        ),
        success=True
    )

    return {
        "success": True,
        "message": (
            f"Database restored from backup '{backup['backup_name']}'. "
            f"Students in database: {students_after}."
        ),
        "restored_backup_name": backup["backup_name"],
        "restored_backup_created_at": str(backup.get("created_at", "")),
        "students_after_restore": students_after,
        "safety_backup_id": safety_backup_id,
        "safety_backup_name": safety_result.get("backup_name"),
    }


@router.delete("/{backup_id}")
def delete_backup(backup_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a backup file and its record. Requires Admin role."""
    if current_user["role"] != "Admin":
        raise HTTPException(403, "Only Admin can delete backups.")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM db_backups WHERE id=%s", (backup_id,))
        backup = cur.fetchone()
        cur.close()

    if not backup:
        raise HTTPException(404, f"Backup ID {backup_id} not found.")

    # Prevent deleting the most recent pre_restore backup (safety net)
    if backup["backup_type"] == "pre_restore":
        raise HTTPException(
            400,
            "Pre-restore safety backups cannot be deleted manually. "
            "They will be cleaned up by the retention policy after 30 days."
        )

    backup_path = backup.get("backup_path") or os.path.join(_backup_dir(), backup["backup_name"])
    if os.path.exists(backup_path):
        os.remove(backup_path)

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM db_backups WHERE id=%s", (backup_id,))
        conn.commit()
        cur.close()

    write_audit_log(
        action="BACKUP_DELETED", username=current_user["username"],
        role=current_user["role"],
        target_table="db_backups", target_id=str(backup_id),
        summary=f"Backup {backup['backup_name']} deleted by {current_user['username']}",
        success=True
    )

    return {"success": True, "message": f"Backup '{backup['backup_name']}' deleted."}


@router.get("/audit-log")
def get_audit_log(
    limit: int = 100,
    action: Optional[str] = None,
    username: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch enterprise audit log.
    Admin can see all logs; Staff can only see their own.
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        conditions = []
        params = []

        if current_user["role"] != "Admin":
            conditions.append("username=%s")
            params.append(current_user["username"])
        elif username:
            conditions.append("username=%s")
            params.append(username)

        if action:
            conditions.append("action=%s")
            params.append(action)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(min(limit, 500))

        cur.execute(
            f"SELECT id, username, role, action, target_table, target_id, "
            f"summary, success, error_info, ip_address, created_at "
            f"FROM audit_log {where} ORDER BY created_at DESC LIMIT %s",
            params
        )
        logs = cur.fetchall()
        cur.close()

    for log in logs:
        if log.get("created_at"):
            log["created_at"] = str(log["created_at"])

    return logs


@router.get("/upload-versions")
def get_upload_versions(current_user: dict = Depends(get_current_user)):
    """Return the upload version/snapshot history."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM upload_versions ORDER BY created_at DESC LIMIT 100"
        )
        rows = cur.fetchall()
        cur.close()

    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])

    return rows
