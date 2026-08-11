"""
routes_monitor.py — Database performance and health monitoring endpoints.

Endpoints (Sprint 1):
  GET /api/monitor/health       — DB connection, version, pool status
  GET /api/monitor/db-stats     — table sizes, index info, row counts
  GET /api/monitor/performance  — slow queries, execution times, recent errors
"""

import time
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from database import db_conn
from auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/monitor", tags=["Database Monitoring"])


@router.get("/health")
def db_health(current_user: dict = Depends(get_current_user)):
    """Database connectivity and server health check."""
    start = time.perf_counter()
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)

            # Server version and uptime
            cur.execute("SELECT VERSION() AS version")
            version = cur.fetchone()["version"]

            cur.execute("SHOW STATUS LIKE 'Uptime'")
            uptime_row = cur.fetchone()
            uptime_sec = int(uptime_row["Value"]) if uptime_row else 0

            cur.execute("SHOW STATUS LIKE 'Threads_connected'")
            threads = cur.fetchone()
            threads_connected = int(threads["Value"]) if threads else 0

            cur.execute("SHOW STATUS LIKE 'Max_used_connections'")
            max_conn_row = cur.fetchone()
            max_connections = int(max_conn_row["Value"]) if max_conn_row else 0

            cur.execute("SHOW STATUS LIKE 'Innodb_buffer_pool_reads'")
            buf_reads = cur.fetchone()

            cur.execute("SHOW STATUS LIKE 'Questions'")
            questions = cur.fetchone()
            total_queries = int(questions["Value"]) if questions else 0

            cur.close()

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        uptime_h = round(uptime_sec / 3600, 1)

        return {
            "status": "healthy",
            "db_version": version,
            "db_host": settings.MYSQL_HOST,
            "db_name": settings.MYSQL_DB,
            "uptime_hours": uptime_h,
            "threads_connected": threads_connected,
            "max_used_connections": max_connections,
            "total_queries_lifetime": total_queries,
            "connection_test_ms": elapsed_ms,
            "pool_size": 20,
            "checked_at": datetime.now().isoformat(),
        }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "unhealthy",
            "error": str(e),
            "connection_test_ms": elapsed_ms,
            "checked_at": datetime.now().isoformat(),
        }


@router.get("/db-stats")
def db_stats(current_user: dict = Depends(get_current_user)):
    """
    Detailed database statistics:
    - Table row counts and sizes
    - Index usage info
    - Storage overview
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Table sizes with row counts
        cur.execute(
            """SELECT
               table_name,
               table_rows AS estimated_rows,
               ROUND(data_length / 1024, 1) AS data_kb,
               ROUND(index_length / 1024, 1) AS index_kb,
               ROUND((data_length + index_length) / 1024, 1) AS total_kb
               FROM information_schema.tables
               WHERE table_schema = %s
               ORDER BY (data_length + index_length) DESC""",
            (settings.MYSQL_DB,)
        )
        table_stats = cur.fetchall()

        # Actual precise row counts for key tables
        precise_counts = {}
        for tbl in ["students", "marks", "uploaded_files", "audit_log",
                    "global_undo_snapshots", "upload_versions", "db_backups"]:
            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{tbl}`")
                row = cur.fetchone()
                precise_counts[tbl] = row["cnt"] if row else 0
            except Exception:
                precise_counts[tbl] = -1

        # Index information
        cur.execute(
            """SELECT table_name, index_name, column_name, non_unique
               FROM information_schema.statistics
               WHERE table_schema = %s
               ORDER BY table_name, index_name""",
            (settings.MYSQL_DB,)
        )
        indexes = cur.fetchall()

        # Total DB size
        cur.execute(
            """SELECT
               ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS total_mb
               FROM information_schema.tables
               WHERE table_schema = %s""",
            (settings.MYSQL_DB,)
        )
        total = cur.fetchone()

        cur.close()

    return {
        "database": settings.MYSQL_DB,
        "total_size_mb": float(total["total_mb"] or 0),
        "table_stats": table_stats,
        "precise_counts": precise_counts,
        "indexes": indexes,
        "checked_at": datetime.now().isoformat(),
    }


@router.get("/performance")
def get_performance(current_user: dict = Depends(get_current_user)):
    """
    Query performance insights:
    - Recent query history with execution times
    - Slow queries (above threshold)
    - Average execution time per role
    - Upload processing stats
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Recent queries with timing
        cur.execute(
            """SELECT user_role, natural_query, execution_time, timestamp
               FROM query_history
               ORDER BY timestamp DESC LIMIT 50"""
        )
        recent_queries = cur.fetchall()
        for r in recent_queries:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])

        # Slow queries (above 1 second)
        cur.execute(
            """SELECT user_role, natural_query, execution_time, timestamp
               FROM query_history
               WHERE execution_time > 1.0
               ORDER BY execution_time DESC LIMIT 20"""
        )
        slow_queries = cur.fetchall()
        for r in slow_queries:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])

        # Average execution time per role
        cur.execute(
            """SELECT user_role,
               COUNT(*) AS query_count,
               ROUND(AVG(execution_time), 4) AS avg_time_sec,
               ROUND(MAX(execution_time), 4) AS max_time_sec,
               ROUND(MIN(execution_time), 4) AS min_time_sec
               FROM query_history
               GROUP BY user_role"""
        )
        avg_by_role = cur.fetchall()

        # Upload processing history
        cur.execute(
            """SELECT filename, rows_parsed, students_added, students_updated,
               marks_added, skipped_rows, status, performed_by, created_at
               FROM upload_versions
               ORDER BY created_at DESC LIMIT 20"""
        )
        upload_stats = cur.fetchall()
        for r in upload_stats:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])

        # Audit log summary (last 24h)
        cur.execute(
            """SELECT action, success, COUNT(*) AS cnt
               FROM audit_log
               WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
               GROUP BY action, success
               ORDER BY cnt DESC"""
        )
        audit_summary = cur.fetchall()

        # Backup performance
        cur.execute(
            """SELECT backup_type, status,
               COUNT(*) AS cnt,
               ROUND(AVG(size_bytes) / 1024 / 1024, 2) AS avg_size_mb
               FROM db_backups
               GROUP BY backup_type, status"""
        )
        backup_perf = cur.fetchall()

        cur.close()

    slow_threshold = 1.0
    total_slow = len(slow_queries)
    total_queries = len(recent_queries)
    slow_pct = round(total_slow / max(total_queries, 1) * 100, 1)

    return {
        "recent_queries": recent_queries,
        "slow_queries": slow_queries,
        "slow_query_threshold_sec": slow_threshold,
        "slow_query_count": total_slow,
        "slow_query_pct": slow_pct,
        "avg_by_role": avg_by_role,
        "upload_stats": upload_stats,
        "audit_summary_24h": audit_summary,
        "backup_performance": backup_perf,
        "generated_at": datetime.now().isoformat(),
        "warnings": (
            [f"{slow_pct}% of recent queries are slow (>1s). Consider index optimization."]
            if slow_pct > 20 else []
        ),
    }
