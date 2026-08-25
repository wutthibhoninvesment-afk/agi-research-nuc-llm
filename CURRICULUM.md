# AGI Software-Engineering Research Program (Fable 5 via Claude Code)

**Mission:** become an autonomous software-engineering research system. Deep-learn
(1) agent harness writing, (2) SKILL.md authoring, (3) novel programming-language
design & implementation — and keep every result as durable, reusable skills.

**Budget policy:** consume the Claude Max weekly quota deliberately. Pace against
the 5-hour rolling limit (sleep until reset), stop only when the WEEKLY limit is
reached, then write the final report.

## Tracks (rotation mod 6: 1→harness(A), 2→language(C), 3→skills(B),
## 4→NUC-integration(E), 5→SWE-loop(D), 0→language(C))

### A. Harness engineering (`harness/`)
Build a real, runnable agent harness in Python (stdlib-first):
tool loop, tool registry (file/bash/search), observation truncation, scratchpad
memory file, retry/backoff, trace logging, evaluation harness with MockLLM so the
whole thing is testable offline. Every round must add a capability AND tests.

### B. Skill authoring (`skills/`)
Study Anthropic's Agent Skills docs + best-in-class skills on this machine
(`~/.hermes/skills/`, `~/.claude/plugins/`), then author new SKILL.md files and
upgrade existing ones. Output format: YAML frontmatter (name, description) +
trigger conditions + numbered steps + pitfalls + verification.

### C. Language design (`languages/<lang>/`)
Design and implement a genuinely novel programming language end-to-end:
spec → lexer → parser → AST → evaluator → stdlib → tests. Document ≥3 design
decisions that differ from mainstream languages. All examples must run:
`python3 run.py examples/<name>.lang`. Later rounds: advanced features
(effect system, structural types, AI-native primitives), self-hosting experiments.

### D. Autonomous SWE (`harness/` + `languages/`)
Use the harness ON our own code: autonomous code review, test generation, bug
finding/fixing against the language implementation. Record metrics (bugs found,
tests added, pass rate) — this is the self-improvement loop.

### E. NUC integration (`state/nuc-missions.md`)
Apply the program's knowledge to the real deployment: pgain-nuc running
Colibri + Qwen3.6-35B-A3B for Hermes Agent. SSH in with
`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.42`, take the first unchecked
mission from state/nuc-missions.md (benchmark harness → prompt budgeting →
KV-reuse analysis → fast lane → task-script DSL). Hard rules in CLAUDE.md:
read-only colibri/hermes sources, never touch port 8001, predictions before
measurements (D-013). This track is where knowledge becomes value.

## Round protocol (every round, enforced by driver prompt)
1. Read `state/research-state.md` (cumulative memory) first.
2. Build real, tested artifacts — no stubs, no TODOs.
3. Write `knowledge/round-NNN-<slug>.md` (dense findings, code snippets, failures).
4. Update `state/research-state.md` (append round entry; keep next-steps current).
5. Create/upgrade `skills/<name>/SKILL.md` whenever a reusable technique emerges.

## Endgame (on weekly limit)
- Driver writes `state/FINAL-REPORT.md`.
- Hermes consolidates: best skills → `~/.hermes/skills/`, languages kept runnable,
  knowledge notes indexed.
