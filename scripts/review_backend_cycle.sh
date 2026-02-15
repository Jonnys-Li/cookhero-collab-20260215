#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
OUT_DIR="${1:-artifacts/reviews/$TIMESTAMP}"
mkdir -p "$OUT_DIR"

echo "[review] output directory: $OUT_DIR"

git diff --name-only > "$OUT_DIR/diff_name_only.txt"
git diff --stat > "$OUT_DIR/diff_stat.txt"

grep -E '^(app/|scripts/|config\.yml$|requirements\.txt$|deployments/init-scripts/)' \
  "$OUT_DIR/diff_name_only.txt" > "$OUT_DIR/backend_files.txt" || true

if [[ -s "$OUT_DIR/backend_files.txt" ]]; then
  # shellcheck disable=SC2207
  BACKEND_FILES=($(cat "$OUT_DIR/backend_files.txt"))
  git diff -- "${BACKEND_FILES[@]}" > "$OUT_DIR/backend_diff.patch"
else
  : > "$OUT_DIR/backend_diff.patch"
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
else
  PYTHON_BIN="python"
fi

set +e
PYTHONPYCACHEPREFIX=/tmp/cookhero-pycache "$PYTHON_BIN" -m compileall app scripts \
  > "$OUT_DIR/compileall.log" 2>&1
COMPILE_EXIT=$?

"$PYTHON_BIN" - <<'PY' > "$OUT_DIR/pytest_available.log" 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("pytest") else 1)
PY
PYTEST_AVAILABLE=$?

if [[ $PYTEST_AVAILABLE -eq 0 ]]; then
  "$PYTHON_BIN" -m pytest -q > "$OUT_DIR/pytest.log" 2>&1
  PYTEST_EXIT=$?
else
  echo "pytest is not installed in current environment." > "$OUT_DIR/pytest.log"
  PYTEST_EXIT=127
fi
set -e

{
  echo "# Backend Review Snapshot"
  echo
  echo "- Timestamp: $TIMESTAMP"
  echo "- Output directory: $OUT_DIR"
  echo "- Compile check exit code: $COMPILE_EXIT"
  echo "- Pytest exit code: $PYTEST_EXIT"
  echo
  echo "## Quick Pointers"
  echo
  echo "- Delta list: \`$OUT_DIR/diff_name_only.txt\`"
  echo "- Backend subset: \`$OUT_DIR/backend_files.txt\`"
  echo "- Backend patch: \`$OUT_DIR/backend_diff.patch\`"
  echo "- Compile log: \`$OUT_DIR/compileall.log\`"
  echo "- Test log: \`$OUT_DIR/pytest.log\`"
  echo
  echo "## Findings"
  echo
  echo "Fill this report using docs/templates/BACKEND_REVIEW_REPORT_TEMPLATE.md."
} > "$OUT_DIR/review_report.md"

echo "[review] compile exit: $COMPILE_EXIT"
echo "[review] pytest exit:  $PYTEST_EXIT"
echo "[review] done"
