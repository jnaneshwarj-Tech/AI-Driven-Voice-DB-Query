"""Phase 1.2 / 9.9 probe: prove the newest manual backup restores into a SEPARATE
schema and that its contents match the live database. Never touches student_db."""
import os
import subprocess
import sys

from config import settings

CLIENT = r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.EXE"
SRC = settings.MYSQL_DB
DST = "student_db_backupcheck"
BACKUP = sys.argv[1]

env = dict(os.environ, MYSQL_PWD=settings.MYSQL_PASSWORD)
COMMON = [CLIENT, "-h", settings.MYSQL_HOST, "-P", str(settings.MYSQL_PORT),
          "-u", settings.MYSQL_USER]


def run(sql, db=None):
    cmd = COMMON + (["-D", db] if db else []) + ["-N", "-B", "-e", sql]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.replace(settings.MYSQL_PASSWORD, "***")[:300])
    return r.stdout.strip()


# Refuse to proceed if anything could target the live database.
existing_tables = run(
    f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{DST}'")
if DST == SRC or existing_tables != "0":
    raise SystemExit(f"refusing to restore: {DST} is not empty/absent ({existing_tables} tables)")
run(f"CREATE DATABASE {DST} CHARACTER SET utf8mb4")
print("created", DST)

with open(BACKUP, "r", encoding="utf-8") as f:
    r = subprocess.run(COMMON + ["-D", DST], stdin=f, env=env,
                       capture_output=True, text=True, timeout=1800)
if r.returncode != 0:
    print("RESTORE FAILED:", r.stderr.replace(settings.MYSQL_PASSWORD, "***")[:600])
    raise SystemExit(1)
print("restored from", os.path.basename(BACKUP))

tables_src = int(run(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%r" % SRC))
tables_dst = int(run(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%r" % DST))
print(f"tables: live={tables_src} restored={tables_dst} match={tables_src == tables_dst}")

rows = run("SELECT table_name, table_rows FROM information_schema.tables "
           "WHERE table_schema=%r ORDER BY table_name" % SRC)
lines = [l.split("\t") for l in rows.splitlines() if l.strip()]
top = sorted(lines, key=lambda x: -int(x[1] or 0))[:8]
for name, _ in top:
    a = run(f"SELECT COUNT(*) FROM `{SRC}`.`{name}`")
    b = run(f"SELECT COUNT(*) FROM `{DST}`.`{name}`")
    print(f"  {name}: live={a} restored={b} {'OK' if a == b else 'MISMATCH'}")

sample = run(f"SELECT COUNT(*) FROM `{SRC}`.students WHERE usn='4HG23CS032'")
same = run(f"SELECT COUNT(*) FROM `{DST}`.students WHERE usn='4HG23CS032' "
           "AND blood_group=(SELECT blood_group FROM "
           f"`{SRC}`.students WHERE usn='4HG23CS032')")
print(f"row-level spot check: present={sample} identical={same}")
print("VERIFY_OK" if tables_src == tables_dst else "VERIFY_INCOMPLETE")
