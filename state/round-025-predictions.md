# Round 25 — predictions BEFORE building (banked 2026-08-24)

Context: harness(A) round. Inheritance audit found round 24 (language, died at
max-turns, unrecorded) left Whence v0.7 (F1 builtin-call inlining / F2
frameless closure calls) green in its OWN suite (449) but breaking 6 harness
SWE tests — the determinism oracle reports same-AST rerun A=['1275','2',...×2]
B=[]. Diagnosis before predicting: `_compile_builtin_call` caches a closure on
the shared AST that captures the COMPILING interpreter, and
`_install_builtins` makes fresh `Builtin`/fn objects per interpreter so the
`p is b` identity gate always fails for interpreter 2 → all its builtin calls
run through interpreter 1 (`print` output lands in interp 1's sink).

Planned fix: (a) module-level singleton builtin table (identity holds across
interpreters); (b) `Env.interp` back-pointer on the globals env + `f_bcall`
resolves the CURRENT interpreter by walking to the root env (free in the
common case: the builtin lookup already ends at the root).

- **P1** The fix clears all 6 harness failures and keeps whence green (449)
  with no other test edits needed in either suite. Confidence 80%.
- **P2** After the fix, interpreter 2 on a shared AST takes the compiled
  builtin fast path (identity check passes; its `fast_hits` > 0) — the fix
  costs no fast-path coverage. Confidence 75%.
- **P3** fib(20) fast timing unchanged ±5% vs round-24 baseline 0.115 s (the
  numeric hot path is untouched; the extra root-walk steps only occur in the
  shadowed fallback). Confidence 70%.
- **P4** Elision-order measurement (synthetic ~40-step history, uniform
  observation sizes, single forced compaction, equal token target):
  newest-eligible-first reduces `invalidated_chars` by ≥70% vs the current
  oldest-first order. Confidence 65%.
- **P5** Over a long run with ~10 forced compactions (growing history),
  cumulative invalidated_chars under newest-first ≤ 30% of oldest-first
  (oldest-first re-mutates near the transcript head every time; newest-first
  keeps damage in the tail). Confidence 60%.
- **P6** At least one first-run failure of my own new tests or a wrong
  expectation during the round (program base rate). Confidence 75%.
- **P7** Server-side-compaction + TTL-keyed write pricing land offline-tested
  with no edits needed to EXISTING tests (only new ones). Confidence 55%.

Live-API status check (backlog #1): no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN
/ `ant` on this machine. `~/.claude/.credentials.json` exists but is the
Claude Code CLI's own OAuth store — prior rounds (6/15/19) had it too and
correctly did not count it as API credentials (CLI-scoped, not for custom
clients). Live verification stays blocked; not scored as a prediction.
