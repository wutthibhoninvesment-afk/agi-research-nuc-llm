# AGI Research Workspace — context for Claude Code

## Model Policy (Updated 2026-08-29, round 333)
**Primary:** `claude-opus-5` — the long-term research driver model. Set by the
operator on 2026-08-29 ~12:22 UTC by editing `run_driver.sh`'s three `--model`
sites directly; `run_driver.sh` re-execs itself every round (round 145's
self-re-exec fix), so the change took effect immediately, on round 333.
**Fallback:** None — Opus 5 handles all tracks.

*Previous policy (2026-08-25 -> 2026-08-29): `claude-sonnet-5`, "waiting for
Fable 5 weekly limit reset ~Sunday 2026-08-30". Superseded — the driver never
went back to Fable 5; do not restore that line from this file's history.*

## Ground rules