---
name: audit-the-artefact-that-runs
description: Use when a mechanism is DEPLOYED by copying or generating a file that the version-control tree does not hold — a git hook installed from a generator function, a rendered CI config, a systemd unit written by a script, a crontab, a dotfile, an nginx conf assembled from a template — and every test in the repo asserts about the GENERATOR rather than the deployed copy. Symptoms - a guard "has been there since round N" and nobody can say which generation is installed; a step was added to a generator, committed, tested, and never installed; a deployed file names paths or verbs that no test resolves; someone asks "is the hook actually running?" and the answer comes from reading the generator. The method - parse the DEPLOYED file, compare it to a re-generation using the deployed file's own parameters, resolve every reference it names, and validate the arguments it passes statically rather than by executing them.
---

# Audit the artefact that runs, not the one that is tested

A mechanism that is *deployed* — written out to a path the repository does
not track — has two bodies. There is the generator, which is in git, which
reviewers read and tests assert about; and there is the installed file, which
is what actually executes. Everything anyone knows is about the first one.

The gap is not exotic. It opens the moment somebody edits the generator and
forgets the install step, and it closes only if somebody notices. In between,
every test passes and the deployed mechanism is a previous generation of
itself. Worse: a deployed file usually names *other* things — script paths,
subcommands, unit names — and nothing resolves them either, so the mechanism
can be byte-fresh and still be a no-op.

## Trigger conditions

Any one of these:

1. A repo file is a **generator** for something installed elsewhere
   (`hook_script()`, a `render_*` function, a `*.tmpl`, a `--install` verb),
   and the target path is untracked (`.git/hooks/`, `/etc/`, `~/.config/`).
2. Every test naming the mechanism asserts about a **string the generator
   returns**. Grep the test file for the install path: if it never appears,
   nothing has read the deployed copy.
3. The generator has been **extended more than once** and each extension
   required a separate manual install. That is a recurrence waiting to
   happen, and the recurrences are invisible.
4. The deployed file **invokes other files by relative path**, especially
   behind an existence guard (`[ -f x ] || exit 0`, `command -v`,
   `try: import`). An existence guard converts a broken reference into
   silence, which is the failure mode nobody reports.
5. You are about to add a step to a deployed mechanism and want to know
   whether the previous author's step is even running.
6. An incident review asks "was the guard on?" and the honest answer is "it
   was in the repo".

## Steps

1. **Read the deployed file, not the generator.** Every question here is
   about the file on disk, so parse the file on disk. Importing the generator
   and pulling its output apart is easier and measures the wrong object — the
   generator is what the existing tests already cover.

2. **Compare identity against a re-generation using the DEPLOYED file's own
   parameters.** Generators take arguments (an interpreter path, a prefix, a
   hostname), and the installer may legitimately have been given a
   non-default one. Read those parameters back out of the deployed file, feed
   them to the generator, and compare. A naive byte comparison against the
   generator's defaults reports a difference the installer was *asked for* as
   a drift, and a check that cries wolf on a correct install gets deleted.
   Report at least: `ok`, `stale` (ours, older generation), `foreign`
   (someone else's file — do not clobber it), `absent`.

3. **Resolve every reference the deployed file names.** For each path it
   invokes, does the path exist? Say explicitly what happens when it does
   not — for most deployment shapes the answer is *nothing happens, silently*
   — and say which references are load-bearing. One missing file behind an
   existence guard can disable the only enforcing step while the mechanism
   reports success.

4. **Validate the arguments statically. Do not execute the steps.** Running a
   guard's verb is running the guard. Today's steps may all be read-only
   `check`-shaped verbs; that is a property of today's steps, not a contract
   the mechanism imposes, and a module whose job is to audit the guard must
   not be the thing that fires it. Read the target's CLI surface instead —
   for Python, `ast`-walk for `add_parser(...)`, `add_argument("--flag")` and
   `choices=`; for a shell script, its `case "$1" in` arms.

5. **Fail open on the static analysis, fail closed on existence.** A target
   whose CLI you cannot read is `unknown`, never `broken`, and `unknown` must
   not fail `--strict`. A reader that guesses is worse than one that abstains
   — but a path that is simply not there is not a judgement call.

6. **Key the parser on SHAPE and replay it over the whole history of the
   generator.** A parser written against today's deployed text is the same
   staleness defect one level up. `git log --format=%H -- <generator>`, load
   each revision, generate, parse, and assert the invariants you believe
   (step count monotone, exactly one enforcing step, zero parse failures). If
   an old generation fails to parse, the parser is over-fitted to the
   present.

7. **Put the check where the mechanism is not.** A stale deployed file *is*
   the old text; it cannot warn about being stale. The check belongs in the
   test suite that runs on the live checkout — not inside the mechanism it
   audits, and not in a second copy of the deployment step.

8. **Probe the environment edges instead of assuming them.** Deployment paths
   are resolved by tools with their own rules (`git rev-parse --git-path`,
   `systemctl --user` vs system, `XDG_CONFIG_HOME`). Build a throwaway
   instance and measure. A check that goes red in the project's own
   pristine-worktree runner is a red about your apparatus.

## Pitfalls

* **Asserting the deployed file exists, as a hard failure, in a fresh
  clone.** That is usually correct — an absent file means the mechanism is
  entirely off — but the failure message must name the one-line install
  command, or the next person deletes the test.
* **Reading a fail-open marker as an enforcing one.** `|| exit 0` is how a
  hook declines to block; `|| exit 1` is how it blocks. Counting the first as
  a gate reports the escape hatch as a guard.
* **Matching invocation lines with a regex loose enough to catch the
  existence guards.** `[ -f "$top/x" ]` and `if [ -f "$top/x" ]; then` both
  name a script. Counting them doubles every step.
* **Adding the audit as one more step of the audited mechanism.** It cannot
  observe the state it exists to find.
* **Rewriting the deployed file to make the check pass.** Reinstalling is the
  fix when the generator is right; if the deployed file is right and the
  generator drifted, that is a finding, not a re-install.

## Verification

```
python3 harness/hookaudit.py audit --strict     # exit 0, `identity ok`
python3 -m pytest -q harness/tests/test_hookaudit.py
```

The second is the one that matters: it contains a node that installs the
mechanism, refuses a real `git commit`, then renames one referenced script
and shows the same commit succeeding — the reference gap demonstrated end to
end rather than argued. If your instance of this skill cannot produce that
node, you have audited identity and not reference.
