# CookHero Backend Review Playbook

This playbook defines how ClaudeCode collaboration runs for backend review, debug, and hotfixes.

## 1. Ownership and Scope

- Claude focuses on implementation and lands local working-tree changes.
- Reviewer focuses on backend quality gates, blocker triage, and fixes.
- Default backend scope:
  - `app/**`
  - `scripts/**`
  - `config.yml`
  - `requirements.txt`
  - `deployments/init-scripts/**`
- Frontend changes are reviewed only when backend API contracts are impacted.

## 2. Review Trigger

Run a review cycle for:

- Existing dirty working tree baseline.
- Every subsequent Claude delta.

## 3. Severity Policy

- `P0 Blocker`: security bypass, data corruption/loss, critical runtime breakage.
- `P1 High`: major behavior regression, broken core path, production instability risk.
- `P2 Medium`: non-blocking defect, observability/testing gap, maintainability debt.
- `P3 Low`: style/readability issues.

Default policy:

- For `P0`/`P1`, patch first and report immediately.
- For `P2`/`P3`, report with suggested order and optional patch.

## 4. Standard Review Cycle

1. Collect delta:
   - `git diff --name-only`
   - `git diff --stat`
2. Filter backend scope and inspect patch by module order:
   - `database/`
   - `services/`
   - `api/v1/endpoints/`
   - `rag/`
3. Run semantic checks:
   - `python -m compileall app scripts`
4. Run targeted reproductions for suspicious paths.
5. Apply minimal hotfixes for blocker issues.
6. Run focused regression checks for patched paths.
7. Produce structured findings report.

## 5. Required Finding Format

Each finding must include:

- `Severity`
- `Location` (`path:line`)
- `Symptom`
- `Root Cause`
- `Fix`
- `Regression Risk`

## 6. API/Schema Guardrails

When changes touch endpoint files or response models:

- Verify request/response compatibility.
- Verify status-code semantics.
- List impacted frontend callers.

When changes touch database models:

- Explicitly state migration requirement.
- Explicitly state historical data compatibility risk.

## 7. Python Runtime Baseline

- Runtime compatibility baseline for review: Python `3.9`.
- Keep a note if change depends on `3.12+` behavior.

## 8. Output Artifacts

Store each review under:

- `artifacts/reviews/<timestamp>/`

Recommended files:

- `diff_name_only.txt`
- `diff_stat.txt`
- `backend_files.txt`
- `backend_diff.patch`
- `compileall.log`
- `pytest.log` (or a skip note)
- `review_report.md`
