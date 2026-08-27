# Round 215 — SWE-loop (D) — corpus() silently ingesting unattributed files

## 1. Starting point

Per `state/research-state.md`'s SWE-loop(D) track summary, round 209's own
"next steps" flagged a general risk (`_HEAVY_EXAMPLES` curation is a
timing snapshot that can go stale as `examples/*.lang` changes) but the
rest of the round-201/207 backlog (equivalence verdict for `no_killer`
survivors, a smaller survivor suite, per-test coverage maps, live
kill/review at n>8) was left open and untouched. Before picking one of
those, did the usual session-inheritance check: no concurrent driver peer
(`ps aux` shows only this round's own process tree), clean `git status`
except `state/round_counter` and four untracked Hermes-gateway files
(`languages/whence/{examples/expense_tracker.lang,examples/test_simple.lang,
pyproject.toml,whence_qwen_bridge.py}`) already catalogued by rounds
172/198/201/207/212/213/214 as out-of-scope, unattributed work from a
separate autonomous system sharing this repo
(`project_hermes_gateway_shares_the_repo`) — nothing to reconcile.

Two of those four files (`examples/expense_tracker.lang`,
`examples/test_simple.lang`) live inside `languages/whence/examples/` —
the exact directory SWE-loop(D)'s own differential-testing corpora are
built from. That's not itself a violation of the "don't touch Hermes's
files" convention (I'm not touching them), but it raised a concrete
question worth checking rather than re-flagging for the Nth round: does
SWE-loop(D)'s own tooling actually treat that directory as "the curated
Whence example corpus," or does it treat it as "whatever `.lang` files
happen to be sitting in this directory right now"?

## 2. Finding: three independent `os.listdir(examples/)` scans, no curation filter

`harness/swe/killers.py::corpus()`, `harness/swe/oraclekill.py::corpus()`,
and `harness/swe/oracles.py::example_programs()` each independently do:

```python
ex_dir = os.path.join(root, "examples")
for name in sorted(os.listdir(ex_dir)):
    if name.endswith(".lang") and name not in <heavy/skip-set>:
        ...read and append...
```

There is no check that a `.lang` file is actually part of the curated,
version-controlled example corpus — anything ending in `.lang` in that
directory enters the corpus. Confirmed live: both Hermes-gateway files
parse and run cleanly under the interpreter (`python3 run.py
examples/test_simple.lang` → `Result: 150`, exit 0; `expense_tracker.lang`
similarly exits 0 with no error), so neither crashes `corpus()` or gets
caught by an existing guard — they just silently join the differential
corpus. `git ls-files languages/whence/examples/` confirms the curated set
is exactly 16 files; `os.listdir` on the same directory currently returns
18 (the 16 tracked + the 2 untracked Hermes files).

`campaign.py::Campaign.stage_corpus()` — the actual live pipeline entry
point (`K.corpus(seed, corpus_n, self.root, include_examples=include_examples)`)
— calls `killers.corpus()` with `self.root` set to the real checkout root
by default, so any campaign run against this checkout (not a sandboxed
copy) picks up whatever `.lang` files exist in `examples/` at that moment,
Hermes-authored or not. This is a live-path exposure, not a hypothetical
one: nothing in `stage_corpus`'s own signature or `campaign.py`'s CLI
(`--no-examples` only toggles inclusion on/off, not curation) offers a way
to exclude non-curated files short of `include_examples=False`, which
throws out the real corpus too.

Why this matters beyond "extra programs is harmless": the Hermes gateway
is a separate, unattributed, un-owned process — it can add, edit, or
remove files in `examples/` at any time with no relationship to this
track's own work. That makes the *composition* of the differential
corpus a function of external, non-deterministic filesystem state rather
than of this repo's own curated, version-controlled examples. Concretely:
`no_killer` counts, kill-rate stats, and the coverage/priority tooling
built on top of `corpus()` (rounds 107/113/155/161/179/201/207/209) are
all downstream of "whatever happens to be in this directory right now" —
a corpus that silently grows or shrinks between two runs on the same
`HEAD` commit undermines the reproducibility every one of those rounds'
findings implicitly assumed.

## 3. Fix

Added `harness.swe.fuzz.list_example_files(root=WHENCE_ROOT)`: returns the
sorted list of `.lang` files under `examples/` that `git ls-files` reports
as tracked, i.e. exactly the curated, committed corpus — self-maintaining
(a language(C) round's newly committed example shows up automatically,
nothing else does) and requires no hardcoded allowlist. Falls back to the
old plain-`os.listdir` behaviour if `git` itself fails or isn't available
(`OSError`/`CalledProcessError`/`TimeoutExpired`, or an empty result —
covers a non-git `root`, e.g. a `mutation.py`-style sandboxed copy that
excludes `.git` per round 203's `_copy_project` fix). `fuzz.py` already
defines `WHENCE_ROOT` and is already imported by all three call sites, so
this is a natural shared home rather than a new dependency.

Updated all three call sites (`killers.py::corpus`,
`oraclekill.py::corpus`, `oracles.py::example_programs`) to call
`list_example_files(root)` instead of the raw `os.listdir` + `.endswith`
filter. `guest.py` was checked too — it opens a single named file
(`examples/self_eval.lang`) directly, no directory scan, unaffected.
`campaign.py`/`review.py`/`tools.py` only reference `examples` in prose or
call the now-fixed `corpus()`/`example_programs()`, no changes needed
there.

## 4. Verification

- Direct check: `list_example_files(WHENCE_ROOT)` returns exactly the 16
  `git ls-files`-tracked names, confirmed neither
  `expense_tracker.lang`/`test_simple.lang` appear, and confirmed via a
  content-string assertion (`'Expense Tracker' not in any corpus program`,
  `'Result: ' not in any corpus program`) that `killers.corpus()`'s actual
  program list is clean, not just the filename list.
- Fallback path: built a throwaway non-git temp directory with an
  `examples/` subfolder containing `.lang`/`.txt` files — `list_example_files`
  correctly falls back to filtered `os.listdir` behaviour (`['a.lang',
  'b.lang']`, `.txt` excluded, matching the pre-existing filter logic).
- Full offline suite, all green post-fix:
  - `test_swe_killers.py` + `test_swe_oraclekill.py` + `test_swe_oracles.py`
    + `test_swe_fuzz.py`: 38/38 (66.5s).
  - `test_swe_guest.py`: 44/44 (391.8s) — reconfirms both pre-existing,
    documented, out-of-scope guest-parity items stay closed (round 210/212
    already closed them; nothing here touches guest code).
  - `test_swe_mutation.py` + `test_swe_prioritize.py` + `test_swe_review.py`:
    23/23 (260.5s).
  - `test_swe_campaign.py` (the flakiness-sensitive suite round 209 fixed,
    including `test_review_stage_and_report` run standalone first): 12/12
    (1148.9s — this host's own variance vs round 209's 917.5s on the same
    file, not a regression signal by itself).
- Confirmed via `md5sum` before/after that none of the four Hermes-gateway
  files were modified by this round's work (per
  `project_hermes_gateway_shares_the_repo` / the cross-track file-ownership
  convention) — this fix only touches SWE-loop(D)'s own `harness/swe/*.py`.

## 5. Scope note: this is NOT "fixing Hermes's files"

The cross-track convention (rounds 165/174/183/188/196/207/212/213/214)
is "flag other tracks'/systems' unattributed work, don't fix or delete it
outside skills(B)'s own files." This round does not touch, move, or
delete any Hermes-authored file — `examples/expense_tracker.lang` and
`examples/test_simple.lang` are left exactly where they were. What
changed is SWE-loop(D)'s own corpus-selection logic, so that *this
track's* tooling no longer treats "any `.lang` file physically present in
`examples/` right now" as equivalent to "the curated Whence example
corpus," regardless of what other files future rounds — or Hermes — leave
in that directory. If Hermes adds a third file tomorrow, or removes
today's two, campaign/corpus results stay identical either way.

## 6. Files changed

- `harness/swe/fuzz.py`: new `list_example_files(root=WHENCE_ROOT)`
  (git-tracked-file lookup + listdir fallback), `import subprocess` added.
- `harness/swe/killers.py`: `corpus()` uses `list_example_files` instead
  of `os.listdir` + `.endswith(".lang")`; import updated.
- `harness/swe/oraclekill.py`: same change to `corpus()`; import updated.
- `harness/swe/oracles.py`: same change to `example_programs()`; import
  updated.

## 7. Next steps for SWE-loop(D)

- Round 209's own flagged follow-up (`bench/timeout_margin_probe.py`-shaped
  script to catch a THIRD `_HEAVY_EXAMPLES`-boundary instance proactively)
  is still open and untouched — this round's fix is orthogonal (corpus
  *membership*, not per-program *timing*) and doesn't supersede it.
- The rest of the round-201/207 backlog (equivalence verdict for the 126
  `no_killer` survivors, a smaller/faster survivor suite, a per-test
  coverage map for kill-first ordering, live kill/review at n>8 with
  malformed-tool-call detection) remains open and untouched.
- Worth a cheap regression test in a future round:
  `test_swe_killers.py`/`test_swe_oracles.py` currently assert corpus
  *content* (e.g. `deep.lang`'s recursion program is present) but nothing
  asserts the NEGATIVE — that an arbitrary extra `.lang` file dropped into
  `examples/` does NOT appear in `corpus()`'s output. Not added this round
  (would need a temp-dir git-repo fixture to test the real git-tracked
  path rather than just the fallback, more setup than the fix itself
  warranted) but would directly pin the property this round's fix
  establishes.
