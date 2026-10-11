
---

# Phase 1 defect register + Phase 5 security audit (this session)

## Security + authorization audit (task #75) — findings & fixes

Every protected route was re-checked for a guard, and the concrete gaps were
repaired in-code (not just reported). New tests live in
`backend/tests/test_security_authz.py` (15 tests, all green).

**Fixed this session**

1. **Spreadsheet formula injection in CSV/Excel exports** (OWASP CSV injection).
   Free-text student fields (name, address, discontinuation reason, uploaded
   dynamic headings) were written verbatim, so a value like `=HYPERLINK(...)`
   would execute when the report was opened in Excel/Sheets.
   - `routes_export.py`: added `_csv_cell` (leading-apostrophe guard, also strips
     a leading tab/CR that Excel trims before formula detection), `_safe_writer`
     (wraps both CSV writers so every `writerow` is neutralised), and
     `_harden_workbook` (re-types any openpyxl formula cell back to a plain
     string — display is unchanged, the value can no longer run). Wired into the
     detail-Excel, detail-CSV, table-Excel and table-CSV builders.
   - Test builds a one-cell report model, writes real `.csv`/`.xlsx`, reads the
     bytes back and asserts no cell remains a formula and the text is preserved.

2. **Path-traversal on uploads.** `_save_upload_cache` / `_get_upload_cache` /
   `_remove_upload_cache` joined a client-controlled filename straight onto the
   upload dir, so `../../…` or an absolute path could read/write outside it.
   - `routes_files.py`: added `_upload_path()` — reduces the name to its
     basename (slash-agnostic), rejects empty/`.`/`..`, and confirms via
     `realpath` + `commonpath` that the result is still inside the uploads
     directory. All three helpers now route through it.
   - Tests assert hostile names resolve inside the dir and never escape.

3. **Schema cache never invalidated after upload.** `intent_fields`
   (`_COLS_CACHE` / `_DYN_CACHE`) was refreshed only by `invalidate_cache()`,
   which was never called in production, so headings added by a new file stayed
   unsearchable until the process restarted.
   - `routes_files.py` `update_database`: calls `intent_fields.invalidate_cache()`
     right after `register_dynamic_fields(...)` commits. Satisfies Phase 1
     ("stale caches / outdated schema mappings") and Phase 6 ("caches
     invalidated after relevant writes").

**Verified clean (no change needed)**

- **JWT lifecycle**: expired, foreign-signed and garbage tokens all raise 401; a
  missing `SECRET_KEY` fails closed with 503 (`_configured_jwt_secret`). Tested.
- **Role enforcement** `require_roles`: correct role passes, wrong role → 403,
  match is case/whitespace insensitive. Tested.
- **Destructive SQL**: `validate_sql_query` refuses Staff `DELETE` and refuses
  `DROP`/`TRUNCATE`/unbounded `DELETE` for every role, so a rejected write never
  reaches MySQL and the record is unchanged. Tested.
- **PII in logs**: audit summaries and `logger.*` calls record username, action,
  name+USN and query text — never Aadhaar/phone/password/OTP. Confirmed.
- **Secret leakage in errors**: `routes_backup` scrubs `MYSQL_PASSWORD` from
  mysqldump stderr before returning; the only `{e}`-in-detail paths are DB parse
  errors that do not carry credentials. Confirmed.

## Phase 1 register — dead / stale code found (NOT deleted — needs your go-ahead)

These are genuinely unused or broken, but the repo is not under git, so deleting
shared files is irreversible. I am surfacing them rather than removing them:

- `backend/sync_students.py` — leftover MongoDB code (`students_col` no longer
  exists); broken and unreferenced.
- `backend/rag_sql_generator.py:~2295` `generate_mongo_query` — dead alias.
- `backend/email_service.py:~244` — deprecated link-reset path; verify unreferenced.
- `backend/routes.py`, `query_engine.py`, `schema_init.py` — 0-byte / never-mounted
  routers (`main.py` mounts only auth/query/export/files/undo/backup/monitor/lifecycle).
- `backend/schema_metadata.json` (PostgreSQL `SERIAL` model) and
  `schema_memory.json` — unreferenced; note `schema_metadata ready` is still
  printed at startup by a mount that no longer uses it.
- `backend/app.db` — 86 KB SQLite artifact; no code opens it.
- `database/schema.sql` — duplicates `create_indexes`, not imported.
- Destructive one-off CLIs at the backend root (`full_reset.py`,
  `drop_uploaded_data.py`, `clear_uploaded_data.py`, `remove_dummy.py`,
  `fix_usn_length.py`, `add_missing_cols.py`, `seed_marks.py`, `check_*.py`) —
  a deployment footgun; recommend quarantining them out of the shipped tree.
- Duplicate frontend tree at repo root (`src/`, `index.html`, `vite.config.js`,
  `dist/`) plus `major 2/` and `AI-Driven-Voice-DB-Query/` copies.
- `_file_cache` (routes_files.py) is per-worker and popped only on delete —
  unreliable under multiple workers; document single-worker or move to a shared store.

Full backend suite after these changes: **254 tests OK**.
