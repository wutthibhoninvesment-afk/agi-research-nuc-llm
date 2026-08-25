# AGI Research Workspace — context for Claude Code

You are operating one ROUND of an autonomous research program. See CURRICULUM.md.

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

- Connect: `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.42` (key auth works).
  Deploy with `scp -i ~/.ssh/id_ed25519_nuc <file> jab@192.168.1.42:<path>`.
- Pick the first unchecked mission in `state/nuc-missions.md`; tick it when done.
- READ-ONLY on the NUC (never edit/delete): `/work/src/colibri*`, `/work/models/`,
  `/work/src/hermes`, `/work/src/solar-nuc`, `/work/notes.md`, all systemd units.
- NEVER send requests to NUC port **8001** (GLM frontier lane — one stray request
  evicts a ~550 s KV cache).
- Allowed write paths on the NUC: `~/nuc-research/**`, `/work/logs/**`, `/tmp/**`.
- Units `qwen36-colibri` / `qwen36-toolproxy` may be restarted ONLY if a mission
  requires it; record every restart in the round file.
- Live endpoints on the NUC: `http://127.0.0.1:8000` (engine, OpenAI-compatible,
  NO tools support), `http://127.0.0.1:8080` (tool-proxy, tools supported).
- Banking rule D-013: write PREDICTIONS before measuring, then score misses
  honestly. Results go to `/work/logs/<mission>.md` (NUC) AND the round file (Mac).
- If SSH fails twice in a row, record the failure and exit cleanly.

## What "done" means for a round
- Tests pass (run them, show output in the round file).
- research-state.md updated.
- knowledge file exists with honest failures included.
