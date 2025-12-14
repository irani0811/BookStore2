#!/usr/bin/env bash
set -euo pipefail

# Environment knobs:
#   TEST_LOG_DIR            -> directory for log files (default: <repo>/logs)
#   PYTEST_ARGS             -> extra pytest args (default: verbose run)
#   PYTEST_SKIP_PATTERN     -> pytest -k expression to exclude tests
#   TEST_SUMMARY_LOG_FILE   -> filtered log (coverage table + test case list)
#   TEST_LINES_LOG_FILE     -> detailed per-test lines (default: <summary>-lines.log)

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-$PROJECT_ROOT}"

LOG_DIR="${TEST_LOG_DIR:-"$PROJECT_ROOT/logs"}"
mkdir -p "$LOG_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
base_log_path="$LOG_DIR/test-$timestamp"

SUMMARY_LOG_FILE="${TEST_SUMMARY_LOG_FILE:-"$base_log_path-summary.log"}"
TEST_LINES_FILE="${TEST_LINES_LOG_FILE:-"$base_log_path-lines.log"}"

mkdir -p "$(dirname "$SUMMARY_LOG_FILE")"
mkdir -p "$(dirname "$TEST_LINES_FILE")"
touch "$SUMMARY_LOG_FILE" "$TEST_LINES_FILE"
: > "$SUMMARY_LOG_FILE"
: > "$TEST_LINES_FILE"

exec > >(tee /dev/null) 2>&1

log_line() {
    printf "%s\n" "$1"
}

log_line "Summary log   : $SUMMARY_LOG_FILE"
log_line "Test lines log: $TEST_LINES_FILE"
log_line "Test workspace: $PROJECT_ROOT"

log_step() {
    local label="$1"
    shift
    printf "➡ %s..." "$label"
    if "$@"; then
        echo "done"
    else
        local status=$?
        echo "FAILED (status=$status)"
        exit $status
    fi
}

SKIP_PATTERN=${PYTEST_SKIP_PATTERN:-"not test_search_global and not test_bench"}
PYTEST_ARGS=${PYTEST_ARGS:-"-vv -s -rA --maxfail=1 --durations=20 --log-cli-level=INFO"}
IFS=' ' read -r -a PYTEST_ARGS_ARR <<< "$PYTEST_ARGS"
PYTEST_BASE_ARGS=("${PYTEST_ARGS_ARR[@]}" --ignore=fe/data -k "$SKIP_PATTERN")

log_line "Pytest args: ${PYTEST_BASE_ARGS[*]}"

run_pytest_with_stream() {
    local summary_lines_file="$1"
    shift
    python - "$summary_lines_file" "$@" <<'PY'
import os
import re
import subprocess
import sys
from pathlib import Path

summary_lines_path = Path(sys.argv[1])
cmd = sys.argv[2:]

ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

test_line_regex = re.compile(
    r"(?:^|/)(?:fe|be)/test.*::.*\b(PASSED|FAILED|ERROR|SKIPPED|XPASS|XFAIL)\b",
    re.IGNORECASE,
)

def strip_ansi(text: str) -> str:
    return ansi_re.sub("", text)

with summary_lines_path.open("a", encoding="utf-8") as s_log:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    try:
        for raw_line in proc.stdout:
            sys.stdout.write(raw_line)
            sys.stdout.flush()
            if test_line_regex.search(strip_ansi(raw_line)):
                s_log.write(strip_ansi(raw_line))
                if not raw_line.endswith("\n"):
                    s_log.write("\n")
                s_log.flush()
    finally:
        proc.stdout.close()
    exit_code = proc.wait()
sys.exit(exit_code)
PY
}

coverage_cmd=(coverage run --timid --branch --source fe,be --concurrency=thread -m pytest "${PYTEST_BASE_ARGS[@]}")

log_line "➡ Running pytest with coverage..."
run_pytest_with_stream "$TEST_LINES_FILE" "${coverage_cmd[@]}"
pytest_status=$?
if [[ $pytest_status -ne 0 ]]; then
    echo "Pytest failed (see $TEST_LINES_FILE for captured cases)"
    exit $pytest_status
fi
log_step "Combining coverage data" coverage combine

log_line ""
log_line "📊 Coverage summary"
coverage_report_output=$(coverage report)
coverage_status=$?
printf "%s\n" "$coverage_report_output"
if [[ $coverage_status -ne 0 ]]; then
    echo "coverage report failed"
    exit $coverage_status
fi

log_step "Generating coverage HTML" coverage html

{
    echo "==== Coverage Summary ===="
    printf "%s\n" "$coverage_report_output"
    echo
    echo "==== Detailed Test Results ===="
    if [[ -s "$TEST_LINES_FILE" ]]; then
        cat "$TEST_LINES_FILE"
    else
        echo "[no tests captured]"
    fi
} > "$SUMMARY_LOG_FILE"

log_line "Completed. Summary: $SUMMARY_LOG_FILE"
log_line "Detail lines: $TEST_LINES_FILE"
