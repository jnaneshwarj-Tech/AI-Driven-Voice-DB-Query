# Master QA Test Manifest — College Student Database ERP

Run date: 2026-10-11 · Repo: `C:\Users\manoj\Desktop\major` · Scope: 12-phase final QA brief.

Rules of evidence used throughout:
- Expected results are computed independently from SQL against the isolated staging
  database (`student_db_staging`), never from the application's own output.
- Production database `student_db` is never reset or destructively written.
- A test is PASS only when the returned USN set and values match DB truth.
  Skipped / blocked is recorded as such and never counted as a pass.

Environment
- Backend: FastAPI `main.py`, documented start `python main.py` (port 8000).
- Frontend: Vite `npm run dev` (port 5173, proxy `/api` -> 127.0.0.1:8000).
- Tests: `cd backend && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`
- Staging: `MYSQL_DB=student_db_staging` (pydantic-settings env override, no code change).

Status legend: PASS / FAIL / FIXED-RETEST-PASS / SKIP / BLOCKED. Severity: S1 blocker, S2 major, S3 minor.

| ID | Phase | Input / action | Expected | Actual | Status | Defect (sev) | Fix | Retest |
|----|-------|----------------|----------|--------|--------|--------------|-----|--------|
| P1-01 | 1 | `git status` inventory before any change | Checkpoint exists, no work lost | Repo dirty (36 modified / 54 untracked); archive `_qa_checkpoints/code_20261011_140659.tar.gz` (593 files) + commit `30c0f0a5` (74 files) | PASS | - | - | - |
| P1-02 | 1 | `mysqldump` latest manual backup `backup_manual_20261011_130212.sql` (106 MB) restored into fresh schema `student_db_backupcheck` | Restore succeeds, table + row counts match live | 36/36 tables; row-level spot check identical; top tables match; log tables differ only by writes made after 13:02 | PASS | - | - | - |
| P1-03 | 1 | Drop the verification schema afterwards | `student_db` untouched, staging schema removed | `remaining schemas: student_db` | PASS | - | - | - |
| P1-04 | 1 | Existing test suite against current code (baseline) | Recorded, incl. pre-existing failures | `Ran 329 tests in 51.020s — OK` (0 failures) | PASS | none pre-existing | - | - |
| P1-05 | 1 | Real commands identified from docs | Documented, not guessed | README: `python init_mysql.py`, `python main.py`, `npm run dev`. No test command is documented anywhere in README/PROJECT_STATUS/FINAL_QA_REPORT | PASS (gap logged as P1-08) | - | - | - |
| P1-06 | 1 | Isolated staging DB built from live *structure only* (`mysqldump --no-data`) | 36 tables, zero production rows | `student_db_staging` = 36 tables, then truncated; seed report: 63 students, 310 marks rows, all 11 lifecycle statuses, 6 districts, 20 students with backlogs, 55 with pending/unpaid fees | PASS | - | - | - |
| P1-07 | 1 | Synthetic fixtures cover Phase-3 boundary cases | CGPA exactly 8.00 / 7.50 / 6.00, duplicate names, Kannada names, blank personal fields, missing parent phone | Present (seed indices 0-2, 3-5 `Rahul Kumar`, 7-9 Kannada, 10-12 sparse, `idx%3` parent-phone-blank) | PASS | - | - | - |
| P1-08 | 1 | Documentation lists how to run tests | New dev can run the suite | Was undocumented | FIXED-RETEST-PASS (S3) | No test/staging command in README | README section "4. Test suite (isolated staging database)" with the exact commands used here | re-read README, commands executed verbatim |
| P1-09 | 1 | Run the 329-test suite against staging instead of production | Suite passes with zero production data | First run: `Ran 329 … FAILED (failures=19, errors=2)`; all 21 traced to one hidden data-loss defect (D0) plus three test-premise bugs (D5-D7). After fixes: **`Ran 332 tests — OK`**, staging row count unchanged by the run | FIXED-RETEST-PASS | see D0, D5, D6, D7 | see defect register | full suite on staging, twice |
| P1-10 | 1 | Policy check: tests must not touch production | Destructive tests are impossible against `student_db` by default | A `Bash` guard blocked a production-suite run; staging is the documented target | PASS | - | - | - |

## Defect register (rolling)

| # | ID | Sev | Where | Symptom | Root cause | State |
|---|----|-----|-------|---------|------------|-------|
| D0 | P1-09 | **S1** | `routes_query.py` `/query/generate` + `/query/analytics` → `routes_files.reconcile_trashed_file_data()` → `_reconcile_orphaned_source_records()` | **Typing in the search box deleted every student and every mark row.** Reproduced 5/5: staging went 63 → 0 rows on a single `"???"` search; also fired for `show all students`. Silent, unaudited, unrecoverable except from a backup | A Trash cleanup sweep ran on the *read* path and judged a student disposable whenever its `source_file` had no `uploaded_files` row — so any row not created through the upload UI (script-seeded, restored from backup, imported before upload tracking, or whose file row had been pruned) was mass-deleted | FIXED: sweep now requires the concrete filenames just purged from Trash (`_purge_expired_trash` returns them), runs only at the file endpoints, captures an undo snapshot and writes a `FILE_DATA_PURGE` audit record; removed from both read endpoints. Pinned by `tests/test_read_path_data_safety.py` (3 tests) |
| D1 | P7-01 | S2 | `backend/routes_backup.py::_run_mysql_restore` | Restore can only target the live `settings.MYSQL_DB`; restoring a backup overwrites production by design, with no target-schema option and no confirmation beyond the route guard | Restore command hard-codes the app DB | OPEN |
| D2 | P7-02 | S2 | `backend/routes_backup.py` (`mysqldump`/`mysql` argv) | DB password passed as `-p<secret>` in argv → visible to any process list / job object on the host; other call sites already use `MYSQL_PWD` | CLI credential passing | OPEN |
| D3 | P4-01 | S2 | schema: `student_fees`, `student_lifecycle_events`, `student_lifecycle_status`, `marks`, `student_history` have no FK to `students` | Deleting a student leaves orphan academic/fee/lifecycle rows which re-attach to a re-imported student with the same USN | No cascading constraint | OPEN (user approval pending for schema change) |
| D4 | P7-03 | S3 | `routes_auth` registration/reset | `admin@college.edu` is a dead Admin e-mail, so Admin cannot receive an OTP; `register()` hard-codes Staff role | Seeded credential without reachable mailbox | OPEN |
| D5 | P1-09 | S3 (test) | `tests/test_nl_staff_queries.py::test_who_not_paid_fees` | Truth SQL counted only `'no'`/`'not paid'` as unpaid, so students whose fee says `pending` were "extra rows" from a correct engine | Test defined truth too narrowly | FIXED: truth is now "at least one fee row recording no payment" (`no/not paid/unpaid/pending/due/balance/0`); set equality still asserted |
| D6 | P1-09 | S3 (test) | `tests/test_distance_backlog_queries.py::test_backlog_list_projects_academic_and_subject` | "stored semester overridden" — keying stored semesters by USN collapsed a student's several backlogs onto one value | Test assumed at most one backlog per student | FIXED: keyed by `(usn, subject)`, still asserts exact equality |
| D7 | P1-09 | S3 (test) | `tests/test_adversarial_search.py::test_unmappable_occupation_phrasing_clarifies_not_errors` | `"list farmer father students"` failed for returning 14 rows — which are *exactly* the 14 farmer-father students in DB truth | Test forbade the spec's own "offer the closest valid interpretation" | FIXED: either a 400 clarification or the exact authoritative set; a wrong set still fails |
