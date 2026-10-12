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
import re
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from database import db_conn, write_audit_log
from auth import get_current_user, require_roles
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


def _row_path(backup: dict) -> str:
    """Where a backup row says its file is — resolved one way, everywhere.

    The list used to look in the backup directory by name while the restore and
    delete doors used `backup_path` first, so the two could disagree about
    whether a dump exists.
    """
    name = backup.get("backup_name") or ""
    return backup.get("backup_path") or (os.path.join(_backup_dir(), name) if name else "")


# A dump that cannot restore these is not a dump of this application.
_CORE_TABLES = ("students", "marks")


def _dump_problem(filepath: str) -> str | None:
    """Return why this file must not be piped into the running database, or None.

    `mysql < file` has no idea what it is being handed: a wrong file from this
    folder, a log dump, or a dump of some other schema would be applied to the
    college's live database and only discovered afterwards. Reading what the file
    says about itself is cheap by comparison.

    The one usable clue mysqldump leaves is its own header comment
    (`-- Host: localhost    Database: student_db`) plus the
    `-- Current Database: `x`` markers a `--databases` dump writes. This folder
    really does mix schemas — it holds both production and staging dumps — so a
    dump declared for another schema is refused rather than applied here.
    """
    banner = False
    tables: set = set()
    used: list = []
    declared: list = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh):
                if i == 0:
                    banner = line.startswith("--") and "dump" in line.lower()
                if not declared:
                    m = re.search(r"--\s*(?:Host:.*?|Current\s)?Database:\s*`?([^`\s]+)`?",
                                  line)
                    if m:
                        declared.append(m.group(1))
                if line.startswith("USE ") or line.startswith("use "):
                    m = re.search(r"[`\"]?([A-Za-z0-9_$]+)[`\"]?;?\s*$", line)
                    if m:
                        used.append(m.group(1))
                for m in re.finditer(r"(?:CREATE TABLE|INSERT INTO)\s+`([^`]+)`", line):
                    tables.add(m.group(1))
                if i > 200000:      # 10 MB dumps; the header is enough
                    break
    except Exception as e:
        return f"the backup file could not be read ({e})."

    if not banner:
        return ("the file does not start with a mysqldump header, so it is not a "
                "database dump this tool can trust.")
    wrong = [s for s in declared if s != settings.MYSQL_DB]
    if wrong:
        return (f"the dump says it was taken from database '{wrong[0]}', but this app "
                f"runs on '{settings.MYSQL_DB}'. Restore it only from a server started "
                f"with MYSQL_DB={wrong[0]}, or select a dump whose header names "
                f"'{settings.MYSQL_DB}'.")
    other = [s for s in used if s != settings.MYSQL_DB]
    if other:
        return (f"the dump says it was taken from database '{other[0]}', but this app "
                f"runs on '{settings.MYSQL_DB}'.")
    if not any(t in tables for t in _CORE_TABLES):
        seen = ", ".join(sorted(tables)[:5]) or "no tables"
        return (f"the dump holds none of this application's core tables "
                f"(found: {seen}).")
    return None


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


def _cli_env() -> dict:
    """Environment for mysqldump/mysql, carrying the password off the command line.

    A `-p<secret>` argument is readable by anybody who can list processes on this
    host (task manager, `wmic process`, a shared CI agent), and the college's
    database login is the same one the app uses. MYSQL_PWD is the documented
    channel that keeps it out of the process table.
    """
    return dict(os.environ, MYSQL_PWD=settings.MYSQL_PASSWORD)


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
            "--single-transaction",          # consistent snapshot, no lock
            "--routines",
            "--triggers",
            "--add-drop-table",
            "--complete-insert",
            "--extended-insert",
            # The backup register and the audit trail describe the operations
            # around this database; they are not the college's records. Dumping
            # them means a restore rewinds them: the pre-restore safety dump
            # taken to protect a restore had its own register row erased by that
            # restore (the file stayed on disk, unnamed and unprunable), and every
            # audit entry written between the dump and the restore was destroyed —
            # including the RESTORE_START entry for the restore itself.
            # The backup register and the audit trail describe the operations
            # around this database; they are not the college's records. Dumping
            # them means a restore rewinds them: the pre-restore safety dump
            # taken to protect a restore had its own register row erased by that
            # restore (the file stayed on disk, unnamed and unprunable), and every
            # audit entry written between the dump and the restore was destroyed —
            # including the RESTORE_START entry for the restore itself.
            f"--ignore-table={settings.MYSQL_DB}.db_backups",
            f"--ignore-table={settings.MYSQL_DB}.audit_log",
            settings.MYSQL_DB,
        ]

        with open(backup_path, "w", encoding="utf-8") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=300,  # 5 minute max
                text=True,
                env=_cli_env(),
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
                env=_cli_env(),
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
def create_backup(current_user: dict = Depends(require_roles("Admin"))):
    """Create a manual backup. Requires Admin role."""
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
def list_backups(current_user: dict = Depends(require_roles("Admin"))):
    """List all backups. Requires Admin role."""
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id, backup_name, backup_path, backup_type, size_bytes, status, verified,
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
        # Check if file still exists on disk — at the path the row records.
        path = _row_path(b)
        b["file_exists"] = bool(path) and os.path.exists(path)
        b.pop("backup_path", None)

    return backups


@router.get("/storage-status")
def get_storage_status(current_user: dict = Depends(require_roles("Admin", "Staff"))):
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

    # Backup storage on disk, reconciled against the register. A dump no row
    # points at cannot be restored from the UI and is never pruned; a row whose
    # file is gone offers a restore button that will fail. Both have to be named
    # for the database owner to act on them.
    backup_dir = _backup_dir()
    on_disk = {}
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            fp = os.path.join(backup_dir, f)
            if os.path.isfile(fp):
                on_disk[os.path.normpath(fp)] = os.path.getsize(fp)
    backup_storage_bytes = sum(on_disk.values())

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT backup_name, backup_path, status FROM db_backups")
        registered = cur.fetchall()
        cur.close()
    referenced = set()
    missing_files = []
    for row in registered:
        path = os.path.normpath(_row_path(row))
        referenced.add(path)
        if path not in on_disk and row["status"] in ("success", "verified"):
            missing_files.append(os.path.basename(path))

    orphan_files = []
    orphan_bytes = 0
    for path, size in on_disk.items():
        if path in referenced or not path.lower().endswith(".sql"):
            continue
        orphan_files.append((path, size))
        orphan_bytes += size
    orphan_files.sort(key=lambda item: -os.path.getmtime(item[0]))

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
    if orphan_files:
        warnings.append(
            f"{len(orphan_files)} dump file(s) in {backup_dir} ({round(orphan_bytes/1024/1024, 2)} MB) "
            "are not in the backup register: they cannot be restored from this screen and the "
            "retention policy will never remove them. Ask the database owner before deleting.")
    if missing_files:
        warnings.append(
            f"{len(missing_files)} registered backup(s) have no file on disk. Their restore "
            "buttons will fail.")

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
        "orphan_dump_count": len(orphan_files),
        "orphan_dump_mb": round(orphan_bytes / 1024 / 1024, 2),
        "orphan_dumps": [
            {"file": os.path.basename(path), "size_mb": round(size / 1024 / 1024, 2),
             "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()}
            for path, size in orphan_files[:25]
        ],
        "missing_file_count": len(missing_files),
        "missing_files": missing_files[:25],
    }


@router.post("/restore/{backup_id}")
def restore_backup(
    backup_id: int,
    body: RestoreRequest = Body(default=RestoreRequest()),
    current_user: dict = Depends(require_roles("Admin"))
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

    backup_path = _row_path(backup)
    if not os.path.exists(backup_path):
        raise HTTPException(
            404,
            f"Backup file not found on disk: {backup['backup_name']}. It may have been deleted."
        )

    # 1b. Read what the file says it is before anything is overwritten, and
    # before the safety dump is written — a refused attempt must cost nothing.
    problem = _dump_problem(backup_path)
    if problem:
        write_audit_log(
            action="RESTORE_REFUSED", username=current_user["username"],
            role=current_user["role"],
            target_table="db_backups", target_id=str(backup_id),
            summary=(f"Restore of {backup['backup_name']} refused before touching the "
                     f"database: {problem} No changes were made."),
            success=False, error_info=problem
        )
        raise HTTPException(400, f"Restore refused: {problem} Nothing was changed.")

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
            f"Database '{settings.MYSQL_DB}' restored from backup "
            f"'{backup['backup_name']}'. Students in database: {students_after}."
        ),
        "restored_backup_name": backup["backup_name"],
        "restored_backup_created_at": str(backup.get("created_at", "")),
        "target_database": settings.MYSQL_DB,
        "students_after_restore": students_after,
        "safety_backup_id": safety_backup_id,
        "safety_backup_name": safety_result.get("backup_name"),
    }


@router.delete("/{backup_id}")
def delete_backup(backup_id: int, current_user: dict = Depends(require_roles("Admin"))):
    """Delete a backup file and its record. Requires Admin role."""
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
            "Pre-restore safety backups are kept: the retention policy prunes only "
            "automatic daily/weekly dumps, so nothing deletes this one automatically. "
            "Ask the database owner before removing it, and check the disk usage under "
            "Storage status."
        )

    backup_path = _row_path(backup)
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
    current_user: dict = Depends(require_roles("Admin", "Staff"))
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
def get_upload_versions(current_user: dict = Depends(require_roles("Admin", "Staff"))):
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
