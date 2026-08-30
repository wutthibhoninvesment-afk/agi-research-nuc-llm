#!/bin/bash
set -u
DEST=state/nuc-swap-watch-r352
LOG="$DEST/poll.log"
mkdir -p "$DEST"
: > "$LOG"
for i in $(seq 1 600); do
  ts=$(date -u +%FT%TZ)
  status=$(ssh -i /home/pgain/.ssh/id_ed25519 -o ConnectTimeout=10 \
    jab@100.78.44.111 "ps -p 2337 -o pid= 2>/dev/null" 2>&1)
  echo "$ts iter=$i status=[$status]" >> "$LOG"
  pid_alive=$(echo "$status" | head -1 | tr -d ' ')
  if [ -z "$pid_alive" ]; then
    echo "$ts process gone, pulling final files" >> "$LOG"
    break
  fi
  sleep 60.0
done
# remote_outdir left UNQUOTED here (deliberately, tag is pre-validated to
# exclude shell metacharacters) so the REMOTE shell tilde-expands it itself;
# shlex.quote()-ing a leading "~/" here would single-quote it and suppress
# that expansion on the remote end (round 100's fast_lane.py bug, same class).
ssh -i /home/pgain/.ssh/id_ed25519 -o ConnectTimeout=10 jab@100.78.44.111 \
  "uptime; ls -la ~/nuc-research | grep r352" >> "$LOG" 2>&1
scp -i /home/pgain/.ssh/id_ed25519 -o ConnectTimeout=10 \
  jab@100.78.44.111:'~/nuc-research/swap-watch-r352-checkpoint.jsonl' \
  "$DEST/swap-watch-r352-checkpoint-final.jsonl" >> "$LOG" 2>&1
scp -i /home/pgain/.ssh/id_ed25519 -o ConnectTimeout=10 \
  jab@100.78.44.111:'~/nuc-research/swap-watch-r352-long.json' \
  "$DEST/swap-watch-r352-long.json" >> "$LOG" 2>&1
echo "PULL_DONE" >> "$LOG"
