"""
Master QA Phase 9 — undo, backups and recovery.

A backup is only worth what the restore door can do with it, and an undo token is
only worth what it can really put back. So this file tests the doors, not the
happy path:

  * what the dump/restore command line actually looks like (a password in argv is
    readable by anyone who can list processes on the college's server),
  * what `POST /api/backup/restore/{id}` refuses before it touches anything —
    a wrong file, a dump of another database, an unconfirmed call — and whether a
    refused attempt still costs a 10 MB safety dump,
  * whether the backup register and the disk agree (a dump no row points at is a
    backup nobody can restore and nothing can clean up),
  * whether an undo really restores every row it captured, and whether it notices
    work that another operator did *after* the snapshot.

Everything here runs against the staging database, writes only synthetic
`9ZZ9P…` USNs and temporary files, and cleans up after itself. The restore
subprocess is stubbed in this file: a real restore of the staging database is
proved over HTTP in `qa/live_phase9_recovery_check.py`.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import routes_backup
import routes_undo
from config import settings
from database import db_conn
from fastapi import HTTPException

USN = "9ZZ9P00001"
OTHER = "9ZZ9P00002"
ADMIN = {"username": "p9_admin", "role": "Admin"}
QA_PREFIX = "9ZZ9P"


def _sql(q, p=()):
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(q, p)
        rows = list(cur.fetchall())
        cur.close()
    return rows


def _run(q, p=()):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, p)
        conn.commit()
        cur.close()


def _seed_students():
    _purge()
    for usn, name, sem in ((USN, "Undo One", 5), (OTHER, "Undo Two", 6)):
        _run("INSERT INTO students (usn, name, gender, district, area_type, branch,"
             " current_sem, lifecycle_status) VALUES (%s,%s,'Male','Hassan','RURAL',"
             " 'CSE',%s,'Active')", (usn, name, sem))
    _run("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,1,8.00,2024)", (USN,))
    _run("INSERT INTO marks (usn, semester, sgpa, year) VALUES (%s,2,9.00,2025)", (USN,))
    _run("INSERT INTO student_fees (usn, fee_type, year, status, amount_paid,"
         " remaining_amount) VALUES (%s,'VTU',1,'Paid','5000','0')", (USN,))
    _run("INSERT INTO student_backlogs (usn, subject, semester, year, cleared)"
         " VALUES (%s,'Operating Systems',4,'2026',0)", (USN,))
    _run("INSERT INTO student_lifecycle_status (usn, current_status, effective_date,"
         " reason, reason_category, last_enrolled_semester, updated_by)"
         " VALUES (%s,'Active',%s,'regular','Other',5,'p9_admin')",
         (USN, datetime.now().strftime("%Y-%m-%d")))


def _purge():
    for q in ("DELETE FROM marks WHERE usn LIKE %s",
              "DELETE FROM student_fees WHERE usn LIKE %s",
              "DELETE FROM student_backlogs WHERE usn LIKE %s",
              "DELETE FROM student_field_sources WHERE usn LIKE %s",
              "DELETE FROM student_lifecycle_status WHERE usn LIKE %s",
              "DELETE FROM student_lifecycle_events WHERE usn LIKE %s",
              "DELETE FROM students WHERE usn LIKE %s"):
        _run(q, (f"{QA_PREFIX}%",))
    _run("DELETE FROM global_undo_snapshots WHERE performed_by LIKE 'p9_%'")
    _run("DELETE FROM db_backups WHERE created_by LIKE 'p9_%'")
    _run("DELETE FROM audit_log WHERE username LIKE 'p9_%'")


class _Stub:
    """Temporarily replace a module attribute and put it back."""

    def __init__(self, module, name, value):
        self.module, self.name = module, name
        self.new = value
        self.missing = object()

    def __enter__(self):
        self.old = getattr(self.module, self.name, self.missing)
        setattr(self.module, self.name, self.new)
        return self

    def __exit__(self, *exc):
        if self.old is self.missing:
            delattr(self.module, self.name)
        else:
            setattr(self.module, self.name, self.old)
        return False


class CommandLineHygiene(unittest.TestCase):
    """The password must never reach the process list of the college's server."""

    def setUp(self):
        _purge()

    def _capture(self, func, path):
        calls = {}

        def fake_run(cmd, **kw):
            calls["cmd"] = list(cmd)
            calls["env"] = dict(kw.get("env") or {})
            calls["kw"] = kw

            class R:
                returncode = 0
                stderr = ""
                stdout = ""
            return R()

        with _Stub(routes_backup.subprocess, "run", fake_run), \
             _Stub(routes_backup, "_mysqldump_path", lambda: "mysqldump"), \
             _Stub(routes_backup, "_mysql_path", lambda: "mysql"):
            ok, err = func(path)
        return calls, ok, err

    def test_the_dump_command_never_carries_the_password_in_argv(self):
        secret = settings.MYSQL_PASSWORD
        self.assertTrue(secret, "staging is expected to have a DB password")
        with tempfile.TemporaryDirectory() as td:
            calls, ok, _ = self._capture(routes_backup._run_mysqldump,
                                         os.path.join(td, "out.sql"))
        joined = " ".join(calls["cmd"])
        self.assertNotIn(secret, joined, "mysqldump got the password in argv")
        self.assertFalse([a for a in calls["cmd"] if a.startswith("-p")],
                         f"a -p<secret> argument is still being passed: {calls['cmd']}")
        self.assertTrue(ok)

    def test_the_restore_command_never_carries_the_password_in_argv(self):
        secret = settings.MYSQL_PASSWORD
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("-- MySQL dump 10.13\nCREATE TABLE `students` (`usn` int);\n")
            path = fh.name
        try:
            calls, ok, _ = self._capture(routes_backup._run_mysql_restore, path)
        finally:
            os.unlink(path)
        joined = " ".join(calls["cmd"])
        self.assertNotIn(secret, joined, "mysql restore got the password in argv")
        self.assertFalse([a for a in calls["cmd"] if a.startswith("-p")],
                         f"a -p<secret> argument is still being passed: {calls['cmd']}")
        self.assertTrue(ok)

    def test_the_password_still_reaches_the_tools(self):
        # Moving it out of argv must not break authentication: the supported
        # channel is the MYSQL_PWD environment variable.
        with tempfile.TemporaryDirectory() as td:
            calls, _, _ = self._capture(routes_backup._run_mysqldump,
                                        os.path.join(td, "out.sql"))
        env = calls["env"]
        self.assertEqual(env.get("MYSQL_PWD"), settings.MYSQL_PASSWORD,
                         "the password was neither in argv nor in MYSQL_PWD — the "
                         "dump would simply fail to authenticate")

    def test_the_dump_leaves_the_register_and_the_audit_trail_outside_itself(self):
        # A restore rewinds whatever the dump carries. Dumping `db_backups` meant
        # the pre-restore safety dump lost its own register row to the restore it
        # was protecting (the file stayed on disk, unnamed, unprunable); dumping
        # `audit_log` meant every entry written between the dump and the restore
        # was destroyed, including that restore's own RESTORE_START entry.
        with tempfile.TemporaryDirectory() as td:
            calls, ok, _ = self._capture(routes_backup._run_mysqldump,
                                         os.path.join(td, "out.sql"))
        ignored = {a.split("=", 1)[1] for a in calls["cmd"] if a.startswith("--ignore-table=")}
        self.assertTrue({f"{settings.MYSQL_DB}.db_backups", f"{settings.MYSQL_DB}.audit_log"}
                        <= ignored,
                        f"the dump still carries the records a restore rewinds: {sorted(ignored)}")
        self.assertFalse([t for t in ignored if t.split(".", 1)[1] in
                          ("students", "marks", "student_fees", "student_backlogs")],
                         "the dump excludes college records, so a restore would not bring them back")
        self.assertTrue(ok)

    def test_a_failure_message_never_echoes_the_password(self):
        secret = settings.MYSQL_PASSWORD
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "out.sql")

            def fake_run(cmd, **kw):
                class R:
                    returncode = 2
                    stderr = f"mysqldump: Got error: 1045: Access denied for 'x' (using password: YES) {secret}"
                    stdout = ""
                return R()

            with _Stub(routes_backup.subprocess, "run", fake_run), \
                 _Stub(routes_backup, "_mysqldump_path", lambda: "mysqldump"):
                ok, err = routes_backup._run_mysqldump(out)
        self.assertFalse(ok)
        self.assertNotIn(secret, err)


class _RestoreHarness(unittest.TestCase):
    """Call the restore door with the subprocess and the safety dump stubbed."""

    def setUp(self):
        _purge()
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        self.ran = []

    def tearDown(self):
        _purge()
        self.tmp.cleanup()

    def dump(self, body, name="p9_dump.sql", path=None):
        p = path or os.path.join(self.tmp.name, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return p

    def row(self, backup_type="manual", status="success", path=None, name="p9_dump.sql",
            created_at=None):
        _run("INSERT INTO db_backups (backup_name, backup_path, backup_type, status,"
             " verified, created_by, record_count, size_bytes, created_at)"
             " VALUES (%s,%s,%s,%s,1,%s,3,1024,%s)",
             (name, path or os.path.join(self.tmp.name, name), backup_type, status,
              "p9_admin", created_at or datetime.now() - timedelta(days=1)))
        return _sql("SELECT id FROM db_backups WHERE backup_name=%s", (name,))[0]["id"]

    def call_restore(self, backup_id, confirmed=True):
        stubs = []
        calls = self.calls

        def fake_restore(path):
            calls.append(path)
            return True, ""

        def fake_safety(backup_type="manual", created_by="system"):
            self.ran.append(backup_type)
            return {"success": True, "backup_id": 999, "backup_name": "p9_safety.sql"}

        stubs.append(_Stub(routes_backup, "_run_mysql_restore", fake_restore))
        stubs.append(_Stub(routes_backup, "create_backup_internal", fake_safety))
        with stubs[0], stubs[1]:
            return routes_backup.restore_backup(
                backup_id, routes_backup.RestoreRequest(confirmed=confirmed),
                current_user=ADMIN)


class RestoreDoorGuards(_RestoreHarness):
    def test_a_file_that_is_not_a_database_dump_is_refused(self):
        # Someone picks the wrong .sql from the backup folder: the door must say
        # no before it overwrites the college's database.
        path = self.dump("<html><body>404 Not Found</body></html>\n" * 5)
        bid = self.row(path=path)
        with self.assertRaises(HTTPException) as got:
            self.call_restore(bid)
        self.assertEqual(got.exception.status_code, 400)
        self.assertIn("dump", str(got.exception.detail).lower())
        self.assertEqual(self.calls, [], "mysql was handed a file that is not a dump")

    def test_a_dump_of_some_other_application_is_refused(self):
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `orders` (`id` int);\n"
                        "INSERT INTO `orders` VALUES (1);\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException) as got:
            self.call_restore(bid)
        self.assertEqual(got.exception.status_code, 400)
        self.assertEqual(self.calls, [], "a dump with no student tables was restored anyway")

    def test_a_dump_taken_from_a_different_database_is_refused(self):
        # mysqldump with --databases writes a USE statement; restoring that into
        # the app's own schema would silently move the whole college elsewhere.
        path = self.dump("-- MySQL dump 10.13\nCREATE DATABASE !40100 `other_college`;\n"
                        "USE `other_college`;\nCREATE TABLE `students` (`usn` int);\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException) as got:
            self.call_restore(bid)
        self.assertEqual(got.exception.status_code, 400)
        self.assertIn("other_college", str(got.exception.detail))
        self.assertEqual(self.calls, [])

    def test_a_dump_whose_header_declares_another_database_is_refused(self):
        # `backend/backups/` is one folder shared by two schemas and demonstrably
        # holds dumps of both (measured: 89 declaring `student_db`, 35 declaring
        # staging). mysqldump without --databases writes no USE statement, so its
        # own header comment is the only marker the file carries — and a staging
        # dump restored over the college's real database would replace every
        # record with synthetic QA rows.
        other = "some_college_elsewhere"
        path = self.dump("-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)\n"
                         "--\n"
                         f"-- Host: localhost    Database: {other}\n"
                         "-- ------------------------------------------------------\n"
                         "CREATE TABLE `students` (`usn` varchar(20));\n"
                         "INSERT INTO `students` VALUES ('0000000000');\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException) as got:
            self.call_restore(bid)
        self.assertEqual(got.exception.status_code, 400)
        msg = str(got.exception.detail)
        self.assertIn(other, msg, "the refusal did not say which schema the dump is for")
        self.assertIn(settings.MYSQL_DB, msg, "the refusal did not say what this app runs on")
        self.assertEqual((self.calls, self.ran), ([], []),
                         "mysql was handed a dump of another database")

    def test_a_dump_declared_for_this_database_is_still_restored(self):
        # The counter-test, without which the header check would just be a door
        # that refuses everything: this app's own dumps name this schema.
        path = self.dump("-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)\n"
                         "--\n"
                         f"-- Host: localhost    Database: {settings.MYSQL_DB}\n"
                         "-- ------------------------------------------------------\n"
                         "CREATE TABLE `students` (`usn` varchar(20));\n"
                         "INSERT INTO `students` VALUES ('9ZZ9P00001');\n")
        bid = self.row(path=path)
        out = self.call_restore(bid)
        self.assertTrue(out["success"], out)
        self.assertEqual(self.calls, [path])

    def test_a_real_dump_of_the_other_schema_in_this_folder_is_refused(self):
        # Not a fixture: the college's own backup folder, read only. Measured at
        # Phase 9 close-out it holds dumps declaring two different schemas, which
        # is exactly the mix this check exists for.
        d = routes_backup._backup_dir()
        foreign = []
        for name in sorted(os.listdir(d)):
            if not name.endswith(".sql"):
                continue
            p = os.path.join(d, name)
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    head = "".join([fh.readline() for _ in range(4)])
            except OSError:
                continue
            m = re.search(r"--\s*(?:Host:.*?|Current\s)?Database:\s*`?([^`\s]+)`?", head)
            if m and m.group(1) != settings.MYSQL_DB:
                foreign.append((os.path.getsize(p), name, p, m.group(1)))
        if not foreign:
            self.skipTest(f"no dump in {d} declares a schema other than "
                          f"{settings.MYSQL_DB} — nothing real to refuse")
        _, name, path, db = min(foreign)
        problem = routes_backup._dump_problem(path)
        self.assertIsNotNone(problem, f"{name} is a dump of '{db}' and the door "
                                     f"would have restored it into "
                                     f"'{settings.MYSQL_DB}'")
        self.assertIn(db, problem)

    def test_a_refused_restore_does_not_cost_a_safety_dump(self):
        # The order matters: taking a pre-restore dump first means every refused
        # or repeated attempt writes ~10 MB to the same disk as the database.
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `orders` (`id` int);\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException):
            self.call_restore(bid)
        self.assertEqual(self.ran, [], "a pre_restore dump was taken for a restore "
                                       "that was about to be refused")

    def test_a_refused_restore_is_written_to_the_audit_log(self):
        path = self.dump("not a dump at all\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException):
            self.call_restore(bid)
        rows = _sql("SELECT action, summary FROM audit_log WHERE username='p9_admin'")
        self.assertTrue([r for r in rows if "REFUSE" in r["action"]
                         or r["action"] == "RESTORE_FAILED"],
                        f"a refused restore left no trace: {[r['action'] for r in rows]}")

    def test_a_usable_dump_is_still_restored(self):
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `students` (`usn` int);\n"
                        "CREATE TABLE `marks` (`usn` int);\nINSERT INTO `students` VALUES (1);\n")
        bid = self.row(path=path)
        out = self.call_restore(bid)
        self.assertTrue(out["success"])
        self.assertEqual(self.calls, [path])
        self.assertEqual(self.ran, ["pre_restore"],
                         "the safety dump must still be taken for a real restore")

    def test_an_unconfirmed_restore_does_nothing_at_all(self):
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `students` (`usn` int);\n")
        bid = self.row(path=path)
        with self.assertRaises(HTTPException) as got:
            self.call_restore(bid, confirmed=False)
        self.assertEqual(got.exception.status_code, 400)
        self.assertEqual((self.calls, self.ran), ([], []))


class BackupRegisterTruth(_RestoreHarness):
    def test_the_list_reports_the_path_the_record_carries(self):
        # restore_backup() resolves backup_path first, the list resolves the
        # backup dir + name; when the two disagree the UI says the file is gone
        # while the door would happily restore it (or the reverse).
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `students` (`usn` int);\n",
                         name="elsewhere.sql")
        self.row(path=path, name="p9_moved.sql")
        listed = [b for b in routes_backup.list_backups(current_user=ADMIN)
                  if b["backup_name"] == "p9_moved.sql"]
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0]["file_exists"],
                        "the file is on disk at the recorded path but the list says missing")

    def test_a_dump_on_disk_that_no_record_points_at_is_visible(self):
        # Orphans are the D76 mechanism: files nothing can restore and nothing
        # prunes. Admin has to be able to see them, not guess them.
        orphans = [f for f in os.listdir(routes_backup._backup_dir())
                   if f.endswith(".sql")]
        self.assertTrue(orphans, "no dumps on disk to reason about")
        stray = os.path.join(routes_backup._backup_dir(), "p9_orphan_probe.sql")
        with open(stray, "w", encoding="utf-8") as fh:
            fh.write("-- MySQL dump 10.13\n")
        try:
            status = routes_backup.get_storage_status(current_user=ADMIN)
            names = json.dumps(status, default=str)
            self.assertIn("p9_orphan_probe.sql", names,
                          "the storage view counts bytes but cannot name a dump "
                          "that its own register has forgotten")
        finally:
            os.remove(stray)

    def test_the_delete_door_does_not_promise_a_cleanup_that_never_happens(self):
        # Seed an old pre_restore row against a temporary file, run the real
        # retention policy, then compare reality with what DELETE claims.
        path = self.dump("-- MySQL dump 10.13\nCREATE TABLE `students` (`usn` int);\n",
                         name="p9_pre.sql")
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
        self.row(backup_type="pre_restore", path=path, name="p9_pre.sql", created_at=old)
        bid = _sql("SELECT id FROM db_backups WHERE backup_name='p9_pre.sql'")[0]["id"]
        routes_backup._apply_retention_policy()
        pruned = not _sql("SELECT id FROM db_backups WHERE id=%s", (bid,))
        file_gone = not os.path.exists(path)
        message = ""
        try:
            routes_backup.delete_backup(bid, current_user=ADMIN)
        except HTTPException as exc:
            message = str(exc.detail)
        self.assertTrue(message, "deleting a pre_restore backup should be refused, not allowed")
        # What matters is the direction of the claim: staff must not be told an
        # automatic cleanup will deal with this file, because the policy above
        # demonstrably does not. A denial counts as truth only if reality agrees.
        denial = bool(re.search(
            r"nothing (deletes|prunes|removes|cleans)|never (deletes|prunes|removes|cleans)"
            r"|no automatic|will not be (pruned|deleted|removed|cleaned)", message, re.I))
        self.assertEqual(denial, not (pruned and file_gone),
                         f"the door says {message!r} but the policy "
                         f"{'did' if pruned else 'did not'} clean it up")


class UndoSnapshotFidelity(unittest.TestCase):
    def setUp(self):
        _seed_students()

    def tearDown(self):
        _purge()

    def _snapshot_and_mutate(self, usns=(USN,)):
        """Snapshot, then really change the student, then finalise — one transaction."""
        with db_conn() as conn:
            cur = conn.cursor()
            conn.start_transaction()
            try:
                token = routes_undo.create_undo_snapshot(
                    "UPDATE", list(usns), "p9_admin", "phase 9 probe", conn=conn)
                cur.execute("UPDATE students SET name='Changed By The Operation'"
                            " WHERE usn=%s", (usns[0],))
                cur.execute("DELETE FROM marks WHERE usn=%s", (usns[0],))
                cur.execute("INSERT INTO marks (usn, semester, sgpa, year)"
                            " VALUES (%s,1,3.00,2024)", (usns[0],))
                routes_undo.finalize_undo_snapshot(token, list(usns), conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
        return token

    def test_an_undo_puts_every_captured_row_back(self):
        token = self._snapshot_and_mutate()
        out = routes_undo.restore_student(token, current_user=ADMIN)
        self.assertTrue(out["success"], out)
        self.assertEqual(_sql("SELECT name, current_sem FROM students WHERE usn=%s",
                             (USN,))[0]["name"], "Undo One")
        self.assertEqual([(r["semester"], str(r["sgpa"]))
                          for r in _sql("SELECT semester, sgpa FROM marks WHERE usn=%s"
                                        " ORDER BY semester", (USN,))],
                         [(1, "8.00"), (2, "9.00")],
                         "the undo did not put both original mark rows back")
        self.assertEqual(_sql("SELECT amount_paid FROM student_fees WHERE usn=%s",
                             (USN,))[0]["amount_paid"], "5000")
        self.assertEqual(_sql("SELECT subject FROM student_backlogs WHERE usn=%s",
                             (USN,))[0]["subject"], "Operating Systems")

    def test_a_row_the_undo_cannot_put_back_is_not_swallowed(self):
        # marks/fees used to be re-inserted inside `except Exception: pass`, so a
        # rejected row left the student short while the undo said "restored".
        token = self._snapshot_and_mutate()
        row = _sql("SELECT snapshot_data FROM global_undo_snapshots WHERE undo_token=%s",
                   (token,))[0]
        data = json.loads(row["snapshot_data"])
        self.assertTrue(data["existing_fees"], "fixture has no fee row to corrupt")
        data["existing_fees"][0]["column_that_does_not_exist"] = 1
        _run("UPDATE global_undo_snapshots SET snapshot_data=%s WHERE undo_token=%s",
             (json.dumps(data), token))
        failed = False
        try:
            out = routes_undo.restore_student(token, current_user=ADMIN)
            failed = not out.get("success")
        except Exception:
            failed = True
        self.assertTrue(failed, "an unrecoverable fee row was swallowed and reported as success")
        still = _sql("SELECT undone FROM global_undo_snapshots WHERE undo_token=%s", (token,))
        self.assertTrue(still, "the snapshot disappeared")
        self.assertEqual(int(still[0]["undone"]), 0,
                         "the token was marked used even though the restore failed")
        self.assertEqual(_sql("SELECT COUNT(*) c FROM student_fees WHERE usn=%s", (USN,))[0]["c"],
                         1, "the failed undo left the fee rows gone")

    def test_a_lifecycle_edit_made_after_the_snapshot_is_not_overwritten_silently(self):
        # The register is not a captured section today: another clerk's newer
        # status work must at least stop this undo rather than be replaced by it.
        token = self._snapshot_and_mutate()
        _run("UPDATE student_lifecycle_status SET reason='written by someone else later',"
             " updated_by='p9_other' WHERE usn=%s", (USN,))
        blocked = False
        try:
            out = routes_undo.restore_student(token, current_user=ADMIN)
            blocked = not out.get("success")
        except Exception:
            blocked = True
        self.assertTrue(blocked,
                        "the undo ran over a lifecycle register edit it never captured")
        self.assertEqual(
            _sql("SELECT reason FROM student_lifecycle_status WHERE usn=%s", (USN,))[0]["reason"],
            "written by someone else later",
            "a newer register edit was destroyed by an undo of an older change")

    def test_the_undo_says_how_much_it_put_back(self):
        token = self._snapshot_and_mutate()
        out = routes_undo.restore_student(token, current_user=ADMIN)
        self.assertTrue(out["success"], out)
        counts = out.get("restored")
        self.assertIsInstance(counts, dict,
                              "the response gives staff no way to see what came back")
        self.assertEqual(counts.get("marks"), 2,
                         f"two mark rows went in, response says {counts}")
        self.assertEqual(counts.get("students"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
