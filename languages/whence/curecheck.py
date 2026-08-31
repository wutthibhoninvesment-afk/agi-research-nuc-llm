#!/usr/bin/env python3
"""curecheck.py --- does FOLLOWING a Whence parse error's cure fix the program?

Round 386, language(C). Decision 32 (v0.22, round 354) says *an error that
can name the fix, names it*, and round 354 measured itself honestly: of the
ten machine-written Whence programs in `examples/` that fail to parse, ONE
named a cure before v0.22 and NINE did after; v0.23 took it to ten. That
number counts **cures NAMED**. Nothing in thirty rounds has counted **cures
FOLLOWED** --- whether a reader who does what the message says ends up with
a program that runs.

This module measures the second number. It is deliberately a separate
question from the first, and it does not revise it: `9/10 -> 10/10` was and
remains a true statement about naming.

The strict operational form of "sufficient" used here:

    A cure is MECHANICAL if the error message --- its body, its
    parenthetical hint, its line and its column --- determines a unique
    edit to the source text, with no appeal to knowledge of Whence that
    the message does not itself contain.

`CURES` below is the table of every cure the parser can name, each with the
determinacy verdict and, for the mechanical ones, an applier whose ONLY
licence is the transformation the hint's own example demonstrates. Each
rule records that licence in `derivation`, so the claim "this edit follows
from the message" is auditable rather than asserted.

Anti-rot: every rule keys on a hint constant IMPORTED from `whence.parser`,
never on a copy of its wording. If a future round rewords a hint, the
import still resolves, the trigger still fires, and
`tests/test_v33.py::test_every_parser_hint_has_a_cure_rule` is what fails ---
loudly, in the fast tier --- rather than this file silently classifying a
message it no longer recognises. That is round 385's lesson in this file's
own key: a rule whose effect is to stop measuring something can never be
checked by the thing it stopped measuring, so the check lives outside it.

Usage
-----
    python3 curecheck.py rules                 # the determinacy table
    python3 curecheck.py apply FILE            # mechanical cure loop, one file
    python3 curecheck.py corpus [--json OUT]   # the whole field corpus
    python3 curecheck.py replay LEDGER         # replay a hand-authored ledger
    python3 curecheck.py verify DIR            # re-run cured copies

`corpus` NEVER writes to the files it reads. The field programs belong to a
separate autonomous system (see `state/known-standing-dirty-paths.json`);
every cure is applied to an in-memory copy.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from whence import parser as P                              # noqa: E402
from whence.lexer import LexError                           # noqa: E402
from whence.parser import ParseError, parse                 # noqa: E402
from whence.foreign import FOREIGN_NAMES                    # noqa: E402


# --- determinacy taxonomy -------------------------------------------------
#
# Four verdicts, and the three failing ones are NOT the same failure. That
# distinction is the point of this file: "the hint is vague" is not a
# finding, "the hint omits the block's extent" is.

MECHANICAL = "mechanical"
#: names the construct, not where it ends --- you cannot place the closer.
UNDER_EXTENT = "under-extent"
#: offers two or more edits and does not say which one applies here.
UNDER_CHOICE = "under-choice"
#: demands a construct and says nothing about what goes inside it.
UNDER_CONTENT = "under-content"
#: no hint at all --- the message states what stopped the parse and stops.
NO_CURE = "no-cure"
#: a hint this table does not know. NOT the same as `NO_CURE`, and the
#: distinction is the whole anti-rot property: a parser that grows an
#: eighth hint must show up here as an unclassified one, loudly, rather
#: than being counted as "the error named no cure" --- which would read as
#: a finding about the LANGUAGE when it is a fact about this file being
#: stale. Round 385 spent a round on a boundary that stopped the evidence
#: from being collected; this is the same failure available in one line.
UNCLASSIFIED = "unclassified-hint"

_UNDER = (UNDER_EXTENT, UNDER_CHOICE, UNDER_CONTENT)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


#: v0.33's clause is one of `FOREIGN_NAMES`' own sentences, verbatim, so
#: the matcher is the table --- not a copy of any wording in it.
_FOREIGN_PATTERN = None       # built below, once `FOREIGN_NAMES` is read


def _template_pattern(template):
    """A matcher for a hint that is a `%s` template, built FROM the template.

    `_SEPARATOR_HINT` is the one hint in `parser.py` that interpolates the
    offending token, so no exact string can identify it. Deriving the
    pattern by splitting the imported template on its own `%s` keeps the
    anti-rot property the other six get for free: reword the template and
    this pattern follows it; delete the `%s` and it still works.
    """
    return re.compile("".join(re.escape(part) if i % 2 == 0 else ".*"
                              for i, part in
                              enumerate(re.split(r"%s", template))))


class Cure(object):
    """One cure the parser can name, and what following it costs."""

    def __init__(self, key, hint, trigger, determinacy, derivation,
                 missing=None, applier=None):
        self.key = key
        #: the hint's text, imported from `whence.parser` --- never a copy.
        self.hint = hint
        #: matched against the message BODY (the part before the hint).
        self.trigger = trigger
        self.determinacy = determinacy
        #: why the applier's edit follows from the message, in one sentence.
        self.derivation = derivation
        #: for the non-mechanical ones: the datum the message does not carry.
        self.missing = missing
        self._applier = applier
        if (determinacy == MECHANICAL) != (applier is not None):
            raise ValueError("%s: mechanical iff an applier exists" % key)
        if (determinacy in _UNDER) != (missing is not None):
            raise ValueError("%s: under-determined iff `missing` is set" % key)

    def matches(self, body, hint):
        """Does this rule own the error `(body, hint)`?

        BOTH halves must agree, and the hint is the load-bearing half. Two
        pairs of rules in `CURES` share a body pattern and are told apart
        only by their hint: `two statements on one line` carries either
        `_SEPARATOR_HINT` (mechanical) or `_JUXTAPOSE_HINT` (under-choice)
        depending on what the parser found at the column, and `expected X,
        got Y` carries either `_BRACE_HINT` or `_JUXTAPOSE_HINT`. Matching
        on the body alone would collapse each pair onto whichever rule this
        list happens to hold first --- a classifier whose answer depends on
        its own source order, which is not a classifier.

        `hint` may be an exact string, a compiled pattern (for the one hint
        that is a `%s` template), or None for "this rule does not care".
        """
        if self.hint is not None:
            if hint is None:
                return False
            if hasattr(self.hint, "search"):
                if not self.hint.search(hint):
                    return False
            elif hint != self.hint:
                return False
        return bool(self.trigger.search(body))

    def apply(self, lines, line, col, body, hint):
        return self._applier(lines, line, col, body, hint)


# --- the mechanical appliers ---------------------------------------------
#
# Each of these is licensed by exactly one sentence of one hint, quoted in
# the rule's `derivation`. None of them may consult the grammar.

def _apply_assignment(lines, line, col, body, hint):
    """`x = 2` -> `let x = 2`.

    Licence: the hint's example is `let name = value`, which shows `let`
    immediately before the name. The message's column is the `=`. So the
    name is the identifier that ends where the `=` begins.
    """
    text = lines[line - 1]
    i = col - 1                          # 0-based index of the `=`
    j = i
    while j > 0 and text[j - 1].isspace():
        j -= 1
    k = j
    while k > 0 and (text[k - 1].isalnum() or text[k - 1] == "_"):
        k -= 1
    if k == j or not _IDENT.match(text[k:j]):
        return None                      # no name before the `=` --- decline
    out = list(lines)
    out[line - 1] = text[:k] + "let " + text[k:]
    return out


def _apply_record(lines, line, col, body, hint):
    """`{a: 1}` -> `@{a: 1}`.

    Licence: the hint prints both spellings side by side, and the only
    difference between them is an `@` before the `{`. The message's column
    is the `:`; in the hint's own example the `{` is the one that opens the
    text the `:` sits in, so: the nearest preceding `{` that is not already
    preceded by `@`.
    """
    li, ci = line - 1, col - 1
    while li >= 0:
        text = lines[li]
        start = ci if li == line - 1 else len(text)
        b = text.rfind("{", 0, start)
        while b != -1:
            if b == 0 or text[b - 1] != "@":
                out = list(lines)
                out[li] = text[:b] + "@{" + text[b + 1:]
                return out
            b = text.rfind("{", 0, b)
        li -= 1
    return None


def _apply_separator(lines, line, col, body, hint):
    """`a b` (two statements) -> `a` NEWLINE `b`.

    Licence: the hint ends `--- start `X` on the next line`, and `X` is the
    token the column points at. Splitting the line immediately before that
    column starts `X` on the next line and changes nothing else. The new
    line copies the old one's leading whitespace, which is not licensed by
    the hint and is not load-bearing --- Whence has no indentation rule ---
    but keeps the file readable for whoever reads the trace.
    """
    text = lines[line - 1]
    i = col - 1
    if i <= 0 or i >= len(text):
        return None
    head = text[:i].rstrip()
    tail = text[i:]
    if not head or not tail.strip():
        return None
    indent = text[:len(text) - len(text.lstrip())]
    out = list(lines)
    out[line - 1:line] = [head, indent + tail]
    return out


# --- the table ------------------------------------------------------------

class _ExactSet(object):
    """Matches a hint that IS one of the table's sentences. `search` so it
    can sit in `Cure.hint` beside `_template_pattern`'s compiled regex."""

    def __init__(self, sentences):
        self._set = frozenset(sentences)

    def search(self, hint):
        return hint in self._set


_FOREIGN_PATTERN = _ExactSet(FOREIGN_NAMES.values())


CURES = [
    Cure(
        key="assignment",
        hint=P._SYNTAX_HINTS["="],
        trigger=re.compile(r"^unexpected '='"),
        determinacy=MECHANICAL,
        derivation="the hint's example `let name = value` puts `let` before "
                   "the name; the column is the `=`, so the name is the "
                   "identifier ending at it",
        applier=_apply_assignment,
    ),
    Cure(
        key="record-literal",
        hint=P._RECORD_HINT,
        trigger=re.compile(r"^unexpected ':'"),
        determinacy=MECHANICAL,
        derivation="the hint prints `@{a: 1}` beside `{a: 1}`; the sole "
                   "difference is an `@`, and the `{` to put it on is the "
                   "one the `:` sits inside",
        applier=_apply_record,
    ),
    Cure(
        key="missing-separator",
        hint=_template_pattern(P._SEPARATOR_HINT),
        trigger=re.compile(r"^two statements on one line"),
        determinacy=MECHANICAL,
        derivation="the hint ends `start `X` on the next line` and the "
                   "column is where `X` starts, so the edit is a line break "
                   "at that column",
        applier=_apply_separator,
    ),
    Cure(
        key="braced-block",
        hint=P._BRACE_HINT,
        trigger=re.compile(r"^expected '\{', got "),
        determinacy=UNDER_EXTENT,
        derivation="the hint shows `if c { a } else { b }`, which places an "
                   "opening brace at the column --- and a closing brace at a "
                   "position the message never mentions",
        missing="where the block ENDS. The message gives one position, and "
                "a braced block needs two. `else\\n  x + y` and `else\\n  x\\n"
                "  y` differ only in the extent, and the message is identical "
                "for both.",
    ),
    Cure(
        key="juxtaposition",
        hint=P._JUXTAPOSE_HINT,
        trigger=re.compile(r"^(expected .*, got |two statements on one line)"),
        determinacy=UNDER_CHOICE,
        derivation="the hint names TWO spellings --- `a call is `f(x)`` and "
                   "`text must be quoted` --- for one position",
        missing="WHICH of the two edits applies. `print(Calculating total)` "
                "wants quotes and `f x` wants parentheses, and the message "
                "is word-for-word identical for both.",
    ),
    Cure(
        key="rescue-infix",
        hint=P._SYNTAX_HINTS["rescue"],
        trigger=re.compile(r"^unexpected 'rescue'"),
        determinacy=UNDER_EXTENT,
        derivation="the hint's example `risky rescue fallback` is a "
                   "REORDERING of three spans, and the message locates only "
                   "the `rescue`",
        missing="where `risky` and `fallback` begin and end. The column is "
                "the `rescue` keyword; the two operands it must sit between "
                "are spans the message never delimits, and in the field "
                "corpus they cross lines and carry a `catch ... as err` "
                "binder the target form has no place for.",
    ),
    Cure(
        key="foreign-word",
        hint=_FOREIGN_PATTERN,
        trigger=re.compile(r""),
        determinacy=UNDER_EXTENT,
        derivation="v0.33 names the foreign word and the Whence construct "
                   "that replaces it --- two constructs, and no span",
        missing="what to REWRITE. Every one of the table's sentences that "
                "can reach a parse error names a construct swap (`for`/"
                "`while` -> `map`/`filter`/`fold`, `catch`/`try` -> `risky "
                "rescue fallback`, `return` -> a block's last expression), "
                "not an edit at a position. This is a strictly better "
                "message than the one it replaces and it is still not "
                "mechanical --- naming the right construct is not the same "
                "as determining the edit, which is this round's whole "
                "finding stated about its own fix.",
    ),
    Cure(
        key="if-requires-else",
        hint="every expression has a value",
        trigger=re.compile(r"^'if' requires 'else'"),
        determinacy=UNDER_CONTENT,
        derivation="the message states a requirement and gives the reason "
                   "(`every expression has a value`) but shows no example "
                   "and names no value",
        missing="WHAT the else branch should evaluate to. The message "
                "establishes that a value is needed and is silent on which "
                "one; nothing in it distinguishes `else { 0 }` from `else "
                "{ miss(\"...\") }`.",
    ),
]

_BY_KEY = dict((c.key, c) for c in CURES)


# --- reading an error -----------------------------------------------------

_AT = re.compile(r"^(?P<msg>.*) at line (?P<line>\d+), col (?P<col>\d+)\Z",
                 re.S)


def split_message(rendered):
    """`body (hint) at line L, col C` -> `(body, hint_or_None, line, col)`.

    This is the reader's view and nothing more: the string `run.py` prints
    after `error: `. It does not touch the exception object's attributes,
    because a reader does not have them.
    """
    m = _AT.match(rendered)
    if not m:
        return rendered, None, None, None
    msg = m.group("msg")
    line, col = int(m.group("line")), int(m.group("col"))
    if msg.endswith(")"):
        depth = 0
        for i in range(len(msg) - 1, -1, -1):
            if msg[i] == ")":
                depth += 1
            elif msg[i] == "(":
                depth -= 1
                if depth == 0:
                    return msg[:i].rstrip(), msg[i + 1:-1], line, col
    return msg, None, line, col


def classify(rendered):
    """Which cure, if any, this message names. `NO_CURE` when none does."""
    body, hint, line, col = split_message(rendered)
    if line is None:
        return None, body, hint, line, col
    for cure in CURES:
        if cure.matches(body, hint):
            return cure, body, hint, line, col
    return None, body, hint, line, col


def determinacy_of(cure, hint):
    """`NO_CURE` when the message carried no hint, `UNCLASSIFIED` when it
    carried one this table does not own."""
    if cure is not None:
        return cure.determinacy
    return NO_CURE if hint is None else UNCLASSIFIED


def parse_error_of(text):
    """The rendered first error of `text`, or None if it parses."""
    try:
        parse(text)
    except (ParseError, LexError) as e:
        return str(e)
    return None


# --- the cure loop --------------------------------------------------------

MAX_STEPS = 40


def cure_loop(text, max_steps=MAX_STEPS):
    """Follow every MECHANICAL cure until something stops us.

    Returns `(final_text, steps, outcome)`. `outcome` is one of:
      `parses`          --- no parse error is left
      `stalled`         --- the next cure is under-determined (or absent)
      `no-progress`     --- an applier declined, or produced the same text
      `budget`          --- `max_steps` mechanical edits and still failing
    """
    steps = []
    lines = text.split("\n")
    for _ in range(max_steps):
        rendered = parse_error_of("\n".join(lines))
        if rendered is None:
            return "\n".join(lines), steps, "parses"
        cure, body, hint, line, col = classify(rendered)
        step = {
            "error": rendered,
            "body": body,
            "hint": hint,
            "line": line,
            "col": col,
            "cure": cure.key if cure else None,
            "determinacy": determinacy_of(cure, hint),
        }
        if cure is None or cure.determinacy != MECHANICAL:
            steps.append(step)
            return "\n".join(lines), steps, "stalled"
        out = cure.apply(lines, line, col, body, hint)
        if out is None or out == lines:
            step["declined"] = True
            steps.append(step)
            return "\n".join(lines), steps, "no-progress"
        after = parse_error_of("\n".join(out))
        _, _, _, nline, _ = classify(after) if after else (None, None, None, None, None)
        step["applied"] = True
        step["next_line"] = nline
        # P11's monotonicity claim, recorded per step rather than asserted.
        step["moved_backwards"] = (nline is not None and nline < line)
        steps.append(step)
        lines = out
    return "\n".join(lines), steps, "budget"


def replay(ledger, root=None):
    """Replay a hand-authored cure ledger, recording every error on the way.

    The mechanical loop (`cure_loop`) answers "can a machine follow the
    message?" and its answer is 0 of 10. This answers the other half ---
    "can a READER?" --- without letting the answer be anecdotal. Each entry
    is a literal search/replace plus the cure it answers and the
    information the reader had to supply that the message did not; applying
    them in order and re-parsing between each is what turns a session of
    hand-editing into a number anyone can re-derive.

    An entry whose `old` is not present is a hard error, not a skip: a
    ledger that has drifted from the corpus must fail loudly. The corpus is
    a separate system's and CAN change under us --- `field_programs` reads
    it from git every time for the same reason.
    """
    root = root or _HERE
    by_file = {}
    for e in ledger:
        by_file.setdefault(e["file"], []).append(e)
    rows = []
    for name, edits in sorted(by_file.items()):
        path = os.path.join(root, "examples", name)
        with open(path) as fh:
            text = fh.read()
        seen = []
        for e in edits:
            err = parse_error_of(text)
            if err is not None:
                cure, body, hint, line, col = classify(err)
                seen.append({"error": err, "line": line,
                             "cure": cure.key if cure else None,
                             "determinacy": determinacy_of(cure, hint),
                             "answers": e["answers"], "needed": e["needed"]})
            if e["old"] not in text:
                raise SystemExit("ledger drift: %s: %r not found"
                                 % (name, e["old"][:60]))
            text = text.replace(e["old"], e["new"], 1)
        final_err = parse_error_of(text)
        # Which edits fixed a mistake the GRAMMAR ACCEPTS? Not "which ones
        # happened after the file started parsing" --- an edit can answer no
        # error while other errors are still outstanding elsewhere in the
        # file, and in `whenceguard_v2.lang` most of them do. The claim is
        # per-edit and is tested per-edit: put that ONE edit back into the
        # fully cured file and ask whether the result still parses. If it
        # does, no message about it was ever available to the author.
        accepted = []
        if final_err is None:
            for e in edits:
                if e["new"] not in text:
                    continue
                reverted = text.replace(e["new"], e["old"], 1)
                if parse_error_of(reverted) is None:
                    accepted.append(e["old"].strip().split("\n")[0][:70])
        tmp = os.path.join("/tmp", "curecheck-assisted-" + name)
        with open(tmp, "w") as fh:
            fh.write(text)
        rc = strict = None
        if final_err is None:
            rc, _ = run_program(tmp)
            strict, _ = run_program(tmp, strict=True)
        rows.append({"file": name, "edits": len(edits),
                     "parse_errors_seen": seen,
                     "edits_for_accepted_text": accepted,
                     "n_accepted": len(accepted),
                     "final_error": final_err, "rc": rc, "strict_rc": strict,
                     "cured_path": tmp})
    return rows


def run_program(path, timeout=90, strict=False):
    """`python3 run.py path` --- returncode and the tail of its output."""
    proc = subprocess.run(
        [sys.executable, os.path.join(_HERE, "run.py")]
        + (["--strict-miss"] if strict else []) + [path],
        cwd=_HERE, capture_output=True, text=True, timeout=timeout,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


# --- the corpus -----------------------------------------------------------

def field_programs(root=None):
    """The untracked `.lang` files a separate system leaves in `examples/`.

    Derived from `git ls-files --others`, not from a list in this file: a
    hard-coded list is exactly the kind of name-for-a-fact round 385 spent
    a round on. If the gateway adds a program tomorrow this picks it up.
    """
    root = root or _HERE
    proc = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "examples"],
        cwd=root, capture_output=True, text=True,
    )
    names = [n for n in proc.stdout.split("\n") if n.endswith(".lang")]
    return sorted(os.path.join(root, n) for n in names)


# There is deliberately NO `tracked_programs()` here. It would have been
# four lines and it would have been a FOURTH copy of the `"git",
# "ls-files", "examples"` literal that
# `harness/tests/test_pristine_check.py::test_the_curated_corpus_rule_is_
# duplicated_only_where_declared` pins --- a pin round 385 watched fire on
# the third copy, after the fact, because `git grep` cannot see an
# uncommitted file. Reading it before writing the copy is the whole point
# of having it. This round has no use for the tracked corpus that the field
# corpus does not serve better, so the honest answer is not to make the
# copy and argue for it; `--others` above does not contain the literal.


def survey(paths, max_steps=MAX_STEPS):
    rows = []
    for path in paths:
        with open(path) as fh:
            text = fh.read()
        first = parse_error_of(text)
        row = {"file": os.path.basename(path), "first_error": first}
        if first is None:
            rc, out = run_program(path)
            row.update(parses=True, rc=rc, outcome="parses-unedited",
                       steps=[], applied=0)
        else:
            cured, steps, outcome = cure_loop(text, max_steps)
            row.update(parses=False, outcome=outcome, steps=steps,
                       applied=sum(1 for s in steps if s.get("applied")))
            if outcome == "parses":
                tmp = os.path.join("/tmp", "curecheck-" + row["file"])
                with open(tmp, "w") as fh:
                    fh.write(cured)
                rc, out = run_program(tmp)
                row["rc"] = rc
        rows.append(row)
    return rows


# --- reporting ------------------------------------------------------------

def _fmt_rules():
    lines = ["%-18s %-14s %s" % ("cure", "determinacy", "trigger")]
    lines.append("-" * 74)
    for c in CURES:
        lines.append("%-18s %-14s %s" % (c.key, c.determinacy,
                                         c.trigger.pattern))
    n_mech = sum(1 for c in CURES if c.determinacy == MECHANICAL)
    lines.append("")
    lines.append("%d cure(s): %d mechanical, %d under-determined "
                 "(%s)" % (len(CURES), n_mech, len(CURES) - n_mech,
                           ", ".join(sorted(set(c.determinacy for c in CURES
                                                if c.determinacy != MECHANICAL)))))
    return "\n".join(lines)


def _fmt_survey(rows):
    out = []
    hdr = "%-28s %-6s %-16s %-4s %s" % ("file", "edits", "outcome", "rc",
                                        "stopped by")
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        stopper = ""
        if r["steps"]:
            last = r["steps"][-1]
            if not last.get("applied"):
                stopper = "%s @L%s" % (last["determinacy"], last["line"])
        out.append("%-28s %-6d %-16s %-4s %s" % (
            r["file"], r["applied"], r["outcome"],
            r.get("rc", "-"), stopper))
    total = len(rows)
    reached = sum(1 for r in rows if r.get("rc") == 0)
    parses = sum(1 for r in rows if r["outcome"] in ("parses", "parses-unedited"))
    out.append("")
    out.append("%d file(s): %d parse, %d reach a value (rc=0), "
               "%d mechanical edit(s) applied in total"
               % (total, parses, reached,
                  sum(r["applied"] for r in rows)))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("rules")
    a = sub.add_parser("apply")
    a.add_argument("file")
    a.add_argument("--out", help="write the cured text here")
    c = sub.add_parser("corpus")
    c.add_argument("--json", help="write the full trace here")
    v = sub.add_parser("verify")
    v.add_argument("dir")
    r = sub.add_parser("replay")
    r.add_argument("ledger")
    r.add_argument("--json")
    args = ap.parse_args(argv)

    if args.cmd == "rules":
        print(_fmt_rules())
        return 0
    if args.cmd == "apply":
        with open(args.file) as fh:
            text = fh.read()
        cured, steps, outcome = cure_loop(text)
        for i, s in enumerate(steps, 1):
            print("%d. [%s] %s" % (i, s["determinacy"], s["error"]))
            if not s.get("applied"):
                cure = _BY_KEY.get(s["cure"] or "")
                if cure is not None and cure.missing:
                    print("   missing: %s" % cure.missing)
        print("outcome: %s (%d mechanical edit(s))"
              % (outcome, sum(1 for s in steps if s.get("applied"))))
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(cured)
        return 0 if outcome == "parses" else 1
    if args.cmd == "corpus":
        paths = field_programs()
        rows = survey(paths)
        print(_fmt_survey(rows))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump(rows, fh, indent=2)
        return 0
    if args.cmd == "replay":
        with open(args.ledger) as fh:
            rows = replay(json.load(fh))
        hdr = ("%-28s %-6s %-8s %-8s %-5s %s"
               % ("file", "edits", "errors", "accepted", "rc", "strict"))
        print(hdr); print("-" * len(hdr))
        for r in rows:
            print("%-28s %-6d %-8d %-8d %-5s %s"
                  % (r["file"], r["edits"], len(r["parse_errors_seen"]),
                     r["n_accepted"], r["rc"], r["strict_rc"]))
        ok = sum(1 for r in rows if r["rc"] == 0)
        clean = sum(1 for r in rows if r["strict_rc"] == 0)
        errs = sum(len(r["parse_errors_seen"]) for r in rows)
        acc = sum(r["n_accepted"] for r in rows)
        det = collections.Counter(s["determinacy"]
                                  for r in rows for s in r["parse_errors_seen"])
        print()
        print("%d file(s): %d reach a value, %d clean under --strict-miss"
              % (len(rows), ok, clean))
        uniq = len(set((r["file"], s["error"])
                       for r in rows for s in r["parse_errors_seen"]))
        print("%d edit(s); %d parse-error observation(s) on the way, %d of "
              "them distinct" % (sum(r["edits"] for r in rows), errs, uniq))
        print("%d edit(s) fixed text the grammar ACCEPTS --- no message "
              "about them was ever available" % acc)
        print("determinacy of the %d errors seen: %s"
              % (errs, ", ".join("%s=%d" % kv for kv in sorted(det.items()))))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump(rows, fh, indent=2)
        return 0
    if args.cmd == "verify":
        names = sorted(n for n in os.listdir(args.dir) if n.endswith(".lang"))
        bad = 0
        for n in names:
            path = os.path.join(args.dir, n)
            rc, out = run_program(path)
            tail = [l for l in out.strip().split("\n") if l.strip()]
            print("%-28s rc=%-3d %s" % (n, rc, tail[-1][:90] if tail else ""))
            if rc != 0:
                bad += 1
        print("\n%d file(s): %d reach a value, %d do not"
              % (len(names), len(names) - bad, bad))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
