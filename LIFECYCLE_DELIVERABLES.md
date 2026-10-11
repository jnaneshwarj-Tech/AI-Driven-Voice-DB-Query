# Student Lifecycle Management — Final Deliverables & Production Status

Feature: **Student discontinuation, dropout, readmission, rejoining, and
VTU-aligned academic lifecycle management**, integrated into the existing
multilingual Student DBMS (no separate app).

Status date: 2026-10-09

---

## One honest status

**READY WITH DOCUMENTED LIMITATIONS** for production deployment against the
real MySQL `student_db`.

Everything that must be *safe and correct* is implemented, tested, and live.
The limitations are deliberate, conservative design choices required by the
brief ("do not invent VTU rules, do not guarantee eligibility, do not
auto-approve readmission"), not defects. They are listed explicitly below so no
one is misled about what the system does and does not decide on its own.

---

## Evidence (verified this session)

| Check | Result |
|---|---|
| Backend unit/integration suite | `python -m unittest discover -s tests` → **Ran 144 tests … OK** |
| Lifecycle test file | `tests/test_lifecycle.py` → **37 tests OK** |
| Production frontend build | `npm run build` → 2243 modules transformed, **built successfully** |
| Live server | `uvicorn main:app` on 127.0.0.1:8000 → `/docs` = **200** |
| Registered lifecycle routes | **10** under `/api/lifecycle` (all visible in `/openapi.json`) |
| Live auth/role smoke test | OPTIONS=200; missing student→404; bad relation type→400; Staff on Admin-only `/status`→**403** |
| Migration idempotency | All lifecycle tables created with `CREATE TABLE IF NOT EXISTS`; `students.lifecycle_status` added via `_add_col_if_missing` → re-runnable |
| Production `vtu_scheme_rules` content | **0 verified rules** → eligibility is always review-required by design |

No production student, marks, fee, backlog, or semester row was deleted or
altered to achieve any of the above; only synthetic `9ZZLC*` test rows are ever
created by the tests and removed in teardown.

---

## What is implemented, by spec section

- **§2 Lifecycle statuses** — 11 canonical statuses (≤30 chars) with
  Active / Discontinued / Readmission buckets in `lifecycle.py`.
- **§3 Preserve USN & controlled identity links** — `student_identity_links`
  table + Admin-only create/list/delete endpoints. A link is a *recorded
  relationship only*; it never merges, moves, or deletes any record (verified by
  test `test_create_identity_link_records_without_merging`).
- **§4 Discontinuation workflow** — Admin `POST /students/{usn}/status`,
  transactional, audited, undoable; appends to append-only
  `student_lifecycle_events`; never touches academic/fee/semester/backlog rows
  (verified: `test_active_to_temp_discontinuation_preserves_history_and_data`,
  `test_status_change_never_deletes_fees_or_backlogs`).
- **§5 Readmission / rejoining** — request (Staff+Admin), decision
  (Admin only), approve-without-rejoin → `Readmission Approved`, approve-with-
  rejoin → `Rejoined-Active` (both verified end to end).
- **§6 Scheme-aware eligibility engine** — `lifecycle.evaluate_eligibility`,
  conservative and advisory: applies only `verification_status='verified'` rules,
  flags max-duration/backlog/unresolved-scheme concerns, and **always returns
  `review_required=True, auto_approved=False`**.
- **§7 Update records after results** — safe Admin action
  `POST /students/{usn}/backlogs/{id}/clear` flips `cleared` on a *verified*
  pass and appends a CORRECTION event. It never rewrites marks/SGPA/CGPA
  (`grade_recomputed=False`), and scheme recompute stays manual (see Limitations).
- **§8 Lifecycle reports/exports** — lifecycle status + history embedded in
  CSV, Excel, PDF, print, JSON, and the complete-profile view via
  `report_service`; reflected immediately after a change (verified).
- **§9 NL query engine (EN / Kannada Unicode / Roman-Kannada / mixed)** —
  deterministic `_build_lifecycle_query` runs before the fee/dynamic builders;
  multilingual equivalence verified through `kannada_processor.normalize_query`.
- **§10 Authorization + audit** — every write gated by `require_roles`; every
  change writes `audit_log` and an undo snapshot (verified).
- **§11 Safe, versioned migrations + integrity** — additive idempotent schema.
- **§12 Comprehensive testing** — 37 lifecycle tests covering the spec's
  scenario matrix, all green, plus the full 144-test suite.

---

## Documented limitations (intentional, conservative)

1. **No authoritative VTU rules are bundled.** The official VTU B.E./B.Tech
   regulations PDF could not be parsed to verbatim clause text during this work,
   and the brief forbids inventing rules. Therefore `vtu_scheme_rules` ships
   **empty**, and the eligibility engine consequently returns
   `manual_review_required` for every case.
   - **Action before relying on §6 numerics:** an authorized Admin must insert
     `verification_status='verified'` rows into `vtu_scheme_rules`, each carrying
     `source_url`, `clause_ref`, `effective_date`, and batch applicability,
     taken from the official regulations. Until then, treat every eligibility
     result as advisory only — which the UI and API already state.
2. **No automatic SGPA/CGPA recompute on readmission/result changes.** Grade
   recomputation per scheme is left as an explicit human action. The backlog
   `clear` action only marks a subject cleared; it deliberately does not alter
   marks. This protects authoritative academic truth.
3. **Undo restores the derived `students.lifecycle_status` and marks, not the
   append-only event history** (history is intentionally never rolled back). The
   UI shows this as "Undone / Rolled Back" on the status while preserving the
   audit trail.

---

## How to enable §6 numerics once rules are sourced

```sql
-- Example shape; supply the real values & clause from the official PDF.
INSERT INTO vtu_scheme_rules
  (scheme_code, admission_category, rule_key, rule_value,
   source_url, clause_ref, effective_date, verification_status,
   applies_from_batch, applies_to_batch)
VALUES
  ('BE2022', '', 'max_completion_years', '<verified number>',
   'https://vtu.ac.in/...', '<clause>', '<YYYY-MM-DD>', 'verified',
   2022, NULL);
```
Recognized `rule_key`s currently acted on by the engine:
`max_completion_years`, `requires_documents`. Unverified rows are ignored.

---

## Sources consulted for §1 (for the human rule owner to verify verbatim)

- [VTU B.E./B.Tech 2025 regulations (official PDF)](https://vtu.ac.in/wp-content/uploads/2026/05/B.E.B.Tech2025.pdf)
- [VTU Regulations 2022 (mirror PDF, BMSIT)](https://bmsit.ac.in/pdf/autonomous/2022-batch/VTU-Regulations_2022.pdf)
- [VTU Application Format for Readmission (B.E. 5th & 7th semester)](https://cdn.prod.website-files.com/67fdfe35d4387726dad21cae/689c6c35f71b8ca573fef3ef_Application%20Format%20for%20Readmission%20for%20B.E.%205th%20%26%207th%20Semester.pdf)
- [VTU Single Application Format for Readmission 2023 (circular page)](https://www.vturesource.com/vtu-circulars/vtu-schemes-1834.html)

---

# Spec B — Natural-Language Discontinued / Dropout Tracking & Retrieval

Status date: 2026-10-09 · **READY** — implemented end-to-end in the existing
React frontend, FastAPI backend and MySQL `student_db`; no separate app, no
replacement of working features.

## What was added (mapped to the 7 spec sections)

- **§1 NL record (preview → authorized confirm)** — `POST /api/lifecycle/nl/record`
  (`routes_lifecycle.py:594`) parses the command through the SAME multilingual
  pipeline as the query engine (`translate_query_if_needed` for Kannada/mixed +
  `normalize_query`), runs `LC.parse_lifecycle_command` for
  action/status/identity/reason/date/semester, resolves the student against
  MySQL through the existing `_match_student` resolver (never raw SQL), and
  returns `confirm | select_student | clarify | no_record`. It **writes nothing**.
  `LC._USN_RE` is strict (`<digit><2 letters><2 digits><2-3 letters><3 digits>`);
  an out-of-format token (e.g. a synthetic `9ZZLC0001`) is treated as free text
  unless passed as the explicit `usn` field — the tests confirm this boundary.
- **§2 structured permanent store** — reuses `student_lifecycle_events`
  (append-only audit) + `student_lifecycle_status` (derived cache); a status
  change never deletes/overwrites marks, fee or backlog rows, and the reason is
  captured as free text + a controlled `reason_category` (blank stays blank —
  never guessed). Temporary-discontinuation vs formal dropout stay distinct
  statuses; official dropout is never auto-labelled from absence/fees/backlogs.
- **§3 dashboards / lists / exports** — `GET /api/lifecycle/list` filters by
  status, scheme, admission_year(batch), branch, last_semester, reason_category,
  effective-date range and free-text search; whitelisted sort columns only;
  pagination + `total_count`; latest-event badge attached per row.
  `GET /api/lifecycle/export?fmt=csv|xlsx|pdf` renders a flat lifecycle register
  (USN, Name, Branch, Batch, Last Semester, Status Effective Date, Reason,
  Reason Category, Status, Latest Event, Latest Event At) reusing the existing
  reporting primitives + export audit log. Role gating + masking preserved.
- **§4 NL list/count** — the query engine's `_build_lifecycle_query` gained
  reason-category detection (`due to / ಕಾರಣ / for … reasons`), a
  rejoined-after-discontinuation filter (`from_status IN discontinued set`) and a
  corrected fees filter (the `due to` false positive on "financial" is fixed via
  `\bdue\b(?! to)`). Returns real records/counts, never fabricated.
- **§5 transitions** — approved readmission / rejoin update current status while
  preserving old events; clearing a backlog or submitting a request never
  auto-marks rejoined; `is_duplicate_lifecycle_event` + a confirmation-token
  guard prevent duplicate lifecycle events.
- **§6 security** — commit is `require_roles("Admin")` on the backend (preview
  allows Staff); consequential change needs the HMAC confirmation token
  (`query_security_validator`) bound to issuing user + exact payload, verified
  on confirm; every write is parameterised + audited with an undo token; the
  tampered/foreign-owner/expired token path returns 403.
- **§7 tests** — 20 new tests in `tests/test_lifecycle.py`.

## Migrations (idempotent — safe to re-run at startup)

`create_indexes()` in `backend/database.py` is the only schema step and is
automatic on boot. Additive + guarded:
`CREATE TABLE IF NOT EXISTS` for `student_lifecycle_status`,
`student_lifecycle_events`, `readmission_requests`, `vtu_scheme_rules`,
`student_identity_links`; `students.lifecycle_status`,
`student_lifecycle_status.reason_category`, `student_lifecycle_events.reason_category`
added via `_add_col_if_missing`; indexes `idx_le_effective`, `idx_ls_effective`
via `_add_index_if_missing`. No existing column is dropped or repurposed.

Manual equivalent (only if you want to pre-apply before boot):
```sql
ALTER TABLE students                  ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(30) NOT NULL DEFAULT 'Active';
ALTER TABLE student_lifecycle_status  ADD COLUMN IF NOT EXISTS reason_category  VARCHAR(40) NULL;
ALTER TABLE student_lifecycle_events  ADD COLUMN IF NOT EXISTS reason_category  VARCHAR(40) NULL;
CREATE INDEX IF NOT EXISTS idx_ls_effective ON student_lifecycle_status (effective_date);
CREATE INDEX IF NOT EXISTS idx_le_effective ON student_lifecycle_events (effective_date);
```

## Backup & rollback

- **Backup before deploy:** `python backend/db_backup.py` (existing routine; the
  QA suite already produced `backup_manual_20261009_*.sql`, ~95 MB, verified).
- **Roll forward** is automatic and additive — re-deploying needs no manual DDL.
- **Roll back the feature** without touching academic data: the new tables and
  `lifecycle_status`/`reason_category` columns are purely additive; drop them to
  revert (`DROP TABLE student_lifecycle_status, student_lifecycle_events,
  readmission_requests, student_identity_links, vtu_scheme_rules;` and
  `ALTER TABLE students DROP COLUMN lifecycle_status;`). Do this only if the
  feature must be fully removed — normal rollback is redeploying the previous
  app image; the old code never read these tables.
- **Undo a single record:** every confirm returns an `undo_token`; the existing
  undo system (`routes_undo.restore_student`) reverts the derived status while
  leaving the append-only event history intact.

## Failures fixed this session

- **Production ranking defect:** "last/bottom N by CGPA" returned NULL-CGPA
  students in ascending order. Fixed in `routes_query.py` by adding a
  `<cgpa> IS NOT NULL` where-clause for top/last-N rankings (applies to
  cgpa / sgpa_aggregate / sgpa_per_sem). Genuine bug, fixed at the root, no test
  weakened.
- **`due to` mis-classified as fees-pending** in lifecycle retrieval → fixed with
  `\bdue\b(?! to)`.
- **Lifecycle test tie-break:** `test_regression_generated._rank` now orders by
  `CGPA <dir>, s.usn ASC` to match the engine's documented deterministic
  tie-break (surfaced when the dataset grew to 298 students).

## Evidence (verified this session)

| Check | Result |
|---|---|
| Full backend suite | `python -m unittest discover -s tests` → **Ran 164 tests … OK** (144 → +20 Spec B) |
| New Spec B tests | `LifecycleNlRecordTests`, `LifecycleNlAuthorizationTests`, `LifecycleNlRetrievalTests`, `LifecycleMultilingualRecordTests`, `LifecycleTransitionTests` → **all OK** |
| Live HTTP end-to-end | preview `/nl/record`=200 `confirm`; `/nl/confirm`=200 committed; `/list?reason_category=medical`=200 correct; `/export?fmt=csv`=200 (header + `Reason Category`); `/export?fmt=pdf`=200 `%PDF-` |
| Frontend build | `npm run build` → 2243 modules, **built successfully** |
| Migration idempotency | all lifecycle DDL `IF NOT EXISTS` / `_add_col_if_missing` → re-runnable |
| Test-data hygiene | teardown removes only `9ZZLC*` rows; post-run query → **0 leaked synthetic students/events/rules**, production `students` count unchanged (298) |

## Honest remaining limitations (by design, not defects)

- Preview/confirm requires an authorized Admin (Staff may only preview); nothing
  is saved on `select_student` / `clarify` / `no_record`.
- Eligibility stays conservative: `vtu_scheme_rules` holds 0 verified rules in
  production, so readmission always needs manual review — the system never
  auto-approves or guarantees eligibility.
- Kannada-Unicode record commands depend on the shared translation +
  `normalize_query` pipeline; the multilingual record test asserts equivalence
  across EN / broken-English / Roman-Kannada / mixed without a network
  dependency, and the live HTTP path exercises the English command.

## Self-test prompt catalog (11 categories, 110 commands)

A session-only harness (`backend/_selftest_prompts.py`, cleaned up after this
report) drove ~100 natural-language prompts through the live `/api/query/generate`
+ execute + export + lifecycle endpoints, compared each result against independent
MySQL truth, and honoured the permission model. Test rows are the `9ZZ*` synthetics
created in `seed()` and removed in `cleanup()`; no production record is mutated by
insert/update/delete/restore commands.

**Testing rule applied:** *"Compare every result against the actual MySQL records.
A command should be marked as passed only when the result is correct and the
operation respects the configured permissions."* Commands whose feature is not
implemented (or that require an isolated test DB the policy forbids against prod)
are recorded as **PENDING** rather than assumed to work.

Final tally (2026-10-10, after the fixes listed below): **88 PASS / 0 FAIL /
0 CHECK / 22 PENDING** across 110 commands. Python test suite: **172 tests OK**.

| # | Category | PASS / total | PENDING |
|---|---|---:|---:|
| 1 | Basic Search | 8 / 8 | 0 |
| 2 | Academic Performance | 9 / 10 | 1 (scalar avg-SGPA-per-semester not supported) |
| 3 | Discontinued Management | 11 / 12 | 1 (no dedicated `attendance` reason_category; falls back to `disciplinary`) |
| 4 | Personal + Academic | 4 / 8 | 4 (possessive first-name lookup + cross-file / personal-vs-academic split) |
| 5 | File Upload / Validation | 6 / 12 | 6 (cross-file / refresh / diff / validate-all endpoints absent) |
| 6 | NL Understanding | 14 / 14 | 0 |
| 7 | Admin / Staff Permissions | 8 / 9 | 1 (NL "add student" not deterministic) |
| 8 | Backup / Undo / Recovery | 5 / 10 | 5 (restore / pre-post recovery require isolated test DB) |
| 9 | Reports / Exports | 9 / 9 | 0 |
| 10 | Voice Query | 8 / 8 | 0 |
| 11 | Error Handling / Safety | 6 / 10 | 4 (upload-corruption / duplicate / empty-file require isolated test DB) |

### Root-cause fixes validated by the self-test (with committed regression tests)

Each fix below is covered by a `unittest` test in
`backend/tests/test_query_security_validator.py`; the full 172-test suite passes.

1. **Filter-less COUNT "in the database/system"** — generic-noun skip on
   `location_match` + explicit unfiltered `SELECT COUNT(*)` short-circuit;
   previously the LLM built `WHERE location LIKE '%the database%'` and answered 0.
2. **Deterministic top-N ranking (`1=1` neutral predicate)** — "top 5 by CGPA"
   no longer falls through to the LLM (which mis-parsed "top" as a student name);
   ORDER BY / LIMIT / NULL-CGPA exclusion all apply.
3. **Spelled-number ranking** — `_detect_rank_limit` covers both "top 5" and
   "the five students with the highest CGPA"; previously the spelled form
   bypassed all three `\d+` ranking regexes and returned 270 unsorted rows.
   ("maximum / minimum" are intentionally *not* ranking keywords — they are
   threshold operators handled by the CGPA/SGPA matrix.)
4. **Possessive-pronoun filter (`could not map: their` 400)** — added `their`,
   `his`, `her`, `its`, `our`, `your`, `my`, `them` to `known_terms`.
5. **PRESENT row-verify crash on `blood_group` and `current_sem`** — the
   `_row_satisfies_filter_ast` branches were missing the PRESENT operator, so
   `actual in expected` raised `TypeError: 'NoneType' is not iterable` and
   `int(float(None))` raised on semester; both now short-circuit correctly and
   the 500 "results did not satisfy every requested filter" is gone.
6. **Spelled-word semester numbers (`_detect_target_semester` Pattern 6)** —
   "semester three" / "sem fifth" resolve via `_ORDINAL_WORD_MAP`; previously
   these matched 0 rows and the query silently fell through.
7. **Plural partial-name list (`students named Rahul`)** — new regex handler
   emits `name LIKE '%rahul%'`; previously the LLM produced exact `name = 'Rahul'`
   and returned 0.
8. **Update-target descriptor / article stripping** — `_clean_update_target`
   drops the glued `"Student"` descriptor that produced 404 `USN STUDENT…`;
   `_extract_target_and_field` strips a leading article so "the address" resolves
   to column `address`.
9. **Father/mother-name projection is not a filter** — the `parent_pattern`
   lazy `.+?` captured the bare comma from "show the name, usn, father name, and
   cgpa of all students" and produced `father_name = ','` → 0 rows. Values with
   no letter, or a leading filler preposition ("of ravi"), are now skipped so the
   projection registry takes over. Real value filters (`whose father name is
   Rudrappa`, `without father name`) still build correctly.

`_CACHE_VERSION` bumped to
`selected-columns-v7-spelled-ranking-and-father-projection` so stale cached SQL
plans are not reused across the semantic change.

### PENDING items — why (policy or capability, not defects)

- **Restore / backup-over-production (5 commands, cat 8)** — the Testing Rule
  mandates an isolated test DB for insert/update/delete/restore; the deployed
  environment is production MySQL with 298 real students. Running a restore here
  is prohibited by the same rule. Backup *creation*, verification, and Undo for
  controlled single-row deletions all PASS.
- **Upload corruption / duplicate-USN / empty-file (4 commands, cat 11)** —
  same reason; a corrupt upload test would contaminate production unless run
  against an isolated DB.
- **Cross-file join / personal-vs-academic split (3 commands, cat 4)** — the
  current schema stores personal + academic columns on one `students` row plus a
  separate `marks` table; there is no distinct "personal file" vs "academic file"
  concept after import. Combining "which personal record has no matching academic
  record across two files" is a pre-import question the current architecture
  answers only inside the import pipeline, not through `/api/query/generate`.
- **Uploaded-file refresh / diff / validate-all (4 commands, cat 5)** — no
  dedicated endpoint exposes "compare latest file vs DB" or "bulk re-validate
  uploaded file". The NL fallback returns a truthful but non-file-scoped SELECT.
- **Scalar average SGPA by semester (cat 2 #9)** — the engine projects per-
  student SGPA; a scalar aggregate across a semester cohort isn't routed by the
  deterministic builder. Falls through to the LLM which returns rows instead of
  a scalar.
- **Finer-grained lifecycle reason categories (cat 3 #8)** — `attendance shortage`
  currently maps to the existing `disciplinary` category. A dedicated
  `attendance` enum value would need product sign-off, not a code-only change.
- **Possessive first-name CGPA lookup (cat 4 #2)** — `Find Rahul's CGPA.` uses a
  `<Name>'s <field>` possessive shape not yet handled by the deterministic name
  list; the LLM fallback is non-deterministic. Would need a possessive-name
  parser with regression tests against first-name ambiguity.
- **NL "Add student" (cat 7 #1)** — deterministic builder returns `op=None` for
  "Add a test student with USN X named Y". Existing structured-add endpoint
  works; the NL→INSERT path is out of scope.

## Provisional USN for name-only (no-USN) uploads

Feature: a student file that carries names but **no USN column** no longer
rejects every row. On `POST /files/update-db/{filename}` the import assigns each
such student a **temporary VTU-format USN** derived from the batch year in the
filename and gives serials in **ascending name order**.

- `2026 batch.xlsx` (45 name-only rows) → **was** `0 valid / 45 invalid`;
  **now** `45 valid`, temp USNs `4HG26CS001` (AJITH M S) … `4HG26CS045`, each
  derived to Regular / admission batch 2026 / semester 1 via the existing
  `parse_usn_full`. No production row was written during verification (the
  check used a read-only cursor over in-memory records).
- Format `<degree><college><yy><branch><NNN>`; college prefix + branch are taken
  from the file when evident, else the dominant scheme already in `students`,
  else the default `4HG`/`CS`. Batch year from a `20YY` token in the filename;
  a name-only file with no year token is left INVALID with an explicit reason
  (no placeholder USN is invented, and a null-placeholder name like "None" is
  never given one).
- Serials skip any already present in the DB or used by real USNs in the same
  file, so a generated USN never collides with an existing student.
- New idempotent additive column `students.usn_provisional` (TINYINT default 0)
  marks temporary USNs so staff can later swap in the real college USN; the
  import response carries `provisional_usns` + `provisional_count`, and the
  frontend surfaces the count with a "replace with real USNs later" note.

Evidence: `backend/tests/test_provisional_usn.py` — 13 tests (pure allocation /
sort / skip / branch-map / batch-year logic against an in-memory FakeCursor, so
expected values are computed independently; plus one DB integration that inserts
a single synthetic `9ZZ26CS777` student, asserts the persisted
`usn_provisional=1`, and deletes exactly that row). Full suite:
**185 tests OK**. A pre-existing latent mismatch in
`test_distance_backlog_queries.test_backlog_list_projects_academic_and_subject`
was corrected: the truth query now inner-joins `students` (a *student* listing
must exclude the 97 historical orphan backlog rows whose USN no longer resolves
to a student), matching the engine's correct `INNER JOIN students` behaviour.

## Category-scoped dashboard reports

Feature: dashboard reports are now built **per category and per scope** instead
of always dumping every section for every student. Root cause of the old
over-inclusion: `report_service.build_report_model` unconditionally fetched and
rendered Personal + Academic + Fees + Backlogs + Lifecycle for every student in
every format, and the frontend POSTed the whole result set with no category or
scope information.

- **New shared model** `report_service.build_table_report_model(rows, user,
  category)` for five table categories:
  - `student_list` — uses the **displayed rows verbatim** (the query engine
    just computed them live, incl. derived values like current semester, and
    they are already role-masked). Re-reading flat cache columns here showed a
    real bug (Semester 0 vs the dashboard's 7) — displayed data is the source
    of truth for a list report, so it is never "refreshed" away.
  - `academic` — one row per (student, semester) with SGPA + cumulative CGPA
    from `marks` (window `AVG(sgpa)`), refreshed from current MySQL.
  - `personal` — name/DOB/address + authorized fields; Aadhaar/phone/email
    masked server-side by role via `mask_for_role`.
  - `fees` — per-student Total Paid / Total Pending / overall status
    (normalized via `normalize_fee_status`); totals stay **blank** when stored
    amounts are not parseable numbers — never invented.
  - `discontinued` — students whose lifecycle status is in
    `lifecycle.DISCONTINUED_STATUSES`, with discontinuation date, reason,
    reason category, last-enrolled semester, document ref; notes explain
    exclusions/empties.
  - `individual` — full detail of **exactly one** student (reuse of the
    legacy `build_report_model` + branded PDF); 2+ students → HTTP 400.
- **New endpoints** `POST /api/export/report` and
  `POST /api/export/report/preview` (routes_export.py). Formats: PDF via
  `_NumberedCanvas` ("Page X of N" footers, Paragraph cells + proportional
  widths so tables never cut off), Excel (dark header row, `auto_filter`,
  frozen header, sensible widths, numeric amount coercion), CSV (selected
  records + selected columns ONLY, utf-8-sig), Print HTML (A4 `@page`,
  repeating table header, no row splitting across pages). Legacy
  `/export/pdf|excel|csv|json|print` endpoints are untouched (pinned by
  `test_export_verification.py`).
- **Frontend**: single clear **Generate Report** button on the dashboard
  results (replacing the four quick-export buttons per the simplicity
  requirement) opens `ReportModal.jsx`: plain-language category cards, scope
  choice (current page / selected students / all matching results — same
  filter and sorting), format, live preview from the preview endpoint, then
  download. Result tables gained row checkboxes (select-page / select-row)
  feeding the selected-students scope; selection persists across modal
  open/close and clears on a new query.

Evidence: `backend/tests/test_report_categories.py` — 17 tests comparing each
category model against independently computed DB truth (synthetic `9ZZRP…`
rows only, removed in teardown) and each format's generated bytes (CSV column
scoping + no Aadhaar leakage for Staff, Excel autofilter/freeze/widths, PDF
`Page 1 of`, individual-route guards). Full suite: **204 tests OK**. Live HTTP
verification of all categories × formats, frontend production build, and
browser end-to-end: preview matches the dashboard (Sem 7 fix), selected-students
scope reports exactly the ticked rows, blank fee amounts render as "—", the
individual guard shows "Select exactly one student…" with 2 ticked, and an
individual PDF downloads with 200 for exactly 1 ticked student.

Honest notes: the real DB currently has **0 discontinued students** (the
category is proven with synthetic rows and shows an explanatory note when
empty); many real fee rows carry unparseable text amounts, so totals are blank
and status comes from the normalized status only; report content is English.

---

## Phase 5 — Intent-Based Smart Search Using Actual File Headings

Goal: let non-technical staff ask in plain English / Kannada / Romanized
Kannada and get correct, permission-respecting results that use the **real**
MySQL columns and the **actual uploaded file headings**, not hardcoded column
names or canned commands. Existing query / upload / auth / undo / language
systems were preserved and extended, not redesigned.

### New reusable layer — `backend/intent_fields.py`
- Reads the **live** schema at runtime: real `students` columns via
  `information_schema` and uploaded headings stored in `dynamic_data` /
  `field_registry` (cached per process, `invalidate_cache()` after a new
  import). It therefore never *assumes* a field exists — it only resolves
  against columns/keys that are actually present, so a brand-new heading
  becomes searchable with no code change (spec §3 "updates when new files add
  fields", §5 "confirm field exists").
- Token-based synonym matching tolerant of typos, wording order, plurals and
  possessives, and covering **English + Kannada script + Romanized Kannada**
  (ತಾಯಿ/tayi, ತಂದೆ/thande, ಅಭಿವರ್ಧಕ/abhibhataka, ದೂರವಾಣಿ/mahati).
- `resolve_contact(subject)` implements the spec §2 **fallback rule** with an
  ordered chain and **honest labeling**: a mother/father-specific number is
  preferred when present; otherwise the general parent/guardian contact is used
  and labeled **"Parent Contact Number"** (never passed off as the mother's),
  and when nothing suitable exists it returns an explanation instead of
  inventing rows. `field_sql()` refuses any identifier that isn't a real column
  or registered dynamic key (no SQL built from untrusted text).

### Wiring into the deterministic engine — `backend/routes_query.py`
- A bare "give me the `<subject>` contact numbers" request is answered through
  the resolver and projected with the honest alias. `_is_bare_contact_listing`
  gates it so it **never hijacks** absence queries ("without/missing … contact"
  stays a `IS NULL` missing-value query) or multi-condition queries ("rural CS
  … 7th sem … O+ … without emergency contact" keeps every filter) — both
  previously regressed and now pass.
- `_enforce_specific_select` is told (via an `intent_contact` flag) to leave the
  resolver's projection intact. Without this, the generic "phone" narrowing
  silently replaced `parents_phone AS parent_contact_number` with the student's
  own `phone` — showing the wrong number under a "Parent Contact" label. Fixed
  and verified live.
- Parent **occupation** routing (keyword *and* copula forms, singular/plural/
  possessive) resolves against `mother_occupation`/`father_occupation` and is
  guarded so it never matches on a parent **name** ("Father's Name" ≠ "Father's
  Occupation"). The `could not map` guard whitelists the resolver's known terms.
- The location search now reads/projects `taluk` (spec example "students from
  Ajjampura").

### Column display + explanation
- `_filter_by_intent` keeps the resolver-labeled contact column (matched on
  `phone|contact|mobile|mahati`) so the narrow-scope filter never strips the
  requested answer. `generate`/no-match responses surface the resolver's
  `message`. Frontend (`Dashboard.jsx`) renders it as an amber notice banner and
  shows the alias header as "parent contact number".

### Permissions — `backend/report_service.py`
- `mask_for_role` now masks by **pattern** (`phone|mobile|contact|mahati|aadhar`)
  for non-Admin, not just the fixed field list, so a resolver-labeled contact
  column (`parent_contact_number`, an uploaded heading alias, …) is masked in a
  Staff report too (spec §5 "respect the logged-in user's permissions").

### Tests — `backend/tests/test_intent_field_mapping.py` (29 new)
Synthetic heading-variation mapping (many headings → one canonical field;
unknown headings pass through, never guessed), multilingual + possessive/plural
intent detection, resolver fallback chains driven by a **controlled** live-schema
snapshot (mother-specific preferred when present, general-parent fallback
honestly labeled, clear "unavailable" message, new heading auto-becomes
searchable without breaking others, unsafe identifiers rejected), end-to-end
routing of all 8 spec example queries, the no-hijack guards, and Staff vs Admin
contact masking. No production rows are written; expected answers are computed
from schema/heading logic, not from the parser under test.

Evidence: full suite **233 tests OK**. Live MySQL verification through the HTTP
endpoint (`/api/query/generate`) on a freshly-loaded server for all 8 spec
examples plus the two guard cases: mother-phone → `parent_contact_number`
(value = the real parents' number, with the fallback notice); parents'-contact →
`parent_contact_number`; father-is-farmer → `father_occupation` (88 rows);
mothers-are-teachers → `mother_occupation` (2 rows); Ajjampura → matches taluk
(3 rows); O positive → `blood_group` (31 rows); discontinued-for-financial →
lifecycle route (correctly 0, DB has none); highest-CGPA-3rd-sem → `cgpa` from
the marks table (44 rows); "without emergency contact" → `IS NULL` missing list
(148 rows); the compound rural/CS/7th/O+/lateral/without-emergency query → 1 row
with **every** filter preserved.

Honest notes:
- **Restart the running backend.** `main.py` runs uvicorn with `reload=True`,
  but the long-lived `:8000` process was serving pre-Phase-5 code (its results
  differed from the reloaded `:8001`). The changes only take effect after the
  server process restarts and imports the new modules.
- Query #7 (discontinued because of financial problems) returns **0 rows**
  because the current DB has no financial-discontinuation lifecycle records; the
  intent is routed correctly, the number just isn't in the data.
- The DB currently has no mother-specific phone column, so a mother-phone
  request shows the general **Parent Contact Number** with an explanatory notice
  (this is the intended, honest §2 behavior, not a failure).
- Kannada-script *file headings* rely on the importer's existing
  translation/normalization; the search-query path handles Kannada/Romanized
  directly in `intent_fields`. Browser click-through against the stale `:8000`
  server was not performed for this reason; verification is API + DB + unit-test
  evidence.

## Phase 6 — Professional Reports + "Cleared backlog keeps showing" bug

Two reported problems, fixed against the real MySQL data and the running code.

### Bug: a cleared backlog still appeared after updating
Root cause: the natural-language update engine writes the free-text
`students.backlogs` column directly but never touched the structured
`student_backlogs` table, and both the report model and the `/students/{usn}/backlogs`
endpoint read only the table. So `4HG23CS032` had `students.backlogs='cleared'`
while its `student_backlogs` row (Cybersecurity) was still `cleared=0` and kept
showing up.

Fixes (same architecture, no new subsystem):
- `routes_query._sync_backlogs_from_column` runs **inside the update
  transaction** (so it is covered by the existing undo snapshot). When a student
  update touches `backlogs`: a no-backlog text (`cleared`/`none`/`0`/…) marks the
  student's table rows `cleared=1`; a descriptive text replaces the rows via the
  importer's own `_upsert_backlogs`; an empty text is left untouched (a blanked
  column never silently erases real arrears).
- The report model and the backlogs endpoint now honour **both** signals: the
  structured `cleared` flag *and* the `students.backlogs` text
  (`report_service._text_is_no_backlog`), so the already-inconsistent existing
  student stops showing a backlog immediately, without needing another edit.

### Reports were "messed up" (duplicate fees, dash placeholders, blank page)
- **Fees no longer duplicated.** A single shared `_fee_block` builder drives PDF,
  print-HTML, Excel and CSV: structured fee rows are authoritative and the
  workbook (dynamic) fields are used only as a fallback when there are no
  structured records — the old "Additional fee fields (from uploaded workbook)"
  second table is gone.
- **Unavailable data is omitted, not shown as blank/`—`.** In the individual /
  detail report a section (Fees / Backlogs / Academic / Lifecycle) and any column
  inside it (Amount Paid, Remaining, SGPA, CGPA) is dropped when it carries no
  value, and `_lifecycle_fields` no longer emits `—` placeholders. `_cell_text`
  returns an empty cell instead of `—`.
- **Page flow.** Each short section is wrapped in `KeepTogether` so a header is
  never orphaned from its table; a long many-row fee table is allowed to flow
  across pages (with a repeating column header) instead of being pushed whole
  onto a fresh page, which is what left a near-empty page behind.
- Category list reports (Fees / Personal / Academic) keep the tested "honest
  blanks, never invent" invariant: an absent value is a genuinely blank cell, no
  `—` — dropping whole columns there would have broken the existing
  `test_report_categories` guards, so that behaviour was deliberately kept.

### Tests — `backend/tests/test_backlog_clear_sync.py` (6 new)
Synthetic `9ZZBL…` rows only (deleted in teardown, zero-leakage asserted).
Expected values computed by hand from the seeded rows, never from the code under
test: the report omits a backlog whose text says "cleared"; a genuine active
backlog is still shown; the sync flags rows cleared for no-backlog text, replaces
rows for descriptive text, leaves rows untouched for empty text, and ignores an
unknown USN.

Evidence: full suite **239 tests OK**. Rendered PDFs were extracted with
`pdftotext` and confirmed to contain no `—`, no "No … records." empty-section
notes, and no duplicate fee table; the previously stuck `4HG23CS032` report no
longer shows its cleared backlog.

Honest notes:
- **Restart the running backend** to load the new export/query/report code (the
  long-lived `:8000` process serves stale modules even under `reload=True`).
- For a student whose table rows are already out of sync, the report now hides
  the backlog via the text signal; the underlying rows are corrected the next
  time `backlogs` is updated through the engine. No bulk/production mutation was
  run to force old rows in line.

---

# Phase 7 adversarial suite + two engine bugs found & fixed (this session)

New test modules (all run against the real `student_db`, synthetic `9ZZ…` rows
only, teardown-asserted zero leakage):

- `tests/test_security_authz.py` (15) — see Phase 5 above.
- `tests/test_adversarial_search.py` (11) — language/search torture battery,
  false-positive guards, report-scope regression.
- `tests/test_integrity_guards.py` (4) — identity immutability + injection.

## Two real defects discovered by the torture battery (root-caused & fixed)

1. **Spelled-out ordinals mis-routed as a location.** "students in fifth
   semester" (and third/fourth/…) was classified `location_search` and the
   ordinal word "fifth" was extracted as a *place name*, producing a bogus second
   `LIKE '%fifth%'` filter → **0 rows** instead of the correct 5th-semester set.
   Numeric "5th" only worked by accident (the place-capture regex requires a
   leading letter). Root cause in `routes_query.py` `build_deterministic_student_query`:
   the `from|in|at|near` location lookahead blocked "first/last/best…" but not
   second…tenth, and the academic-phrase skip guard only caught "5th sem".
   Fix: added the ordinal words to the location lookahead negative-set, and
   extended `_is_sem_phrase` to treat a bare/attached ordinal word as academic
   (never a place). Verified: "show students in fifth semester" → 64 rows ==
   authoritative; genuine place/taluk/district filters unaffected.

2. **Misleading 403 "Invalid student data." on a valid read.** An unusual
   occupation phrasing ("farmer family students") that the deterministic layer
   cannot map fell to the LLM/rule fallback, produced an unmappable SELECT, and
   the client got **403 "Invalid student data."** — blaming the user's records
   for what is a query-understanding failure (authorization is enforced by
   `require_roles`/`get_current_user`, *not* by this message). Per Phase 2C/§8
   (clarify, never mislabel valid input), `routes_query.py` now returns a
   **400 clarification** with a plain-language example for non-delete
   validation failures. The delete-specific 403 branches are unchanged, so no
   access control is weakened.

## What the battery confirms (robustness)

Across case flips, extra/missing spaces, punctuation, misspellings ("lis rural
studentz", "5th semesterr"), synonyms ("tally"), and spelled-out ordinals, every
tested intent returns exactly the authoritative MySQL set. Glued compounds
("ruralstudent", "fifthsemester", "showdropoutstudents") are an acknowledged,
honest **pending** normalisation gap: they now return a safe no-match (never
fabricated or full-table rows) rather than a false answer.

Suite total after these changes: **269 tests OK**.

---

# Phase 9 — Deployment readiness assessment (this session)

## Change made for a production launch path
- `main.py` `__main__`: the dev server no longer hard-codes `reload=True`. Host,
  port and reload are now env-driven (`APP_HOST`, `APP_PORT`, `DEV_RELOAD`), with
  reload defaulting to **on** so local development is unchanged, and
  `DEV_RELOAD=0` giving a clean non-reloading start. (This also addresses the
  known stale-`:8000` gotcha: a production process started with `DEV_RELOAD=0`
  imports fresh modules and cannot serve stale code.)

## Readiness checklist
- **Reproducible build** — `backend/requirements.txt` present; frontend is a Vite
  app (`package.json`). *Recommend pinning* exact versions (`pip freeze`) before a
  production image, and building the frontend (`npm ci && npm run build`).
- **Configuration / secrets** — `.env.example` is thorough and correctly says
  never commit `.env`. Secrets (MYSQL_PASSWORD, SECRET_KEY, GEMINI_API_KEY,
  SMTP) are read only from env via `config.py`; none are hard-coded. A real
  `.env` exists locally — **must not** be shipped. Auth fails closed with HTTP
  503 if `SECRET_KEY` is unset (`_configured_jwt_secret`).
- **Health check** — `/api/monitor/health` (DB ping) plus `/` liveness JSON.
  `/api/monitor/health` currently requires a JWT; an *unauthenticated* liveness
  (the `/` route) is what an orchestrator should probe.
- **Structured errors / audit** — central `write_audit_log` (actor, role, action,
  target, success, error) used across query/export/files/undo/backup/lifecycle;
  `security_logs` records blocked attempts. No PII or credentials in logs
  (Phase 5 confirmed).
- **Authorization** — role gates on every write/route; destructive ops require
  confirmation tokens; delete is Admin-only and unbounded delete permanently
  blocked. Formula-injection and path-traversal fixed (Phase 5).
- **Backups / undo / restore** — mysqldump-based, password-scrubbed errors,
  retention settings, scheduled auto-backup (APScheduler). Verified in the live
  suite (backup creation + restore into a target DB pass).

## Open items (recommend, not blocking a controlled pilot)
- **CORS** `allow_origins=["*"]` with `allow_credentials=False`. Because auth is
  a Bearer header (not cookies), wildcard is low-risk, but tighten to the
  configured `FRONTEND_URL` origin list for a real deployment.
- **Token lifetime** default `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1000` (~16h).
  Acceptable for a staff desktop app; consider a refresh flow or shorter TTL.
- **Least-privilege DB account** — `MYSQL_USER` defaults to `root`. Create a
  scoped account (SELECT/INSERT/UPDATE/DELETE on `student_db` only; no DROP) for
  the app; keep admin creds for backups out of the app env.
- **Dead / stale tree** (see Phase 1 register) — `sync_students.py`, the 0-byte
  routers, `app.db`, PostgreSQL-flavoured `schema_metadata.json`, the duplicate
  root frontend tree, and the destructive one-off CLIs should be removed from the
  shipped artifact. **Not deleted**: repo is not under git, so these need your
  explicit go-ahead. Until then, do not ship them.
- **LLM dependency** — the deterministic engine answers most queries without the
  LLM; when it falls back and the LLM is unavailable it returns a clarification
  (503/400), never fabricated data. Rate-limit (429) behaviour degrades to
  deterministic paths where available.

## Final classification
**READY FOR CONTROLLED PILOT.** The core search experience, role-based data
integrity, report scoping, backups/undo, and the security surface (formula
injection, path traversal, JWT/role enforcement, destructive-query guards) are
implemented, integrated with the existing architecture, and covered by **269
passing tests** run against the real MySQL `student_db`. It is **not yet**
"ready for production review" until the open items above are closed — chiefly
pinning dependencies, a least-privilege DB account, tightening CORS, a decision
on token lifetime, and removing the dead/destructive files from the shipped
artifact. No production rows were mutated or deleted by this work; all mutation
tests use synthetic `9ZZ…` records with asserted teardown.
