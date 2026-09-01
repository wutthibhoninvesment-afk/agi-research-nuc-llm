# Round 419 (SWE-loop D) — predictions, written BEFORE any measurement (D-013)

Target: `harness/swe/loop.py`, declared `unwired` / owner `SWE-loop(D)` /
`since_round: 415` in `harness/wiring-registry.json`. Round 415 found it; round
418 discharged the OTHER orphan (`ncs_engine.py`) by deletion. This round owns
this one.

The one fact I have before measuring: `git log --oneline -- harness/swe/loop.py`
and `... policy.py` return exactly ONE commit each, `ee30654` (the initial
commit). Neither file has been edited in 418 rounds. Everything they compose
has churned continuously: `swe/fuzz.py` is now 92 KB, `swe/oracles.py` 55 KB,
`swe/killers.py`, `swe/mutation.py`, and all of `agentloop/` have had rounds of
work. A frozen composer over churning parts.

## Predictions

- **P1 — imports resolve.** `python3 -m swe.loop --help` exits 0; every name
  `loop.py` imports (`Agent`, `AgentConfig`, `ToolRegistry`, `TraceLogger`,
  `ReadFileTool`, `SearchTool`, `WHENCE_ROOT`, the six tools, `PolicyLLM`,
  `swe_plan`) still exists. Confidence **0.70**. (Wide blast radius if wrong,
  but names in `agentloop.__all__` are load-bearing for many green tests.)

- **P2 — a full small end-to-end run does NOT complete cleanly first try.**
  `python3 -m swe.loop --out /tmp/... --fuzz-n 20 --oracle-n 10 --corpus-n 20
  --mutant-limit 2` raises, or returns non-zero, or writes a `metrics.json`
  with a null/garbage field. Confidence **0.75**.

- **P3 — if P2 holds, the break is in `loop.py`'s OWN code** (the metrics dict
  / `_passed` / the `.last` attribute reads), not inside the tools — because
  the tools have their own tests and `loop.py` has none. Confidence **0.50**.

- **P4 — `AgentConfig(max_observation_chars=20000)` is still a valid kwarg.**
  Confidence **0.80**.

- **P5 — the documented default invocation is unrunnable.** The docstring's
  `python3 -m swe.loop --out /tmp/swe-run` uses `--mutant-limit 0`, i.e. ALL
  mutants of `whence/interp.py` + `whence/values.py`. Round 107 measured 1056
  mutants for `interp.py` alone at v0.9; the suite is far bigger now. The
  documented command cannot finish inside a round. Confidence **0.80**.

- **P6 — the loop WRITES INTO THE TRACKED CHECKOUT.** `KillTool.run` opens
  `<root>/<test_file>` for writing, and `--root` defaults to `WHENCE_ROOT`
  (the real `languages/whence`), `--test-file` to
  `tests/test_generated_killers.py`. So any real run of this entry point
  edits a file under version control, unlike every other `swe/*` tool, which
  writes under `--out`. Confidence **0.70**.

- **P7 — a fuzz pass at n=20 finds 0 crashers** (the totality oracle has been
  swept for 400 rounds). Confidence **0.85**.

- **P8 — nothing in `harness/tests/` imports `swe.loop`.** (Re-derivation of
  round 415's claim, with the command beside it, per round 414's item 11:
  `python3 harness/wiring_audit.py refs harness/swe/loop.py --in harness`
  or a plain grep.) Confidence **0.95**.

## Disposition, decided before the measurement so the result cannot pick it

Round 415's rule is *wire it, test it, or delete it*. Deletion is wrong here:
`loop.py` is the only file in the tree that composes the SWE-loop track's
engines into one runnable pipeline, and `policy.py`'s `swe_plan` (which IS
tested) exists only to feed it. So: **fix whatever P2 finds, give it a real
test that drives `main()` end-to-end on a throwaway checkout copy, and flip
the registry entry to `wired`.** If P2 turns out false (it runs clean), the
test is still the deliverable and the finding is that it survived 414 rounds
of drift untouched — which is a finding either way.
