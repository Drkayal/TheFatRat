#!/usr/bin/env bash
set -euo pipefail
BASE="/workspace"
RETAIN_DAYS="${RETAIN_DAYS:-7}"

# Purge old tasks
find "$BASE/tasks" -maxdepth 1 -type d -regex ".*/[0-9]{8}" | while read -r daydir; do
  day=$(basename "$daydir")
  # Compare dates
  if [[ "$day" =~ ^[0-9]{8}$ ]]; then
    if [[ $(date -d "$day +$RETAIN_DAYS days" +%s) -lt $(date +%s) ]]; then
      echo "Removing old tasks day=$day"
      rm -rf "$daydir" || true
    fi
  fi
done

# Rotate audit log at 100MB
AUD="$BASE/logs/audit.jsonl"
if [ -f "$AUD" ]; then
  sz=$(stat -c%s "$AUD")
  if [ "$sz" -gt $((100*1024*1024)) ]; then
    ts=$(date +%Y%m%d%H%M%S)
    mv "$AUD" "$BASE/logs/audit-$ts.jsonl" || true
    : > "$AUD"
  fi
fi

echo "Cleanup completed"