#!/bin/sh
# Push finished runs (and, with --models '*', model bundles) to the team's HF dataset repo.
# Skips while a sort.py loop runs so uploads never compete with a live run. Log: /opt/viam/sorter-ali/sync.log
# Installed 2026-11-13 by claude-code/claude-opus-5-5 (op Ali). Remove: crontab -e, delete the sync_cron.sh line.
B=/opt/viam/sorter-ali
if pgrep -f "python3[.0-9]* .*[s]ort[.]py" >/dev/null; then echo "$(date -Is) skip: sort.py running"; exit 0; fi
S=$B/current/sync_data.py; [ -f "$S" ] || S=$B/tools/sync_data.py
export VH_DATA_REPO=aliriz/armfarm04-fastener-runs HF_HUB_DISABLE_PROGRESS_BARS=1
echo "$(date -Is) push via $S $*"
exec flock -n /tmp/vh_sync.lock nice -n 10 $B/.venv/bin/python3.12 "$S" --root $B push "$@"
