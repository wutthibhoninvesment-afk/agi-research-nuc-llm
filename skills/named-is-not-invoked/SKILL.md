---
name: named-is-not-invoked
description: Use when a reachability, coverage or "is this still used" claim is about to be made or trusted -- dead-code sweeps, "which of our tools does CI actually run", deprecation decisions. The failure is GRANULARITY: the instrument answers at the FILE level (something names this path) while the reader hears the COMMAND level (this runs), and the two differ by an order of magnitude. Symptoms: a grep or import graph reports a file reached but cannot say which subcommand ran; a tool has eight subcommands and CI invokes one; a registry says `wired`/`used`/`active` with no verb beside it; a scheduled job is believed to run a checker that only a unit test runs; a path reaches a call graph via a help string or a test asserting the command must NOT run. Covers separating named / called-as-a-library / invoked-as-a-command, extracting declared subcommands from argparse, and reporting UNREACHED without implying untested. NOT unrun-checker-latency, where the tool exists and only scheduling is missing.
---

# "Reached" is a claim at a granularity, and the coarse answer flatters you

A file-level reachability graph answers *does anything name this path*. Every
reader hears *does this run*. When the target is a single-purpose script the
two coincide, and the habit forms. When the target is a multi-command CLI they
come apart badly:

> Measured on a 2258-file research repo: 87 entry points declared `wired`, and
> `wiring_audit.py check` reporting `0 errors, 0 warnings`. Measured as
> COMMANDS instead: **20 verb-declaring entry points, 91 declared subcommands,
> 8 invoked (8.8%).** Restricted to the scheduled pipeline: **4 (4.4%).**

The registry was not lying. It answered a different question, in good faith,
and its own scope note said so — for six release cycles, while every reader
took `wired` to mean the tool ran.

## The three levels, and why collapsing them is the bug

| level | question | typical instrument | what it proves |
| --- | --- | --- | --- |
| 1 **named** | does anything mention this path? | grep, import graph, call graph | almost nothing on its own |
| 2 **called** | is the CAPABILITY exercised? | unit suites, coverage | the logic works — maybe against a mock |
| 3 **invoked** | is the COMMAND run? | this skill | the thing the reader meant |

They come apart in both directions, and both directions were measured:

* **Level 3 dead, level 2 alive.** A registry checker's `check` subcommand was
  invoked by nothing, yet its rules were enforced on every run — by a unit
  test that imported the module. Reporting "the checker never runs" would have
  been *false*, and the level ladder is what stopped it being written down.
* **Level 2 "alive" but hollow.** A pristine-checkout differential had ~20
  passing unit tests over `differential(...)`, all passing a MOCK runner. The
  logic was pinned; the real thing — a worktree plus two full suites — ran on
  no cycle at all. Level 2 green, level 3 red, and the program had spent
  cycles believing it had the coverage.

So `UNREACHED` means **"no automatic command invocation"**, never "untested".
Print that sentence next to the number, in the tool, not just in the report.

## When to use (triggers)

Fires when a reachability / coverage / "is this still used" claim is about to
be **made** or **trusted**:

* A dead-code sweep, a deprecation decision, or a "which of our tools does CI
  actually run" question.
* A registry, audit or dashboard reports `wired` / `used` / `active` /
  `reached` **with no verb beside it**, and a reader is about to take it to
  mean the thing runs.
* The target is a multi-command CLI — `argparse` subparsers, a `choices`
  positional, a dispatch dict — where file-level and command-level answers can
  differ by an order of magnitude.
* A path is "reached" only through a help string, a comment, a recommendation,
  or a test that asserts the command must NOT run unattended.
* A scheduled job is *believed* to run a checker, and the only thing exercising
  that code is a unit test (possibly against a mock).
* Someone is about to write "X is unused" or "X never runs" in a report,
  commit message, or state file.

Do **not** use it when the tool is a single binary with no subcommands and the
only missing thing is scheduling — that is `unrun-checker-latency`, whose
subject is detection latency, not granularity.

## Steps

1. **Say which level your existing claim is at.** Read the tool, not its
   name. If the answer is "a path appears in a text scan", you have level 1.
   Write the level into the registry/report *before* measuring anything —
   half the value is available immediately and costs nothing.

2. **Enumerate DECLARED commands from the declaration, not from `--help`.**
   Parse the source. For `argparse` there are two forms and both are real:

   ```python
   sub.add_parser("check")                      # + aliases=[...]
   ap.add_argument("cmd", choices=["a", "b"])   # POSITIONAL only
   ```

   An **option's** `choices` is not a command. `add_argument("--suite",
   choices=[...])` names values, and reading those as subcommands hands every
   file with a constrained flag an invented CLI that is 90% "dead" — a finding
   the checker manufactured. Running `--help` instead of parsing is worse than
   it looks: it executes the program, and a script with no argv guard does its
   real work on the way to printing usage.

3. **Extract INVOCATIONS per language.** This is the step that decides whether
   the tool is trustworthy, and grep cannot do it:

   * In **shell**, the raw line *is* the command. Scan it.
   * In **Python** (and any language that spawns via an argv list), a raw line
     is *not*. A path-plus-subcommand sitting in a Python line is inside a
     string constant. Read only folded `subprocess.run([...])`-style argv
     literals.

   Measured effect of that one rule: hand-audit precision went from **8 of 11
   to 8 of 8**. Every false positive was a command *inside a string*.

4. **Match the candidate against the DECLARED set.** A positional "first word
   after the path" reads a flag's value, a `-k` expression or a redirect
   target as a command. Requiring membership in a set the target itself
   declares means a false hit has to spell a real subcommand. Keep the
   unfiltered first-word read too, but report it as a *separate, weaker*
   finding — that is where a genuine typo (`pristine_check.py staus`) shows
   up, and where your own extractor bugs surface.

5. **Classify each invocation site.** `scheduled` (CI, the driver, a cron
   suite) / `test` / `other`. A subcommand invoked only from a test really
   does execute, and it is weaker evidence than the pipeline running it —
   report both numbers. The gap between them was 8.8% and 4.4% here.

6. **Decide, per command, whether it SHOULD run.** This is the real work and
   the measurement does not do it. Many dead subcommands are correct: one that
   costs minutes, talks to a live host, or spends money must not run
   unattended. What was missing was never permission — it was the number.

7. **Wire the enforcement where it will actually run**, which is usually a
   test rather than another line in a summary block nobody reads to the end.
   Assert INVARIANTS, never a pinned count: `INVOKED ⊆ DECLARED`, zero
   unexplained invocations, no report against entry points declared
   deliberately-manual, and a non-vacuity floor. A pinned `8 invoked` rots,
   and goes red the moment someone *fixes* something.

## Pitfalls

* **A reference that is evidence of the OPPOSITE of execution.** A test
  asserting `assertManual("python3 tool.py handoff …", "network")` exists to
  guarantee the command is never run unattended. Counting it as coverage reads
  a prohibition as a permission. Same for a `help=` string, an advice message
  (`Use \`tool.py plan\` instead`), and a copy-paste hint a diagnostic prints
  so a human can fix something.
* **A command in a comment.** Recommendation text is not invocation. One
  suite's own header spent a paragraph telling future authors to use
  `slowtier.py run --budget-s N`; nothing had ever run it.
* **Two comment syntaxes in one file.** A file that builds shell inside a
  string has `#` comments the host language's tokenizer correctly refuses to
  strip. Lines still starting with `#` after stripping are prose.
* **A fold that silently drops tokens.** `[sys.executable, "t.py", *argv,
  "--unit", "x"]` — keeping only the string constants loses `*argv`, which is
  where the command was, and the surviving tail gets read as one. Track
  whether the fold was COMPLETE and suppress the weak finding when it was not.
* **Language keywords in the command slot.** `assert "pkg/tool.py" in cands`
  offers `in`. Exclude the words that cannot be a subcommand in either
  language.
* **Reporting deliberately-manual entry points.** A tool nothing automatic
  runs has every command trivially uninvoked. Emitting that is the mute-button
  failure: a check that warns every cycle for a state the project chose gets
  ignored, then uninstalled.
* **Letting the finding set a failing exit code.** A dead subcommand is
  frequently a correct choice. Warn, count, and leave the exit code alone.
* **Exempting yourself.** Your new tool's own subcommands will be uninvoked
  too. Report them. Silencing that by bolting the tool onto a summary block
  improves the number by damaging the signal.

## Verification

You have applied this skill when:

- [ ] The claim states its level (named / called / invoked), and the registry
      or report says which — including for entries that were already there.
- [ ] DECLARED came from parsing the declaration; option `choices` were
      excluded; no `--help` was executed to obtain it.
- [ ] INVOCATIONS were read per language, and you can name the rule you used
      for each language rather than "a regex".
- [ ] **Every** reported invocation site was opened and read by hand at least
      once, and the precision is written down as a fraction. Skipping this is
      how a checker ships with a 27% false-positive rate that reads as a
      finding about the codebase.
- [ ] Sites are split scheduled / test / other, and both totals are published.
- [ ] The word UNREACHED is accompanied, in the tool's own output, by the
      statement that it does not mean untested.
- [ ] The enforcement asserts invariants, not a count, and does not set a
      failing exit code.
- [ ] Your own tool appears in its own output.

Reference implementation: `harness/verb_audit.py` (`verbs` / `check` /
`declared`, layered over `harness/wiring_audit.py`'s file-level closure) and
`harness/tests/test_verb_audit.py`. Re-derive the numbers with:

```bash
python3 harness/verb_audit.py check
python3 harness/verb_audit.py check --driver-only
python3 harness/verb_audit.py verbs --path harness/pristine_check.py
python3 -m pytest -q harness/tests/test_verb_audit.py -p no:cacheprovider
```

Related: `count-carries-its-noun-and-denominator` (when the missing piece is
the noun or the denominator rather than the granularity),
`unrun-checker-latency` (when the tool exists and only its scheduling is
missing), `unenforced-documented-rule` (when no tool exists at all).
