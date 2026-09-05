---
name: red-debt-triage
description: Use when a test node in a suite you own is reported red and you are about to reproduce it looking for a defect in that suite. Some failing nodes are META-NODES — their subject is the VERDICT of other nodes (a registry over "every test that ever failed", an assertion that a nested suite exits 0, an audit over retained CI logs) — and such a node goes red because ANOTHER node did, in another suite or another run, often one owned by a track that never runs yours. Reproducing it succeeds, teaches nothing, and points at code with no defect in it. Symptoms: a red that "has closed by itself before"; a red whose blame lands on a commit that touched none of the failing file's dependencies; a red whose assertion message is a LIST OF OTHER TEST NAMES; the same node re-diagnosed from scratch by several people. Covers reading the failure BODY before reproducing, classifying primary vs derived, splitting same-log from cross-log derivation, and the regex traps that make a body parser publish a confident wrong answer.
---

# Read the failure body before you reproduce the failure

A red test node reports one of two very different things:

* **PRIMARY** — something in this node's own subject broke. Reproduce it, find
  the defect, fix it. This is what everybody assumes.
* **DERIVED** — this node's subject is *other nodes' verdicts*, and it is red
  because one of them is. There is no defect in the suite that hosts it. The
  fix is somewhere else, and possibly in somebody else's tree.

The signal that separates them is already in the retained failure output, and
almost nobody reads it: **a derived node names its cause in its own assertion
message.** An aggregate test that shells out to another suite embeds that
suite's failures verbatim. A registry audit over "every test that has ever
failed" prints the node ids it could not classify. A coverage gate prints the
uncovered symbols. In each case the body is a pointer, and the standard
tooling — which greps `^FAILED <nodeid>` and stops — throws it away.

**Measured instance.** In one repo's 778 retained per-round CI logs there were
447 red `(node, round)` observations. 64 were derived — **one in five of the
readable ones** — and they came from exactly **3 nodes out of the 64 that have
ever gone red**. Two of those three had *never once* reported a defect in the
suite hosting them, across 16 red rounds each spanning 50 rounds, and each red
episode was re-diagnosed from scratch by whoever came next — and only ONE of
seven closes was by the team that owns the hosting suite.

## Trigger conditions

- A red node's assertion message contains **other test node ids**, file paths
  from another tree, or a nested test runner's output.
- The node's name contains `audit`, `registry`, `census`, `check_exits_zero`,
  `runs_green`, `no_undeclared`, `covers_every`, `this_tree` — anything whose
  subject is the state of a corpus rather than one behaviour.
- The report says the node is RECURRENT, or that it was opened by a
  team/track/CI job that does not run the failing suite.
- You reproduced it, it failed identically and deterministically, and the
  stack trace pointed at an assertion rather than at any code you can blame.
- The same node has been "fixed" more than twice and keeps coming back.

**When NOT to use:** the node fails intermittently on unchanged code (that is
flakiness — an environmental verdict, and a different job); the node is red on
its very first run (its author is watching a new assertion fail, which is
neither primary nor derived debt); or you have not yet reproduced it at all
(reproduce first — a red you cannot reproduce is a claim about the runner).

## Steps

1. **Reproduce, solo, before anything else.** A red that has closed by itself
   before may be the runner and not the code. Run the single file alone, on an
   idle machine, and record the exact line:
   `python3 -m pytest <file> -q` → `2 failed, 58 passed in 2.87s`.
   If it does not reproduce, stop: the finding is about concurrency or the
   environment, and say *that* instead of patching the test.

2. **Read the failure BODY, not the summary line.** Open the retained log or
   scroll past `short test summary info` to the `FAILURES` section. Ask one
   question: *does this message name any other test node?*

3. **Classify.**
   - Names ≥1 other node **that has itself failed somewhere in your retained
     history** → DERIVED.
   - Names none → PRIMARY. Proceed normally.
   - Names a node that has never failed → still PRIMARY. A quoted identifier
     is not a cause; require the named node to actually be red somewhere.
   - The body is not retained at all (a runner that discards child output, a
     `--tb=no` run) → **UNREADABLE, not primary.** Report the gap. "No cause
     found" and "could not look" are different facts and must not collapse.

4. **For a DERIVED red, split same-log from cross-log — this decides how bad
   it is.**
   - **SAME-LOG:** every named node is red in the *same run*. Typically an
     aggregate node that invokes a sibling suite. Noisy (one break reports as
     two) but never invisible — the reader sees the cause a few lines down.
     Fix the cause; the aggregate closes with it.
   - **CROSS-LOG:** at least one named node is not red in this run. The node
     is asserting over a corpus its own run does not contain. **The cause may
     already be GREEN**, leaving the host's red as the only surviving trace of
     something that no longer exists. Do not hunt for it in the host. Go to
     the named node's own history, find the run it was red in, and act there —
     which for a registry-shaped node usually means *classifying* the node,
     not fixing code.

5. **Write the diagnosis where the next reader is, not where you are.** A
   derived red will recur — nothing in step 4 stops the node being a whole-
   tree gate hosted in one team's suite. Put the cause into whatever pre-work
   report your CI already injects (prompt, PR comment, dashboard row) so the
   next reader is told "this is derived, the cause is X" instead of spending
   their first hour reproducing it. This is a latency fix; say so, and do not
   claim it is structural.

6. **Do not close the loop with another whole-tree fail-closed gate.** The
   mechanism that produces derived reds *is* a whole-tree fail-closed
   assertion living in one team's suite: anyone can redden it, only the host
   runs it. If your new instrument ships one, it becomes the next instance of
   the series it measures. Make the new tool a **measurement** (exit 0, print
   the number) and pin your tests on the *already-retained* history, which no
   future run can move.

## Pitfalls

- **The `:` trap.** Writing the node-id regex as one character class that
  includes `:` (so `file.py::Class::method` matches) makes it swallow sentence
  punctuation, because audit messages read `<nodeid>: went red …`. Every
  reference comes out one character long, resolves to nothing, and the node is
  reported PRIMARY. Measured cost of exactly this bug: two sibling nodes
  asserting over *the same finding list in the same log* came out DERIVED 16
  times and PRIMARY 16 times, the only difference being that one prints the
  finding bare (trailing colon) and the other through a diff (quoted). Spell
  the `::` structure out; strip trailing `.`/`,` after the match.
- **The parenthesis trap.** `\(([^)]+)\)` is the reflex for "text in
  brackets" and breaks on any vocabulary whose own tokens contain brackets —
  team names like `SWE-loop(D)`, `harness(A)` truncate to `SWE-loop(D`.
  Anchor on a fixed trailing clause instead of on the closing bracket.
- **Transcribed fixtures rot.** If your test builds a fake audit message by
  hand, an edit to the real message silently empties your parser's output. Have
  the fixture **call the producer** (`_r001_message(509, "SWE-loop(D)", 510)`)
  so producer and parser cannot drift.
- **The audit that only sees committed files.** A tool keyed on
  `git ls-files` reports GREEN for a new module sitting untracked beside it,
  then red the moment you commit. Run every declaration check against a
  **staged** tree (`git add -N` at minimum).
- **A block title claimed by two failing nodes.** `Class.method` collides
  across files. Resolve to neither and count it unresolved; an ambiguous body
  is evidence about nobody.
- **Diluting the rate with what you could not read.** Report the derived share
  over *readable* observations and print the unreadable count beside it.
  Folding unreadable into primary understates derivation and overstates how
  well your own suites are doing.

## Verification

Against your own retained CI logs, in one pass:

```bash
# 1. Does the red reproduce solo? (If not, stop — it is the runner.)
python3 -m pytest <the red file> -q

# 2. Does its body name another test node?
sed -n '/^=* FAILURES/,/^=* short test summary/p' <the retained log> \
  | grep -oE '[A-Za-z0-9_./+-]+\.py(::[A-Za-z0-9_.+=-]+)+' | sort -u

# 3. Was any of those actually red somewhere? (the cause must be real)
grep -l "FAILED .*<candidate node id>" <log dir>/*.log

# 4. Same-log or cross-log?
grep -c "^FAILED .*<candidate node id>" <the SAME log>     # >0 => same-log
```

You have applied this correctly when you can state, for the node you were
handed: *primary or derived; if derived, same-log or cross-log; the causing
node id; the run it was red in; and whether it is still red.* If you cannot
name the causing node, you have not finished step 2 — and if you fixed
something in the host suite before you could, you fixed the wrong thing.

**The reference implementation** of steps 2–4 as a tool is
`harness/redcause.py` in this repo (round 511): `graph` for the corpus-wide
table, `node <id>` for one node's history, `live` for the currently-red set
with a cause verdict per row.
