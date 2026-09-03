# AGI Research Workspace — context for Claude Code

You are operating one ROUND of an autonomous research program. See CURRICULUM.md.

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
1. FIRST read `state/research-state.md`, then the CURRICULUM.md track for your round.
2. Build REAL artifacts that run and pass tests. No stubs, no placeholder comments.
3. Write findings to `knowledge/round-<NNN>-<slug>.md` (NNN zero-padded, next free number).
4. Update `state/research-state.md` — append a round entry, refresh "next steps".
5. When you discover a reusable technique, write/upgrade `skills/<kebab-name>/SKILL.md`
   with YAML frontmatter (`name`, `description`), trigger conditions, numbered steps,
   exact commands, pitfalls, and a verification section.
6. Track rotation (round number mod 6): 1→harness(A), 2→language(C), 3→skills(B),
   4→NUC-integration(E), 5→SWE-loop(D), 0→language(C).
   Track D requires A+C to exist; if missing, do A.
7. If you hit a rate-limit/permission error: write what happened to the round file
   and exit cleanly. Do not retry-loop.

## Track E — NUC integration: HARD RULES
The target machine `pgain-nuc` runs Colibri + Qwen3.6 serving Hermes Agent.
Your job: apply this program's knowledge to make it faster/more usable.

- Connect. Two working paths; `state/nuc-missions.md` is the live record and
  wins if these ever disagree:
  - tailnet (works from any tailnet host, and is what the tooling defaults to):
    `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  - LAN (Mac-adjacent hosts only): `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37`
  Deploy with `scp` over whichever path connected.
- Pick the first unchecked mission in `state/nuc-missions.md`; tick it when done.
- READ-ONLY on the NUC (never edit/delete): `/work/src/colibri*`, `/work/models/`,
  `/work/src/hermes`, `/work/src/solar-nuc`, `/work/notes.md`, all systemd units.
- NEVER send requests to NUC port **8001** (GLM frontier lane — one stray request
  evicts a ~550 s KV cache).
- Allowed write paths on the NUC: `~/nuc-research/**`, `/work/logs/**`, `/tmp/**`.
- Units `qwen36-colibri` / `qwen36-toolproxy` may be restarted ONLY if a mission
  requires it; record every restart in the round file. (Round 100: `qwen36-colibri`
  is a USER unit — `systemctl --user`.)
- Live endpoints on the NUC: `http://127.0.0.1:8000` (engine, OpenAI-compatible,
  NO tools support), `http://127.0.0.1:8080` (tool-proxy, tools supported).
  Both are 127.0.0.1-only: engine calls must run ON the box.
- Banking rule **D-013**: write PREDICTIONS before measuring, then score misses
  honestly. Results go to `/work/logs/<mission>.md` (NUC) AND the round file.
- If SSH fails twice in a row, record the failure and exit cleanly.

## What "done" means for a round
- Tests pass (run them, show output in the round file).
- research-state.md updated.
- knowledge file exists with honest failures included.

---
*Provenance of the two sections above (round 346).* `## Ground rules` and
`## Track E` were present at this repo's initial commit `ee30654` and were
deleted — with 36 other lines — by the `AUTO-COMMIT v4` commit `e376750`,
after which `## Ground rules` stood as a heading with no body for the rest of
the program. Round 345 found the resulting dangling `D-013` (cited 42 times)
but concluded the body "predates this repo's git history" and was
unrecoverable, so it deferred the fix to the operator as authorship. It was
in git the whole time. Round 346 restored both sections from `ee30654`.

Restored VERBATIM: rules 1-7, the read-only list, the port-8001 prohibition,
the allowed write paths, the restart rule, the endpoint list, D-013, the
two-SSH-failures rule, and the "done" section. Round 346 changed exactly four
things, all coordinates rather than rules, each because the repo already
records the correction elsewhere: the connect line now leads with the tailnet
path (`state/nuc-missions.md`, round 154) and gives `192.168.1.37` rather
than the original's `192.168.1.42` (CURRICULUM.md and 1234 references
in-tree); the restart bullet notes round 100's finding that
`qwen36-colibri` is a *user* unit; the endpoint bullet notes both ports are
loopback-only; and the results-path bullet drops "(Mac)", which the NUC-hosted
driver made meaningless. NO rule was added, removed, or reworded.

Keep `D-013` spelled literally in `## Ground rules` or in this section:
`skills/skill-authoring/scripts/xref_check.py` reads this file as the X002
registry, and `--provenance` is what proved the body was recoverable.

## 🔴 CRITICAL MISSION: PRODUCTION FIX (Round ~350 Focus)
**Priority:** HIGH | **Target Model:** Claude Opus-5 (Direct Access)
**Current Issues:**
1. **Fold Logic Regression:** `fold()` returns `Miss` instead of calculated values when using inline lambdas or external functions. Needs deep code inspection in `whence/interp.py`.
2. **Strict Syntax Enforcement:** Parser requires explicit `{}` blocks for all `if/else` branches in v0.19. Document this strictly and consider auto-fixing older scripts.

**Instruction:** When reviewing Round tasks, prioritize debugging the Whence interpreter core over general knowledge generation. Use Opus-5 capability to analyze complex DAG merge failures.



## 🚨 CRITICAL MISSION #476: FOLD BUG FIX (Opus-5 Direct)
**Status:** BLOCKING | **Impact:** Core functionality broken
**Briefing File:** `knowledge/mission-fold-fix-v1.md`

### Problem Summary
`b_fold()` in `whence/interp.py` returns an `Env` object instead of the accumulator value, breaking all aggregation logic.

### Immediate Action Required
1. Read `knowledge/mission-fold-fix-v1.md` for full details
2. Inspect `whence/interp.py` function `b_fold()` around line 2666
3. Fix the closure evaluation to return final value, not Env reference
4. Run `pytest tests/test_folding.py` to verify fix
5. Ensure no regression in existing 800+ unit tests
6. Commit with message: `fix(b_fold): correct Env return to accumulator value`

### Why This Matters
Without this fix, Whence-lang cannot perform list aggregation, totaling, or accumulation operations — a fundamental building block for any production use case.

---
