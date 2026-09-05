#!/usr/bin/env python3
"""claim_check.py — re-derive the factual claims a SKILL.md's Verification
block makes, instead of trusting them.

Why this exists
---------------
Every SKILL.md in this workspace ends with a `## Verification` block: exact
commands plus an `# expected: ...` claim about what each one prints. Those
claims are the only thing telling a future reader whether the skill still
works — and **nothing ever re-executes them**. They rot silently, and the
rot has now been confirmed five separate times by five separate rounds:

    round 321  a stale count in `research-state.md`'s own header
    round 333  `Ran 141 tests` (really 165) and a `0 warning(s), exit 0`
               corpus-sweep claim that had been false since ~round 309
    round 338  four stale FACTS (not numbers) across SPEC.md, guest.py,
               test_self_hosting.py, test_parser_differential.py
    round 339  `cd ~/agi-research` in two Verification blocks — a workspace
               path that has not existed since the repo was renamed to
               `agi-research-nuc-llm`, so every command under it was
               unrunnable as written

Rounds 333 and 338 both recommended the same thing: stop clearing these by
hand one at a time and build the sweep. This is that sweep.

Three tiers, cheapest and safest first
--------------------------------------
1. **Static (always).** `C001` — a path named in a Verification command that
   resolves nowhere plausible. No execution at all, so it is safe to run
   anywhere, and it is what catches the `~/agi-research` class. Its six
   suppression rules have one home (`token_exempt_reason`), and the two
   round 507 added carry a paired assertion: `C007` reports a path the repo
   DECLARED absent that has since come into existence, so the allowlist
   behind rule 6 is a claim that can be wrong rather than a mute.
2. **Classification (always).** Every command is sorted into `auto`
   (cheap, offline, read-only, deterministic) or `manual` (with a reason).
   The tally is the honest coverage number — the analogue of round 333's
   "63 fragment links, 0 checked".
3. **Execution (`--run`, opt-in).** Only `auto` commands are executed, and
   their real output is diffed against the claim (`C002`).

Classification FAILS CLOSED: a command whose program is not on the allowlist
is `manual`, never `auto`. This is deliberate and load-bearing. The corpus
contains commands that ssh to another machine, spend money on live model
calls (`live_smoke.py`, `nuc/taskscript/run.py`, `trigger_eval.py` without
`--audit`), write files into the checkout (`--write`, `--out`), and run for
minutes (`swe.campaign --workers 4`). Round 333 had to READ `trigger_eval.py`
line by line to confirm one flag was offline before running it; a tool that
guesses on a denylist would eventually guess wrong and bill somebody. An
allowlist can only ever fail by declining to check something.

Usage:
    python3 claim_check.py PATH [PATH ...]        # static + classify
    python3 claim_check.py --list PATH            # print the command table
    python3 claim_check.py --run PATH             # also execute `auto` ones

Exit codes: 0 = no stale claims, 1 = at least one, 2 = usage/IO problem.
"""

import argparse
import os
import re
import json
import shlex
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))

VERIFICATION_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*verif.*)$", re.I | re.M)
ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.M)
FENCE_RE = re.compile(r"^\s*(```|~~~)")


# --------------------------------------------------------------------------
# Verification-block extraction
# --------------------------------------------------------------------------

def blank_fenced(body):
    """Same text, same length, with every fenced line blanked to spaces.

    Length-preserving on purpose: the heading scan below needs character
    offsets that still index into the ORIGINAL body. (`skill_lint.py`'s
    `strip_fenced_code` collapses fenced lines to "" instead, which is fine
    for regex presence checks but would shift every offset here.)
    """
    out, fence_tok = [], None
    for line in body.split("\n"):
        stripped = line.lstrip()
        if fence_tok is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence_tok = stripped[:3]
            out.append(line)
        else:
            out.append(" " * len(line))
            if stripped.startswith(fence_tok):
                fence_tok = None
    return "\n".join(out)


def verification_section(body):
    """Return the text of the (first) Verification section of `body`, or "".

    The section runs from the heading to the next heading of the same or a
    shallower level, matching how a reader scans the file. `skill_lint.py`'s
    H004 uses the same `verif` substring match on headings, so the two tools
    agree on which section this is.

    Headings are looked for in a fence-blanked copy. Without that, a shell
    comment inside the block (`# 1. Bracket invariants over your REAL data`,
    `# Cheap detector: does a round's own last message …`) parses as a
    level-1 ATX heading and truncates the section at its own first comment —
    which silently emptied 7 of this corpus's 19 Verification blocks.
    """
    m = VERIFICATION_HEADING_RE.search(body)
    if not m:
        return ""
    level = len(m.group(1))
    start = m.end()
    for line_m in ANY_HEADING_RE.finditer(blank_fenced(body), start):
        if len(line_m.group(1)) <= level:
            return body[start:line_m.start()]
    return body[start:]


def split_command_and_comment(line):
    """Split a shell line into (command, comment) at the first `#` that
    starts a comment.

    Quote-aware, because the corpus has real cases where `#` is inside a
    quoted argument (`grep -n "STUB\\|in progress\\|PENDING"` would lose its
    pattern to a naive `line.split("#")`), and position-aware, because a `#`
    glued to a word (`foo#bar`, a URL fragment) is not a comment either.
    """
    sq = dq = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and (sq or dq):
            i += 2
            continue
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        elif c == "#" and not sq and not dq:
            if i == 0 or line[i - 1].isspace():
                return line[:i].rstrip(), line[i + 1:].strip()
        i += 1
    return line.rstrip(), ""


def _unbalanced_quotes(text):
    """True if `text` leaves a quote open (so the command continues)."""
    sq = dq = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        i += 1
    return sq or dq


#: A shell PROMPT, not part of the command. Round 441 measured 23 commands
#: in this corpus written `$ python3 -m pytest …`; under the pre-441
#: whole-line allowlist two of them scraped into `auto` on a substring and
#: the other 21 landed in the single `unknown program` bucket — pooled with
#: the 120 commands that really do invoke un-allowlisted tools, so a
#: systematic and one-line-fixable cause was indistinguishable from the
#: irreducible remainder. Stripped here, at the ONE place both construction
#: sites pass through, so classification, `path_tokens`, the `cd` tracker and
#: the executor all see the same runnable text.
PROMPT_RE = re.compile(r"^\s*\$ +")


class Command:
    """One executable line from a Verification block, with its claim."""

    def __init__(self, path, line_no, command, claim):
        self.path = path
        self.line_no = line_no
        self.command = PROMPT_RE.sub("", command)
        self.claim = claim
        self.kind = None            # "auto" | "manual"
        self.reason = None          # why it is manual (None when auto)

    def __repr__(self):            # pragma: no cover - debugging aid
        return "<Command %s:%d %r>" % (self.path, self.line_no, self.command)


EXPECTED_RE = re.compile(r"^expected\b", re.I)


def parse_commands(text, path="<mem>", first_line=1):
    """Pull (command, claim) pairs out of a Verification section.

    Rules the corpus forced:

    * Only fenced content counts. Prose bullets around the fence are
      guidance, not commands.
    * A trailing `# ...` comment on a command line is that command's claim,
      unconditionally — it is unambiguous.
    * A comment-only line is a claim ONLY if it opens with `expected`
      (continuation comment lines after that one are folded in). Several
      skills number their steps with leading `# 1.` / `# 2.` comments that
      introduce the NEXT command; treating those as the PREVIOUS command's
      claim would attach every claim to the wrong line.
    * Backslash continuations and unterminated quotes (a `python3 -c "..."`
      spanning many lines) join into one logical command.
    """
    commands = []
    in_fence = False
    fence_tok = None
    pending = None                  # Command awaiting `# expected:` lines
    in_expected = False
    buf = None                      # (line_no, text) of a joined command
    for offset, raw in enumerate(text.split("\n")):
        line_no = first_line + offset
        stripped = raw.strip()
        if not in_fence:
            if FENCE_RE.match(raw):
                in_fence, fence_tok = True, stripped[:3]
            continue
        if stripped.startswith(fence_tok):
            in_fence, fence_tok, pending, in_expected = False, None, None, False
            buf = None
            continue
        if buf is not None:
            buf = (buf[0], buf[1] + "\n" + raw)
            if buf[1].rstrip().endswith("\\") or _unbalanced_quotes(buf[1]):
                continue
            cmd_text, comment = split_command_and_comment(buf[1].split("\n")[-1])
            joined = "\n".join(buf[1].split("\n")[:-1] + [cmd_text])
            pending = Command(path, buf[0], joined.strip(), comment)
            commands.append(pending)
            in_expected = bool(comment)
            buf = None
            continue
        if not stripped:
            pending, in_expected = None, False
            continue
        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if pending is not None and EXPECTED_RE.match(comment):
                pending.claim = (pending.claim + " " + comment).strip() \
                    if pending.claim else comment
                in_expected = True
            elif pending is not None and in_expected:
                pending.claim = (pending.claim + " " + comment).strip()
            else:
                pending, in_expected = None, False
            continue
        cmd_text, comment = split_command_and_comment(raw)
        # The continuation test runs on the COMMAND half, never the raw line.
        # `grep -n "STUB" state/research-state.md | tail  # the CURRENT
        # session's stub` has a lone apostrophe in its comment; testing the
        # raw line for balanced quotes read that as an open quote and
        # swallowed the next three commands of session-inheritance-audit's
        # block into one unparsed blob — silently, since a swallowed command
        # simply never appears in the report.
        if cmd_text.rstrip().endswith("\\") or _unbalanced_quotes(cmd_text):
            buf = (line_no, raw)
            continue
        if not cmd_text.strip():
            continue
        pending = Command(path, line_no, cmd_text.strip(), comment)
        commands.append(pending)
        in_expected = bool(comment)
    return commands


# --------------------------------------------------------------------------
# Tier 2: safety classification (fail-closed allowlist)
# --------------------------------------------------------------------------
# A command reaches `auto` only by matching AUTO_PATTERNS and matching no
# MANUAL_PATTERN. MANUAL_PATTERNS are checked first and win, so a normally-fine
# program with a dangerous flag (`pytest ... --out /repo/x`) stays manual.

PLACEHOLDER_RE = re.compile(r"<[^>]{1,40}>|\bNNN\b|\bLAST\b|\*")

MANUAL_PATTERNS = [
    # -- costs money -------------------------------------------------------
    (r"\bclaude\b|\blive_smoke\.py\b|--live\b", "priced",
     "spends real model tokens"),
    (r"\btrigger_eval\.py\b(?!.*--audit)", "priced",
     "trigger_eval.py launches live `claude -p` probes unless --audit"),
    (r"taskscript/run\.py", "priced",
     "task-script tiers dispatch to a real model (see "
     "preflight-priced-task-scripts)"),
    # -- leaves this machine ----------------------------------------------
    (r"\bssh\b|\bscp\b|\bcurl\b|\bwget\b|\bfast_lane\.py\b|\bhandoff\b",
     "network", "contacts another host"),
    # -- writes ------------------------------------------------------------
    (r"--write\b|--out\b|(?<![0-9])>(?!=)|\brm\b|\bmv\b|\bcp\b|"
     r"\bgit\s+(commit|add|checkout|reset|stash)\b|\bmkdir\b|\bprintf\b|"
     r"\btee\b", "mutating", "creates or modifies files"),
    # -- minutes, not seconds ---------------------------------------------
    (r"\bswe\.(campaign|loop|mutation|fuzz|oracles|coverage|oraclekill|triage)\b"
     r"|--workers\b|\bbench_\w+\.py\b|\bdemo\.py\b", "expensive",
     "long-running campaign/benchmark"),
    # Round 441. `pytest -k 'no_decider'` with no path collects the WHOLE
    # rootdir. Seven such commands sit in one skill's block, invisible until
    # PROMPT_RE stopped the `$ ` prefix from demoting them to "unknown
    # program"; promoting them to `auto` without this would have turned a
    # 336-command sweep into seven full-repo collections.
    # `--version`/`--help` never collect anything, so they are not expensive
    # and the corpus uses `pytest --version` as its cheapest smoke command.
    (r"^\s*(python3?\s+-m\s+)?pytest\b(?!.*--(?:version|help)\b)"
     r"(?!.*(?:[\w./-]+\.py|\b\w[\w./-]*/))",
     "expensive", "pytest with no test path: collects the whole rootdir"),
    # -- answer depends on the machine, not the repo -----------------------
    (r"^\s*(ps|pgrep|find|uptime|free|df|dmesg)\b|\|\s*(ps|pgrep)\b",
     "environment", "reports live machine state, not a repo fact"),
    # -- shell plumbing this tool deliberately does not emulate ------------
    (r"^\s*(for|while|if|case)\b|\$\(", "shell",
     "shell construct, not a single checkable command"),
]

# Round 441. Every rule below matches the PROGRAM POSITION of a shell
# segment, never the raw command string.
#
# Until this round the eight script-named entries were plain `\bname\.py\b`
# searches over the whole line, so the allowlist licensed a FILENAME rather
# than a program. Measured at HEAD, with the file's own `classify()`:
#
#     sed -i 's/a/b/' claim_check.py        -> auto      <-- edits this file
#     sed -i 's/a/b/' somewhere_else.py     -> manual
#     vim claim_check.py                    -> auto
#     chmod 777 skill_lint.py               -> auto
#
# The first of those is not hypothetical: it is
# `skills/second-door-skips-the-gate/SKILL.md:224` verbatim, a deliberate
# break-it-and-see step whose very next line is `git checkout claim_check.py`
# (correctly `manual`, so the undo would have been skipped). The module
# docstring's promise -- "An allowlist can only ever fail by declining to
# check something" -- was false for those eight entries for as long as they
# existed, and nothing noticed because `corpus_check.py` never passes
# `--run`, so the published coverage was `0/336 commands` every round.
#
# Each rule is (program regex, `require` or None, `forbid` or None). The
# program regex is matched against `program_of(segment)`, which is fully
# anchored; `require`/`forbid` are searched against the WHOLE command, and
# exist only to keep the three flag-qualified entries as narrow as they were.
AUTO_RULES = [
    (r"^python -m (pytest|unittest)$", None, None),
    (r"^pytest$", None, None),
    (r"^skill_lint\.py$", None, None),
    (r"^check_round_recorded\.py$", None, None),
    (r"^trigger_eval\.py$", r"--audit\b", None),
    (r"^claim_check\.py$", None, None),
    # --run would nest executors
    (r"^state_claim_check\.py$", None, r"--run\b"),
    # offline: reads the case file + report dir
    (r"^case_coverage\.py$", None, None),
    # Round 429. Only the READ-ONLY subcommands. `check` and `baseline` run
    # whole suites in a fresh worktree (minutes) and append to
    # state/pristine-check-ledger.jsonl, so they must stay manual; naming the
    # four verbs explicitly is what keeps them there when a fifth is added.
    # `(?![\w.-])` and not `\b`: `\b` matches before a hyphen, so a future
    # `suites-and-write` verb would have inherited `suites`'s auto verdict.
    (r"^pristine_check\.py$",
     r"\bpristine_check\.py\s+(suites|status|baseline-status|dirt)(?![\w.-])",
     None),
    # Round 501 (skills B). Offline, free and read-only -- EXCEPT `--write`,
    # which appends an entry to state/prediction-bank-ledger.json, and
    # `--force`, which REPLACES one. Forbidden by name for the reason the
    # pristine_check entry above names its verbs rather than its exclusions:
    # a future write flag must not inherit an `auto` verdict by default. Added
    # so `state/research-state.md`'s round-501 next-step #1 can carry a
    # RE-DERIVABLE claim -- `carryforward_check.py` -> exit 0 -- which is the
    # first checkable claim a next-steps block has carried since round 495.
    (r"^carryforward_check\.py$", None, r"--(write|force)\b"),
    (r"^(wc|head|tail|cat|ls|grep)$", None, None),
    (r"^git$", r"^\s*git\s+(status|log|diff|show)\b", None),
]

MANUAL_COMPILED = [(re.compile(p), c, r) for p, c, r in MANUAL_PATTERNS]
AUTO_COMPILED = [(re.compile(p),
                  re.compile(q) if q else None,
                  re.compile(f) if f else None) for p, q, f in AUTO_RULES]

# `perl -e 'alarm N; exec @ARGV' REAL COMMAND` -- this repo's documented
# timeout wrapper (`preflight-priced-task-scripts`, `colocated-model-lane`,
# `self-updating-driver-loop`). The program to classify is the one after it.
EXEC_WRAPPER_RE = re.compile(
    r"^\s*perl\s+-e\s+(?P<q>['\"])[^'\"]*exec\s+@ARGV[^'\"]*(?P=q)\s+")

#: `FOO=bar cmd` -- an assignment prefix is not the program.
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=\S*$")

_INTERPRETERS = ("python", "python3", "python2")


def split_segments(command):
    """Split on `&&`, `||`, `;` and `|` -- but never inside quotes.

    A naive `re.split` cuts `python3 -c "import x; print(y)"` in half and
    then classifies `print(y)"` as a program. Round 441: every segment of a
    chained command runs, so every segment must classify `auto` for the line
    to be `auto`. `ls -la /var/log/sysstat/ && journalctl --list-boots` was
    `auto` on the strength of its FIRST word alone.
    """
    out, buf, i, sq, dq = [], [], 0, False, False
    while i < len(command):
        c = command[i]
        if c == "\\" and i + 1 < len(command):
            buf.append(command[i:i + 2])
            i += 2
            continue
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        if not sq and not dq:
            two = command[i:i + 2]
            if two in ("&&", "||"):
                out.append("".join(buf)); buf = []; i += 2; continue
            if c in ";|":
                out.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c)
        i += 1
    out.append("".join(buf))
    return [s for s in out if s.strip()]


def _tokens(segment):
    try:
        return shlex.split(segment)
    except ValueError:                      # unbalanced quotes: best effort
        return segment.split()


def program_of(segment):
    """The program a shell segment INVOKES, canonicalised, or "".

    `python3 -m pytest ...` -> `python -m pytest`; `python3 foo/bar.py ...` ->
    `bar.py`; `sed -i ... claim_check.py` -> `sed`. Basenamed so that
    `skills/skill-authoring/scripts/case_coverage.py` and a bare
    `case_coverage.py` are the same program.
    """
    segment = EXEC_WRAPPER_RE.sub("", segment)
    toks = _tokens(segment)
    while toks and ENV_ASSIGN_RE.match(toks[0]):
        toks.pop(0)
    if not toks:
        return ""
    head = os.path.basename(toks[0])
    if head not in _INTERPRETERS:
        return head
    rest = toks[1:]
    for i, t in enumerate(rest):
        if t == "-m" and i + 1 < len(rest):
            return "python -m %s" % rest[i + 1]
        if t == "-c":
            return "python -c"
        if t.endswith(".py"):
            return os.path.basename(t)
    return "python"


def _segment_is_auto(segment, whole):
    prog = program_of(segment)
    for prog_rx, require, forbid in AUTO_COMPILED:
        if not prog_rx.match(prog):
            continue
        if require is not None and not require.search(whole):
            continue
        if forbid is not None and forbid.search(whole):
            continue
        return True
    return False

# `cd X && real_command` — classify (and time) the real command, not the cd.
CD_PREFIX_RE = re.compile(r"^\s*cd\s+(\S+)\s*&&\s*")


def classify(command):
    """Return ("auto", None) or ("manual", reason). Fails closed."""
    body = CD_PREFIX_RE.sub("", command)
    if PLACEHOLDER_RE.search(body):
        return "manual", "placeholder: not runnable as written"
    if re.match(r"^\s*cd\s+\S+\s*$", body):
        return "manual", "bare `cd`: sets up the next command, checks nothing"
    for rx, category, reason in MANUAL_COMPILED:
        if rx.search(body):
            return "manual", "%s: %s" % (category, reason)
    segments = split_segments(body)
    if not segments:
        return "manual", "unknown program: empty command (fails closed)"
    for seg in segments:
        if not _segment_is_auto(seg, body):
            return "manual", ("unknown program: allowlist has no entry for "
                              "%r in command position (fails closed)"
                              % (program_of(seg) or seg.strip()))
    return "auto", None


# --------------------------------------------------------------------------
# Tier 1: static path resolution
# --------------------------------------------------------------------------
# Only paths that resolve NOWHERE plausible are reported. Everything in this
# section exists to keep the FALSE-POSITIVE rate at zero, because a checker
# that cries wolf about `/tmp/camp` gets muted and then never catches the real
# `cd ~/agi-research`. Four suppression rules, each forced by a real corpus
# case (the first draft of this file fired 31 times: 2 true, 29 false):
#
#   1. SCRATCH: `/tmp/...` is created BY the command, not required by it.
#   2. PLACEHOLDER tokens (`round-NNN`, `round-*.json`, `<name>`, `$p`) are
#      templates the reader fills in; they are not supposed to resolve.
#   3. `mutating`/`network` commands are not path-checked at all — their path
#      arguments are outputs (`--write tests/gen.py`) or live on another host
#      (`fast_lane.py handoff ./model jab@box '~/m'`).
#   4. UNANCHORED relative paths are skipped: a token whose first component
#      is not itself a real directory under some known base is relative to
#      something this tool cannot see. `sampled-interval-brackets` documents
#      `pytest -q tests/test_bounds.py` for the READER'S repo, which has no
#      `tests/` here — undecidable statically, so not a finding.
#   5. CREATED-IN-BLOCK (round 507): a path the Verification block itself
#      makes, at or before the command that names it — `touch
#      languages/whence/zz_probe.py && python3 harness/readset.py blast`.
#      **Rule 1 already states this rule and tests a proxy for it.** Its
#      reason string is "created by the command, not required by it"; its
#      test is a `/tmp/`-family prefix. A file created INSIDE the repo
#      satisfies the sentence and fails the proxy, which is how round 505's
#      `diff-to-check-blast-radius` skill reddened this checker for two
#      rounds. `created_paths` computes the evidence; the gate still decides.
#   6. DECLARED ABSENT (round 507): `state/known-absent-paths.json`, the
#      registry `xref_check`'s X004 rule already reads. A path can be
#      correct-as-written AND missing on purpose — a negative control
#      (`readset.py blast languages/whence/no_such_file.py`, whose whole
#      point is a path that does not exist inside a directory that does) is
#      not rot, and rule 4 lets it through today only when it is written
#      UNANCHORED, i.e. only when it is written badly. Reusing X004's file
#      rather than minting a second one is deliberate: round 506 put a path
#      in that registry to close this very red, and the red stayed open
#      because the two checkers did not share it. The sharing comes with a
#      POSITIVE CONTROL — see `check_absent_registry` and C007 — because an
#      allowlist nothing ever falsifies is a mute, not a rule.
#
# Bases accumulate across a Verification block: `cd harness` sets the working
# directory, and any directory NAMED as an argument (`swe.mutation
# ../languages/whence whence/interp.py`) becomes a plausible base for every
# later command in the same block, which is how that skill's later
# `--files whence/interp.py` lines are meant to be read.

PATH_EXT_RE = re.compile(r"\.(py|md|sh|json|lang|errand|txt|cfg|toml|yaml|yml)$")
URLISH_RE = re.compile(r"://|^-|^\d+$")
TOKEN_PLACEHOLDER_RE = re.compile(r"[*?$<>]|\bNNN\b|\bLAST\b")
SCRATCH_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/", "/proc/")
UNCHECKED_CATEGORIES = ("mutating", "network")

# Rule 5's evidence. Programs whose NON-FLAG arguments are things they bring
# into existence, and programs whose LAST non-flag argument is a destination.
# `rm` is deliberately absent: it is already `mutating`, and a path a block
# deletes is a path the block required.
CREATING_PROGRAMS = ("touch", "mkdir", "tee")
CREATING_DEST_PROGRAMS = ("cp", "mv", "install", "ln")
# `>` / `>>`, but never `2>&1`: the character class excludes `&`, so the
# redirect-to-fd form matches nothing rather than inventing a file called `1`.
REDIRECT_RE = re.compile(r">>?\s*([^\s;|&<>]+)")

# Rule 6's registry, shared with `xref_check.py`'s X004 (round 345). One file,
# two readers, one `_comment` describing both.
ABSENT_ALLOWLIST = os.path.join("state", "known-absent-paths.json")


def _norm_tok(tok):
    """One normalisation, used on BOTH sides of every token comparison.

    `path_tokens` keeps `./x` as written and a `touch` argument may be
    spelled `./x` or `x`; comparing the two raw forms silently misses. The
    reported token is always the raw one — only the comparison is normalised.
    """
    tok = (tok or "").strip("'\"`,;()")
    return os.path.normpath(tok) if tok else tok


def created_paths(command):
    """Paths this command line BRINGS INTO EXISTENCE, normalised.

    Granularity is the command LINE, not the shell segment: `touch X && q X`
    and the (nonsensical) `q X && touch X` are treated alike, because this
    returns a set for the whole line. That is the one over-approximation the
    rule accepts, and it is bounded — ACROSS lines the caller accumulates in
    order, so a path created at line 5 does not excuse a claim at line 2.
    Both halves are pinned in `TestRuleFiveEndToEnd`.

    Returns a set of normalised tokens. Callers hand it to the gate; nothing
    here decides anything.
    """
    out = set()
    for m in REDIRECT_RE.finditer(command):
        out.add(_norm_tok(m.group(1)))
    for seg in split_segments(command):
        toks = _tokens(seg)
        while toks and ENV_ASSIGN_RE.match(toks[0]):
            toks.pop(0)
        if not toks:
            continue
        prog = os.path.basename(toks[0])
        args = [t for t in toks[1:] if not t.startswith("-")]
        if prog in CREATING_PROGRAMS:
            out.update(_norm_tok(a) for a in args)
        elif prog in CREATING_DEST_PROGRAMS and len(args) >= 2:
            out.add(_norm_tok(args[-1]))
    out.discard("")
    return out


def load_absent_allowlist(repo_root, path=None):
    """Repo-relative paths whose ABSENCE is declared correct, as a set.

    Deliberately the same file `xref_check.load_absent_allowlist` reads. The
    duplication is eight lines; the alternative was a second registry, and a
    second registry is what kept this checker red for two rounds while an
    entry for the offending path sat in the first one.
    """
    try:
        with open(os.path.join(repo_root, path or ABSENT_ALLOWLIST),
                  encoding="utf-8") as f:
            return set(json.load(f).get("paths", {}))
    except (OSError, ValueError):
        return set()


def token_exempt_reason(tok, created=(), declared_absent=()):
    """Why `tok` must NOT be resolved, or None if it is a checkable claim.

    THE one home for suppression rules 1, 2 and the "not a path at all" half
    of the list above. Round 411: this used to be three bare `continue`s
    inside `path_tokens`, which made the exemption a property of ONE producer
    rather than of the tool. `check_paths` has a second door — the `cd`
    branch, which matches its target with its own regex and never calls
    `path_tokens` — and for 71 rounds that door resolved tokens the four
    rules exempt. It went unnoticed only because no Verification block
    contained a placeholder or scratch `cd` until round 410 wrote one.

    So the rule is stated once, as a function with a name, and BOTH doors
    ask it. A third door added later must ask it too; the invariant is
    pinned by `test_every_c001_site_consults_the_exemption_gate`.

    Rule 3 (mutating/network) is NOT here: it is a property of the COMMAND,
    not of the token, and `check_paths` applies it from `cmd.reason`.
    Rule 4 (unanchored) is NOT here either: it needs the caller's bases and
    lives in `is_anchored`.

    Round 507 added rules 5 and 6, and they are the reason this function
    takes arguments beyond the token. Both are properties of the token IN A
    CONTEXT — what the block has already made, and what the repo has already
    declared missing on purpose — so the context is passed IN rather than
    read here. The gate stays the one decider; `created_paths` and
    `load_absent_allowlist` are producers of evidence, and a caller that
    forgets them gets the round-411 behaviour, not a crash.
    """
    if not tok or URLISH_RE.search(tok):
        return "not a path: url, flag or bare number"
    if TOKEN_PLACEHOLDER_RE.search(tok):
        return "placeholder: a template the reader fills in"
    if tok.startswith(SCRATCH_PREFIXES):
        return "scratch: created by the command, not required by it"
    norm = _norm_tok(tok)
    if norm in created:
        return ("created: this Verification block makes this path itself, "
                "so its absence between runs is the point")
    if norm in declared_absent or tok in declared_absent:
        return ("declared absent: %s says this path is correct while missing"
                % ABSENT_ALLOWLIST)
    return None


def path_tokens(command):
    """Path-shaped arguments of a command, in order.

    Deliberately narrow: a token counts only if it is `~`/absolute/`./`
    anchored, or it contains a `/` and ends in a known extension or a slash.
    Bare words (`tests`, `harness`) are skipped — too many are subcommands or
    -k expressions, and a false STALE costs more than a missed one.
    """
    out = []
    for raw in re.split(r"[\s=]+", command):
        tok = raw.strip("'\"`,;()")
        if token_exempt_reason(tok) is not None:
            continue
        if tok.startswith(("~", "/", "./", "../")):
            out.append(tok)
        elif "/" in tok and (PATH_EXT_RE.search(tok) or tok.endswith("/")):
            out.append(tok)
    return out


def resolve_token(tok, bases):
    """First existing filesystem path for `tok` under any of `bases`, else None."""
    if tok.startswith("~"):
        cand = os.path.expanduser(tok)
        return cand if os.path.exists(cand) else None
    if os.path.isabs(tok):
        return tok if os.path.exists(tok) else None
    for base in bases:
        cand = os.path.normpath(os.path.join(base, tok))
        if os.path.exists(cand):
            return cand
    return None


def is_anchored(tok, bases):
    """True if `tok`'s first path component names a real directory under some
    base — i.e. the path is expressed relative to something this tool can see,
    so a miss is real rot rather than an unknown base. Absolute and `~` paths
    are always anchored: there is nothing else they could be relative to."""
    if tok.startswith(("~", "/")):
        return True
    if tok.startswith(("./", "../")):
        return True                 # explicitly relative to a base we know
    head = tok.split("/")[0]
    if not head:
        return True
    return any(os.path.isdir(os.path.join(b, head)) for b in bases)


class Finding:
    def __init__(self, command, code, message, level="STALE"):
        self.command, self.code, self.message, self.level = \
            command, code, message, level

    def __str__(self):
        return "%s:%d: %s %s %s" % (self.command.path, self.command.line_no,
                                    self.level, self.code, self.message)


def check_paths(commands, repo_root, declared_absent=None):
    """C001: a Verification command names a path that resolves nowhere.

    `cd DIR` inside the fence updates the working directory used for
    subsequent commands, which is how most of this corpus is written
    (`cd harness && python3 -m pytest -q tests/...`). Returns
    (findings, n_checked, n_skipped) so the caller can report honest coverage
    instead of implying every path was verified.

    Two things ACCUMULATE across the command list, and they accumulate for
    the same reason `cwd` and `bases` do: the list is one Verification
    block's worth of shell, read top to bottom. `bases` grows with every
    directory named; `created` grows with every path a command makes. A
    caller that wants per-block scoping calls this once per block.

    `declared_absent` defaults to the registry under `repo_root`; pass a set
    to override it (the tests do, and so would a caller auditing a checkout
    that has no registry).
    """
    findings = []
    cwd = repo_root
    extra_bases = []
    created = set()
    if declared_absent is None:
        declared_absent = load_absent_allowlist(repo_root)
    n_checked = n_skipped = 0
    for cmd in commands:
        created |= created_paths(cmd.command)
        m = re.match(r"^\s*cd\s+(\S+)", cmd.command)
        if m:
            target = m.group(1).strip("'\"")
            # A `cd` target is a path claim like any other and gets the same
            # suppression rules (round 411). This branch is the tool's SECOND
            # door into C001 — it has its own regex and never calls
            # `path_tokens` — so it has to ask the gate itself.
            #
            # Exempt is NOT the same as "skip the branch": the assignment
            # below is a side effect on `cwd` that every later command in the
            # block depends on, and it must still happen when the target is
            # exempt AND happens to exist (`cd /tmp/wt` in a block run after
            # the worktree was created). Only the FINDING is suppressed.
            exempt = token_exempt_reason(target, created, declared_absent)
            resolved = resolve_token(target, [cwd, repo_root])
            if exempt is not None:
                n_skipped += 1
            elif resolved is None:
                n_checked += 1
                findings.append(Finding(
                    cmd, "C001", "`cd %s` — no such directory (checked %s)"
                    % (target, _describe_bases([cwd, repo_root], repo_root))))
                continue
            else:
                n_checked += 1
            if resolved is not None and os.path.isdir(resolved):
                cwd = resolved
            if not CD_PREFIX_RE.match(cmd.command):
                continue
        category = (cmd.reason or "").split(":")[0]
        bases = [cwd, repo_root] + extra_bases
        for tok in path_tokens(cmd.command):
            if category in UNCHECKED_CATEGORIES:
                n_skipped += 1
                continue
            # `path_tokens` asked the gate with no context (rules 1 and 2 are
            # all it can decide from a bare token); rules 5 and 6 need the
            # block, so this is the same gate asked a second time with what
            # the block knows. One home, two questions.
            if token_exempt_reason(tok, created, declared_absent) is not None:
                n_skipped += 1
                continue
            if not is_anchored(tok, bases):
                n_skipped += 1
                continue
            n_checked += 1
            hit = resolve_token(tok, bases)
            if hit is not None:
                if os.path.isdir(hit) and hit not in bases:
                    # a directory named as an argument is a plausible base for
                    # every later command in this same Verification block
                    bases.append(hit)
                    extra_bases.append(hit)
                continue
            findings.append(Finding(
                cmd, "C001", "path %r resolves nowhere (checked %s)"
                % (tok, _describe_bases(bases, repo_root))))
    return findings, n_checked, n_skipped


def check_absent_registry(repo_root, path=None):
    """C007: a path DECLARED absent that now EXISTS.

    Rule 6 lets a Verification block name a path that is not there. On its
    own that is a mute: an allowlist no measurement can falsify passes just
    as well against a registry somebody filled with real rot. So the
    registry is read in BOTH directions. Every declared path that has come
    into existence is a finding against the DECLARATION, reported at the
    registry's own file:line rather than at the skill's, because the
    declaration is what went stale.

    This is round 506's gitignore-pin lesson applied one file over: it
    replaced an only-negative assertion with a pair, on the grounds that an
    only-negative assertion cannot tell a working filter from one that
    dropped everything. Same here — C007 firing zero times is only evidence
    if C007 can fire.

    A missing or unparseable registry returns no findings. A checkout
    without one (every tmp tree the tests build) is not making a false
    declaration; it is making none.
    """
    rel = path or ABSENT_ALLOWLIST
    try:
        with open(os.path.join(repo_root, rel), encoding="utf-8") as f:
            text = f.read()
        entries = json.loads(text).get("paths", {})
    except (OSError, ValueError):
        return []
    lines = text.split("\n")
    findings = []
    for declared in sorted(entries):
        if not os.path.exists(os.path.join(repo_root, declared)):
            continue
        line_no = next((i + 1 for i, ln in enumerate(lines)
                        if '"%s"' % declared in ln), 1)
        findings.append(Finding(
            Command(rel, line_no, "(registry entry)", None), "C007",
            "declared absent but EXISTS: %r. Either the path was created "
            "and the declaration is now false, or the declaration named the "
            "wrong path. Remove the entry or fix the prose it protects "
            "— do not leave a live path allowlisted as missing."
            % declared))
    return findings


def _describe_bases(bases, repo_root):
    names = []
    for b in bases:
        rel = os.path.relpath(b, repo_root)
        names.append("<repo>" if rel == "." else "<repo>/" + rel)
    return ", ".join(dict.fromkeys(names))


# --------------------------------------------------------------------------
# Tier 3: execute and compare
# --------------------------------------------------------------------------
# Only metrics that appear IN THE CLAIM are compared. A claim of
# "all passed, < 1s" states no number, so only the exit code is checkable —
# reported as `unquantified` rather than silently counted as verified.

METRICS = [
    ("ran_tests", re.compile(r"\bRan (\d+) tests?\b")),
    ("passed", re.compile(r"\b(\d+) passed\b")),
    ("failed", re.compile(r"\b(\d+) failed\b")),
    ("deselected", re.compile(r"\b(\d+) deselected\b")),
    ("skills", re.compile(r"\b(\d+) skill\(s\)")),
    ("errors", re.compile(r"\b(\d+) error\(s\)")),
    ("warnings", re.compile(r"\b(\d+) warning\(s\)")),
    ("gaps", re.compile(r"\b(\d+) gaps?\b")),
]
EXIT_RE = re.compile(r"\bexit (\d+)\b")


# Round 459. A claim on a MONOTONE number is the wrong shape as an equality.
# Round 441 ran this tier once and found 15 stale C002s; every single one
# understated, because every one was a suite or corpus size and those only
# grow. `== 165 passed` is therefore a claim that is guaranteed to go stale
# on the next test somebody adds, and correcting it only resets the clock.
# `>= 165 passed` is the same fact with the direction of drift written into
# it: it stays true until somebody DELETES a test, which is the event a
# reader actually wants to hear about.
#
# Four spellings, all found in this corpus's prose: `>= 207 passed`,
# `\u2265 207 passed`, `at least 207 passed`, `207+ passed`.
FLOOR_MARK_RE = re.compile(
    r"(?:>=|\u2265|at least|no fewer than|minimum(?: of)?)\s*(?=\d)", re.I)
#: `207+ passed` -- the trailing spelling.
PLUS_FLOOR_RE = re.compile(r"\b(\d+)\+(?=\s)")


def _normalise_floors(claim):
    r"""`(text with the floor markers removed, offsets of the marked digits)`.

    Removing them is not cosmetic. `METRICS`'s prefix-shaped patterns --
    `\bRan (\d+) tests?\b` -- want the number IMMEDIATELY after the word, so
    `Ran >= 865 tests` matches nothing at all and the claim degrades to
    `C003 unquantified`: a floor that silently switches the check OFF. This
    round wrote exactly that bug into `skill-authoring`'s own block and its
    own after-pass caught it, which is the pitfall the round's skill warns
    about, committed by the round that wrote the warning.
    """
    text, offsets, last = [], set(), 0
    for m in PLUS_FLOOR_RE.finditer(claim):
        text.append(claim[last:m.start()])
        offsets.add(sum(len(s) for s in text))
        text.append(m.group(1))
        last = m.end()
    text.append(claim[last:])
    claim, last, out, more = "".join(text), 0, [], set()
    for m in FLOOR_MARK_RE.finditer(claim):
        out.append(claim[last:m.start()])
        more.add(sum(len(s) for s in out))
        last = m.end()
    out.append(claim[last:])
    # Offsets from the first pass shift by however much the second pass cut
    # before them; recompute rather than track, since both passes are rare.
    joined = "".join(out)
    shifted = set()
    for off in offsets:
        head = claim[:off]
        shifted.add(off - sum(len(m.group(0)) for m in FLOOR_MARK_RE.finditer(head)))
    return joined, more | shifted


def claim_constraints(claim):
    """Metric name -> (op, asserted integer), for every metric in `claim`.

    `op` is `"=="` for a bare number and `">="` for a FLOOR. Four spellings:
    `>= 230 passed`, `\u2265 230 passed`, `at least 230 passed`, `230+ passed`.
    """
    text, floors = _normalise_floors(claim)
    out = {}
    for name, rx in METRICS:
        m = rx.search(text)
        if m:
            out[name] = (">=" if m.start(1) in floors else "==",
                         int(m.group(1)))
    m = EXIT_RE.search(text)
    if m:
        out["exit"] = (">=" if m.start(1) in floors else "==", int(m.group(1)))
    return out


def claim_metrics(claim):
    """Metric name -> asserted integer, for every metric named in `claim`.

    The equality VIEW of `claim_constraints`, kept at this exact signature
    because `state_claim_check.py:748` consumes it and a floor means nothing
    to that tool's `S003` comparison yet.
    """
    return dict((k, v) for k, (_op, v) in claim_constraints(claim).items())


def observed_metrics(output, returncode):
    out = {}
    for name, rx in METRICS:
        found = rx.findall(output)
        if found:
            out[name] = int(found[-1])
    out["exit"] = returncode
    return out


# Round 459. `expiring-fixture-window:140` writes its expected value as a
# bare output line UNDER the command instead of a `#` comment. `parse_commands`
# reads that line as a COMMAND, so the real command's claim is empty and the
# whole site degrades to `C003 UNQUANTIFIED` -- an expected value invisible to
# the tier whose entire job is checking expected values. Round 441 found it by
# hand while chasing something else and called it "a finding of its own"; it
# was never given a detector, so nothing would have found the second one.
#
# The rule fires only on a command that ALSO failed to classify (`unknown
# program`), which is what keeps the false-positive rate at zero: a real
# program named `203` does not exist, and a real command that happens to
# start with the word `expected` does not either.
BARE_EXPECTATION_RE = re.compile(
    r"^\s*(?:expected\b"
    r"|\d+\s+(?:passed|failed|skipped|deselected|error|warning|test)"
    r"|(?:Ran|OK\b)\s*\d*\s*(?:tests?)?\s*$"
    r")", re.I)


def check_bare_expectations(commands):
    """C005: lines that state an expectation where a command should be."""
    findings = []
    for cmd in commands:
        if cmd.kind != "manual":
            continue
        if not (cmd.reason or "").startswith("unknown program"):
            continue
        first = cmd.command.split("\n")[0]
        if BARE_EXPECTATION_RE.match(first):
            findings.append(Finding(
                cmd, "C005",
                "expectation written as a bare line, not a `#` comment: %r "
                "parses as a COMMAND, so the real command above it has an "
                "empty claim and is never number-checked" % first[:70],
                level="UNCOMMENTED"))
    return findings


def run_command(cmd, repo_root, cwd, timeout):
    """Execute one `auto` command. Returns (output, returncode).

    The command runs in its OWN process group and the timeout kills the whole
    group. `subprocess.run(..., shell=True, timeout=T)` would kill only the
    `/bin/sh` it spawned; a `pytest` grandchild survives, reparents to init and
    keeps burning CPU for the rest of the sweep — which is exactly what
    happened the first time this ran (`ppid=1`, a `test_swe_campaign` run still
    going four minutes into a 150-second cap, skewing every later command's
    timing on a shared box).

    This is a pitfall this repo had already written down —
    `skills/fuzz-mutate-kill-loop/references/pitfalls.md`, "`subprocess.run
    (timeout=)` kills the child, not its children" — in a corpus this very
    tool was built to audit. Reading a pitfall is not the same as applying it.
    """
    try:
        proc = subprocess.Popen(cmd.command, shell=True, cwd=cwd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                start_new_session=True)
    except OSError as e:
        return "claim_check: could not start: %s" % e, -1
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out, proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):     # already gone
            proc.kill()
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:                 # pragma: no cover
            out = ""
        return (out or "") + "\nclaim_check: TIMEOUT after %ss" % timeout, -1


def check_by_running(commands, repo_root, timeout, dry_run=False,
                     ledger=None, budget=None, skill=None):
    """C002: run every `auto` command and diff its metrics against the claim.

    Returns `(findings, n_executed)`. Round 441: the summary line used to
    report `n_ran = n_auto if args.run else 0`, which over-counts, because an
    `auto` command whose paths are absent from this checkout is reported C004
    and never executed. The caller now gets the number that actually ran.

    `dry_run=True` performs every step -- the `cd` tracking, the C004 gate,
    the claim parse -- and prints the command and the directory it would run
    in INSTEAD of executing it. That mode exists because this round found
    `sed -i … claim_check.py` classified `auto`: the only safe way to ask
    "what would this tier do to my tree" was a tier that does not do it.

    A Verification fence is read as ONE shell session, so any leading `cd`
    — bare or `cd X && real_command` — moves the working directory for every
    later command in the block. Getting this wrong is not a cosmetic bug:
    `fuzz-mutate-kill-loop` opens with `cd harness && …` and then issues five
    more bare `python3 -m pytest -q tests/…` lines that only resolve from
    inside `harness/`.
    """
    findings = []
    n_executed = 0
    spent = 0.0
    cwd = repo_root
    for cmd in commands:
        m = re.match(r"^\s*cd\s+(\S+)", cmd.command)
        if m:
            resolved = resolve_token(m.group(1).strip("'\""), [cwd, repo_root])
            if resolved and os.path.isdir(resolved):
                if not CD_PREFIX_RE.match(cmd.command):
                    cwd = resolved
                    continue
                # `cd X && rest`: run the whole line from here, then stay in X
                pending_cwd = resolved
            else:
                pending_cwd = None
                if not CD_PREFIX_RE.match(cmd.command):
                    continue        # C001 already reported the bad `cd`
        else:
            pending_cwd = None
        if cmd.kind != "auto":
            if pending_cwd:
                cwd = pending_cwd
            continue
        # Resolve against the directory the command will actually run in.
        # For `cd X && rest`, that is X — not the current cwd. Getting this
        # wrong made the C004 gate skip four real, runnable commands as
        # "absent from this checkout" (`cd harness && pytest tests/…`).
        run_bases = [pending_cwd or cwd, repo_root]
        missing = [t for t in path_tokens(cmd.command)
                   if resolve_token(t, run_bases) is None]
        if missing:
            findings.append(Finding(
                cmd, "C004", "not run here: %s absent from this checkout "
                             "(a portable skill documenting the READER's "
                             "repo, not this one)" % ", ".join(repr(m) for m in missing),
                level="SKIPPED"))
            if pending_cwd:
                cwd = pending_cwd
            continue
        # Round 459. A budget that silently stops is worse than no budget: it
        # reports a clean sweep over a prefix. Every command the budget
        # declines is reported, by name, as its own finding.
        if budget is not None and spent >= budget:
            findings.append(Finding(
                cmd, "C006", "not run: %.0fs budget already spent (%d command"
                             "(s) into this block)" % (spent, n_executed),
                level="BUDGETED"))
            if pending_cwd:
                cwd = pending_cwd
            continue
        wanted = claim_constraints(cmd.claim)
        if not wanted:
            findings.append(Finding(
                cmd, "C003", "claim %r states no checkable number; ran it "
                             "anyway for the exit code only" % cmd.claim,
                level="UNQUANTIFIED"))
        if dry_run:
            print("would run [%s]: %s"
                  % (os.path.relpath(pending_cwd or cwd, repo_root),
                     cmd.command.replace("\n", " ")))
            if pending_cwd:
                cwd = pending_cwd
            continue
        t0 = time.monotonic()
        output, rc = run_command(cmd, repo_root, cwd, timeout)
        elapsed = time.monotonic() - t0
        spent += elapsed
        n_executed += 1
        got = observed_metrics(output, rc)
        mine = []
        for name, (op, want) in sorted(wanted.items()):
            if name not in got:
                mine.append(Finding(
                    cmd, "C002", "claim says %s=%d but the command printed no "
                                 "%s at all" % (name, want, name)))
            elif op == ">=" and got[name] < want:
                mine.append(Finding(
                    cmd, "C002", "claim says %s>=%d, observed %s=%d"
                    % (name, want, name, got[name])))
            elif op == "==" and got[name] != want:
                mine.append(Finding(
                    cmd, "C002", "claim says %s=%d, observed %s=%d"
                    % (name, want, name, got[name])))
        findings.extend(mine)
        if ledger is not None:
            ledger.append({
                "skill": skill, "path": cmd.path, "line": cmd.line_no,
                "command": cmd.command.replace("\n", " ")[:400],
                "claim": cmd.claim[:400], "seconds": round(elapsed, 2),
                "returncode": rc,
                "timed_out": "claim_check: TIMEOUT" in output,
                "wanted": dict((k, "%s%d" % (op, v))
                               for k, (op, v) in sorted(wanted.items())),
                "observed": dict(sorted(got.items())),
                "findings": [f.code for f in mine],
                # the process cwd, not the effective one: a `cd X &&`
                # line carries its own cd and runs from HERE.
                "cwd": os.path.relpath(cwd, repo_root),
            })
        if pending_cwd:
            cwd = pending_cwd
    return findings, n_executed


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def skill_md_paths(path):
    """Every SKILL.md reachable from `path` (file, skill dir, or dir of dirs)."""
    if os.path.isfile(path) and os.path.basename(path) == "SKILL.md":
        return [path]
    if os.path.isdir(path):
        direct = os.path.join(path, "SKILL.md")
        if os.path.isfile(direct):
            return [direct]
        out = []
        for entry in sorted(os.listdir(path)):
            sub = os.path.join(path, entry, "SKILL.md")
            if os.path.isfile(sub):
                out.append(sub)
        return out
    return []


def commands_for(md_path):
    """Parse one SKILL.md and return its classified Verification commands."""
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    # Skip frontmatter so reported line numbers match the real file.
    lines = text.split("\n")
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
    body = "\n".join(lines[body_start:])
    section = verification_section(body)
    if not section:
        return []
    offset = body.index(section) if section else 0
    first_line = body_start + body[:offset].count("\n") + 1
    cmds = parse_commands(section, md_path, first_line)
    for c in cmds:
        c.kind, c.reason = classify(c.command)
    return cmds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT,
                    help="base for resolving repo-relative paths "
                         "(default: the repo this script lives in)")
    ap.add_argument("--list", action="store_true",
                    help="print every command with its auto/manual verdict")
    ap.add_argument("--run", action="store_true",
                    help="execute `auto` commands and diff their real output "
                         "against the claim (never runs `manual` ones)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what --run WOULD execute, and where, without "
                         "executing anything")
    ap.add_argument("--timeout", type=int, default=300,
                    help="per-command timeout in seconds under --run")
    ap.add_argument("--budget", type=float, default=None,
                    help="stop EXECUTING once this many seconds of command "
                         "time have been spent; every declined command is "
                         "still reported, as C006")
    ap.add_argument("--ledger", default=None,
                    help="append one JSON row per executed command to this "
                         "file (the receipt --run has never left behind)")
    args = ap.parse_args(argv)

    md_paths = []
    for p in args.paths:
        found = skill_md_paths(p)
        if not found:
            print("%s: no SKILL.md found here or in immediate subdirectories"
                  % p, file=sys.stderr)
            return 2
        md_paths.extend(found)

    repo_root = os.path.abspath(args.repo_root)
    findings, n_auto, n_manual, reasons = [], 0, 0, {}
    paths_checked = paths_skipped = n_executed = 0
    ledger = [] if args.ledger else None
    budget_left = args.budget
    t_start = time.monotonic()
    for md in md_paths:
        try:
            cmds = commands_for(md)
        except (OSError, UnicodeDecodeError) as e:
            print("%s: cannot read: %s" % (md, e), file=sys.stderr)
            return 2
        for c in cmds:
            if c.kind == "auto":
                n_auto += 1
            else:
                n_manual += 1
                reasons[c.reason.split(":")[0]] = \
                    reasons.get(c.reason.split(":")[0], 0) + 1
            if args.list:
                print("%s:%d: %-6s %s%s" % (
                    c.path, c.line_no, c.kind, c.command.split("\n")[0][:90],
                    "" if c.kind == "auto" else "   [%s]" % c.reason))
        findings.extend(check_bare_expectations(cmds))
        path_findings, checked, skipped = check_paths(cmds, repo_root)
        findings.extend(path_findings)
        paths_checked += checked
        paths_skipped += skipped
        if args.run or args.dry_run:
            before = time.monotonic()
            run_findings, ran = check_by_running(
                cmds, repo_root, args.timeout, dry_run=args.dry_run,
                ledger=ledger, budget=budget_left,
                skill=os.path.basename(os.path.dirname(md)))
            findings.extend(run_findings)
            n_executed += ran
            # The budget is global, so what one skill spends the next one
            # does not have. `check_by_running` gets the REMAINDER.
            if budget_left is not None:
                budget_left = max(0.0, budget_left - (time.monotonic() - before))
            if ledger:
                with open(args.ledger, "a", encoding="utf-8") as fh:
                    for row in ledger:
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                del ledger[:]

    # Once, not once per skill: the registry is a property of the checkout.
    # Deliberately AFTER the loop and before printing, so a C007 lands in the
    # same sorted-by-nothing stream as every other finding and counts toward
    # the same exit code.
    findings.extend(check_absent_registry(repo_root))

    for f in findings:
        print(f)
    n_stale = sum(1 for f in findings if f.level == "STALE")
    n_bare = sum(1 for f in findings if f.level == "UNCOMMENTED")
    n_budgeted = sum(1 for f in findings if f.level == "BUDGETED")
    reason_str = ", ".join("%s %d" % (k, v) for k, v in sorted(reasons.items()))
    print("claim_check: %d skill(s), %d command(s): %d auto-checkable, "
          "%d manual (%s)" % (len(md_paths), n_auto + n_manual, n_auto,
                              n_manual, reason_str or "none"))
    # Round 417. This line is the one `corpus_check.py` quotes and the one
    # `run_driver.sh` therefore logs, and until now the only number on it
    # that a reader could act on was `0 stale`. The denominators were on the
    # line ABOVE it, which no aggregator reads. Two of them matter and they
    # say different things: `paths` is what the static tier really checked,
    # and `commands` is 0 of 264 unless `--run` was passed -- so without
    # `--run` this tool's `0 stale` is zero-of-zero on the command tier, and
    # says so now instead of reading as a clean bill of health.
    # Round 459. These two are recall gaps and must be PUBLISHED, but not
    # last: `TestSummaryCarriesItsDenominators` pins the `coverage` clause as
    # the final line because `corpus_check.run_one` keeps `lines[-1]` for the
    # driver's one-line summary. Round 417 moved the denominators there
    # deliberately; appending after them would evict them from driver.log and
    # re-open the exact hole round 417 closed. `COVERAGE_RE` scans the FULL
    # output, so a line above it is still aggregated -- it is only the
    # 200-character summary that is last-line-only.
    if n_bare or n_budgeted or args.run:
        print("claim_check: %d uncommented expectation(s) invisible to the "
              "number tier; %d command(s) declined by --budget; %.1fs elapsed"
              % (n_bare, n_budgeted, time.monotonic() - t_start))
    n_ran = n_executed
    print("claim_check: %d path(s) resolved, %d unresolvable-by-design "
          "(scratch/created/declared-absent/placeholder/output/unanchored); "
          "%d stale claim(s) of %d "
          "checked; coverage %d/%d paths, %d/%d commands"
          % (paths_checked, paths_skipped, n_stale, paths_checked + n_ran,
             paths_checked, paths_checked + paths_skipped,
             n_ran, n_auto + n_manual))
    return 1 if n_stale else 0


if __name__ == "__main__":
    sys.exit(main())
