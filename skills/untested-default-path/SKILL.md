---
name: untested-default-path
description: Use when a tool, script or CLI has green tests and failed in production anyway, or before trusting that a tested tool actually runs — especially if every test builds a fixture and passes it in. Symptoms: each test calls the tool with `--ref DIR` / `--config` / `--fixture` / an injected client while real invocations pass none of those; a helper only the default branch reaches has no caller in any test; a tool "was broken for months and the suite never went red"; a `main()`, an auto-discovery step, a "fetch the reference from git/network/env" step, or an `or`-fallback that no test exercises; a repro that is just "run it with no arguments". Covers tabling every parameter by who supplies it, writing the missing default-path test plus its positive control, dating the outage by re-executing the entry path at each commit, and splitting a tool that was BROKEN from one nobody was RUNNING. NOT for a checker nothing invokes (unrun-checker-latency) or a hand-written list gone stale (derived-subject-set).
---

# The argument every test supplies is the argument production omits

Tests make the awkward parts go away. A tool that fetches its reference from
git gets a `--ref` flag "for testing"; a tool that discovers its inputs gets
`--files`; a tool that talks to a service gets an injected client. Every test
then uses the escape hatch, because that is what it is for, and the escape
hatch is the only path with coverage. The default path — the one every real
invocation takes — is executed by nobody until a user runs it.

Nothing about this looks like a gap. The tool has tests. The tests are
thorough: they sabotage the reference and check the tool notices, they test
retry behaviour, they test the flag that changes the comparison. They are all
downstream of a setup step they never run.

```
The path with the most tests is the path production never takes.
Count coverage by ENTRY POINT, not by assertion.
```

Worked example (round 395, this repo). `languages/whence/bench/ref_diff.py`
compares the working tree against a reference package, and it had five tests
covering sabotage detection, a mode-only counter change, fuzz mode, and two
timeout-retry behaviours. All five passed `--ref <dir>`. The default path
builds the reference by extracting it from git, and the function that does
that — the only reader of the module list, the only caller of `git` — had
zero test callers for its whole life. A new module arrived, the extraction
missed it, and the command died with `ModuleNotFoundError` before comparing
anything, at nine consecutive commits, with all five tests green throughout.

## When to use (triggers)

- A tool has tests, they pass, and it failed anyway.
- Before quoting a tool's result as evidence, when you have not personally
  run it in its default configuration.
- Reviewing a test file where every test constructs a fixture directory,
  temp repo, fake client or config and passes it to the tool.
- A tool that reads git, the network, the environment, or "the current
  directory" to find its own inputs.
- A regression that reproduces with no arguments and not with the flags in
  the test suite.

**When NOT to use:** a checker nothing schedules is `unrun-checker-latency`
(the tool works; only its invocation is missing). A hand-written list that
stopped matching the artefact is `derived-subject-set` (the list is the
defect; here the list may be perfect and untested). A rolling prose number
nobody re-derives is `carried-claim-rot`.

## Steps

1. **List the tool's parameters and mark who supplies each one.** For a CLI,
   read the argument parser; for a library, the constructor. Then grep the
   test file for each flag.

   ```bash
   grep -n "add_argument" tool.py
   grep -c -- "--ref" tests/test_tool.py     # 5
   grep -c -- "--ref" $(git grep -l "tool.py" --  '*.sh' '*.yml' Makefile)  # 0
   ```

   Outcome: a table of parameters where at least one row reads "every test
   supplies it, no caller does". That row is the finding.

2. **Find the code only the default branch reaches.** Every `a.x or
   fallback()` has a `fallback` and it is usually a function. Ask git how
   many callers it has.

   ```bash
   grep -rn "def extract_head\|extract_head(" --include='*.py' . | grep -v '^./tool.py'
   ```

   Outcome: a named function with zero callers outside the tool. Do not
   accept "it is covered indirectly" — name the test.

3. **Write the default-path test, and make it exercise the real step.** Not
   a mock of the git call: the actual call, into a tempdir, followed by the
   thing the tool does next (import it, parse it, connect to it). If the
   default path needs the network, that is a reason to mark the test, not a
   reason to skip the step.

   ```python
   def test_default_reference_is_buildable_and_importable(tmp_path):
       rd = _load_tool_module()
       rd.extract_head(str(tmp_path))                 # the untested step
       r = subprocess.run([sys.executable, "-c",
                           "import sys; sys.path.insert(0, %r); "
                           "import whence_ref.interp" % str(tmp_path)],
                          capture_output=True, text=True)
       assert r.returncode == 0, r.stderr
   ```

4. **Add the positive control.** A guard that has never been shown to go red
   is not a guard. Build the default reference, remove the piece the historic
   bug omitted, and assert the failure message.

   ```python
   os.remove(os.path.join(tmp, "whence_ref", "foreign.py"))
   assert "No module named 'whence_ref.foreign'" in _import(tmp).stderr
   ```

   Outcome: two tests, one green for the right reason and one that proves the
   first one can fail.

5. **Date the outage by re-executing the entry path per commit.** Do not
   reason from the source about when it broke — rebuild and run it. The
   verdict is a pure function of (the tool's source, the artefact it reads),
   so it can only change at a commit touching one of those; probe that set
   and carry each verdict forward to the next probed commit.

   ```bash
   python3 -m swe.toolliveness commits      # the commits that can move it
   python3 -m swe.toolliveness sweep        # rebuild + import at each
   python3 -m swe.toolliveness intervals    # alive/dead spans, with heads
   ```

   Outcome: a dead interval with real endpoints — commits, and the rounds or
   releases that ran under them — replacing whatever interval was published
   from memory.

6. **Separate BROKEN from UNUSED, because they have different fixes.**
   Count, separately: the commits at which the tool could not run, and the
   time since it last produced a *published result*. Derive the second from
   the tool's own output strings, not from its filename — a report that
   quotes "0 differing pairs" without naming the tool is still a use of it.

   ```bash
   python3 -m swe.toolliveness cites        # name-kind vs output-kind hits
   ```

   Outcome: two numbers. In the worked example the tool was dead for 5 rounds
   and had not published a result for 62, so the breakage cost nothing and
   the real defect was that nothing ran it. Fixing the code would have closed
   the smaller of the two problems.

7. **Ask what the default path's clean result actually covered.** A tool
   restored to life will print a summary; check its denominator before
   quoting it. The same round found "0 differing (file, mode) pairs" was
   computed over 66 of 96 pairs, the other 30 skipped by an exemption branch
   that printed per-item and never reached the summary line. See
   `skills/zero-rate-needs-a-distance`.

## Pitfalls

- **"The fixture path and the default path share 95 % of the code."** They
  do, and the 5 % is the part that touches the outside world, which is where
  tools break. Coverage percentage is the wrong unit; entry points are the
  unit.
- **Testing the default path by mocking the step it exists to perform.**
  Patching `subprocess.check_output` to return a canned blob tests the
  caller, not the extraction. The historic bug lived in *which files were
  asked for*, which a mock returning bytes cannot see.
- **Reading the source to date the outage instead of running it.** The
  module list changed spelling mid-history (a literal tuple, then a
  directory listing); a sweep that assumed either spelling measures the
  wrong tool on one side of that commit. Read each commit's own copy.
- **Ordering history by commit timestamp.** Two commits made inside one
  second compare equal and every verdict lands in the wrong span; a rebase
  can put author time out of order for real. Order by position in
  `git log --reverse`. This exact bug appeared in the sweep tool written for
  this skill and was caught only because the hermetic fixture made three
  commits in the same second.
- **Grepping the filename for usages.** "ref_diff.py" misses every mention
  of `ref_diff` bare or possessive; four rounds were lost that way in the
  worked example before the needle was reduced to the stem. Derive the
  needles (stem + printed literals), then sanity-check the count against a
  manual read of one file.
- **Treating "nobody complained" as evidence the tool worked.** In the
  worked example nobody complained because nobody ran it. Silence measures
  usage, not health.

## Verification

- [ ] Every parameter of the tool is in a table marked *supplied by tests /
      supplied by callers / defaulted*, and no row is defaulted-and-untested.
- [ ] The default-path test calls the real entry function, not a mock of it.
- [ ] A positive control exists that reproduces the historic failure message.
- [ ] The outage interval is stated as commits, produced by re-execution, not
      by reading the diff.
- [ ] "Broken for N" and "unused for M" are reported as two numbers.
- [ ] The restored tool's summary line prints its own denominator.

```bash
# the shape of a passing verification, from the worked example
python3 -m pytest tests/test_v10.py -k "extract_head or module_set or omitting" -q
#   3 passed

python3 -m swe.toolliveness report
#   alive  e376750..3772ac6  280 heads  rounds 144-385
#   dead   4c05cf4..21538a8    9 heads  rounds 387-391  ModuleNotFoundError: ...
#   alive  1b18b2c..ea92702    5 heads  rounds 392-394
#   span 4c05cf4..21538a8 rounds [387, 388, 389, 390, 391]: 0 citation(s)
```

The last line is the one to read twice. Zero citations while dead is not
reassurance — it is the measurement that says the interesting number was
never the outage.
