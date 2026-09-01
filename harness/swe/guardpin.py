"""Guard pins: falsify the CLAIM that a named test guards a named call.

`mutation.py` asks one question — *did the suite go red?* — and it asks it of
every site it can reach. That is the right question for coverage and the
wrong one for the failure this program keeps finding, which is not "nothing
covers this line" but **"the test we NAME for this behaviour is not the thing
that catches it"**:

* **round 411** — `claim_check.check_paths`'s `cd` branch had its own regex,
  never called the exemption gate, and nothing noticed for 71 rounds. The
  fix's own structural pin says, in its docstring, "Deliberately coarse — it
  cannot prove the call is on the right path." Nothing measured that.
* **round 412** — a test asserted the right verdict *string* while the branch
  it was named after was unreachable behind an earlier one. It passed
  forever without ever reaching its subject.

A **guard pin** is a declaration with three parts: a call site located
SYMBOLICALLY (`path` + `func` + `target`, never a line number — line numbers
rot silently, a symbol that moved makes the pin `unlocatable` and loud), a
falsifying edit, and the pytest node id that is claimed to catch it. The
runner applies the edit to a throwaway copy and requires that test to go RED.

Verdicts
--------
``guarded``        the named test went red. The pin holds.
``misattributed``  the named test stayed GREEN but the wider suite went red.
                   Something guards the call; it is not what the record says.
``unguarded``      named test green AND suite green. Nothing in the declared
                   scope notices the call being neutered.
``wrong_reason``   the named test went red, but the failure text does not
                   contain the pin's declared `expect_in_failure`. Round 412's
                   shape: red, but not for the assertion the pin is about.
``nonviable``      the pin's own test is RED on the UNMUTATED copy. Round
                   349's rule — a verdict against a non-green baseline is not
                   evidence, and it fails in the flattering direction.
``inconclusive``   the mutant run produced no evidence either way (pytest
                   exited 2-5: collection/config error, nothing collected).
``unlocatable``    the site the pin names is not in the file any more.

`keep_call`: the knob the instrument turns on
---------------------------------------------
With ``keep_call=false`` the call's TEXT is replaced by the literal — the
identifier is gone from the file. With ``keep_call=true`` the edit is
``(CALL, LIT)[1]``: the call still runs, its side effects still happen, its
name is still in the source, and only its VALUE is discarded.

A test that greps the source for `foo(` passes the second and fails the
first. A test that exercises the behaviour fails both. Running the same pin
both ways is therefore a measurement of what a structural pin buys, and the
two verdicts differing is not a bug in either — it is the answer.

Why the splice is textual
-------------------------
`mutation.generate` re-unparses every top-level statement, which deletes
every comment in the module. For a mutation SCORE that is harmless. Here it
is a confound: a source-reading test could go red merely because the comments
vanished, and the whole point is to tell a structural pin from a behavioural
one. So `apply_edit` unparses only the smallest enclosing STATEMENT and
splices it back over that statement's own line range, re-indented. Every
other byte of the file — comments included — is unchanged.
"""

import ast
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_HERE = os.path.dirname(os.path.abspath(__file__))

try:                                            # package import
    from .mutation import _copy_project, classify_mutant_run
    from .proc import run_capped
except ImportError:                             # pragma: no cover - script mode
    # `python3 harness/swe/guardpin.py` has no package context, and
    # `mutation.py` itself imports `.proc` relatively — so putting THIS
    # directory on the path is not enough. The parent is, because
    # `harness/swe/__init__.py` makes `swe` a real package.
    sys.path.insert(0, os.path.dirname(_HERE))
    from swe.mutation import _copy_project, classify_mutant_run
    from swe.proc import run_capped


REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
DEFAULT_REGISTRY = os.path.join("state", "swe", "guard-pins.json")

#: `becomes` -> the constant the call's value is replaced by.
BECOMES = {"none": None, "true": True, "false": False}

_STMT_KINDS = {
    "if": (ast.If,), "raise": (ast.Raise,), "expr": (ast.Expr,),
    "assign": (ast.Assign, ast.AnnAssign, ast.AugAssign),
    "for": (ast.For, ast.AsyncFor), "while": (ast.While,),
    "return": (ast.Return,), "with": (ast.With, ast.AsyncWith),
    "try": (ast.Try,), "assert": (ast.Assert,),
}

EDITS = ("call_value", "drop_stmt")


class EquivalentEdit(Exception):
    """The declared edit provably cannot change behaviour.

    The one case that matters here: `keep_call=true` on a call whose value is
    DISCARDED anyway — a bare `f(x)` statement. `(f(x), None)[1]` runs the
    same call for the same side effects and throws away a value nobody read,
    so the mutant is semantically identical to the original. Every test would
    stay green and the tool would report `unguarded` about a call that is
    perfectly well guarded. An equivalent mutant that is reported as a
    finding is worse than no instrument: it is a finding-shaped artefact of
    the tool's own edit.
    """


class PinUnlocatable(Exception):
    """The site a pin names is not in the file (any more). Never silent:
    a pin that cannot find its subject is a FINDING about the pin, and the
    alternative — mutating whatever is at the recorded line number now — is
    how a rotted pin starts reporting confident nonsense."""


# ------------------------------------------------------------------ locating --

def _callee_name(node):
    """Dotted name of a call's callee: `f` -> "f", `a.b.f` -> "a.b.f"."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _callee_name(node.value)
        return (base + "." + node.attr) if base else node.attr
    return ""


def _matches_callee(dotted, target):
    return dotted == target or dotted.endswith("." + target)


def find_function(tree, func):
    """The single `def`/`class.def` named `func`. Ambiguity is an error.

    `func` may be "name" or "Class.method". A name that resolves to two
    different definitions raises rather than picking one: the pin would
    otherwise be silently about whichever the walker reached first.
    """
    want_cls, _, want_fn = func.rpartition(".")
    hits = []

    def walk(node, cls):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name == want_fn and (not want_cls or cls == want_cls):
                    hits.append(child)
                walk(child, cls)
            else:
                walk(child, cls)

    walk(tree, "")
    if not hits:
        raise PinUnlocatable("no function named %r" % func)
    if len(hits) > 1:
        raise PinUnlocatable("%r is ambiguous: %d definitions at lines %s"
                             % (func, len(hits), [h.lineno for h in hits]))
    return hits[0]


def _stmt_parents(fn):
    """id(node) -> INNERMOST enclosing STATEMENT node, for every node in `fn`.

    Innermost, and the word is load-bearing. The first draft of this function
    wrote `if id(child) not in out` — keep the first statement seen — and
    `ast.walk` is BREADTH-first, so the first statement seen is the
    OUTERMOST one. Every call in this module's own registry then resolved to
    the enclosing `for` loop or `if`, and `apply_edit` faithfully re-unparsed
    that whole block: the diff for one two-token edit deleted eleven lines of
    comment and renormalised every string quote in the function.

    Which would not have been a wrong ANSWER — it would have been a wrong
    EXPERIMENT. This module's entire point is telling a source-grep pin from
    a behavioural one, and a splice that deletes the file's comments changes
    the very text a source-grep pin reads. The instrument would have
    manufactured its own findings. Caught by reading `guardpin locate`'s
    diffs before running a single test, which is what that mode is for.

    `ast.walk` still yields outer statements first, so overwriting — rather
    than keeping the first — leaves the deepest statement containing each
    node as its parent.
    """
    out = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.stmt):
            for child in ast.walk(node):
                if child is not node:
                    out[id(child)] = node
    return out


def _in_source_order(nodes):
    return sorted(nodes, key=lambda n: (n.lineno, n.col_offset))


def find_call_sites(fn, target):
    """Every `target(...)` call inside `fn`, in source order."""
    return _in_source_order([n for n in ast.walk(fn)
                             if isinstance(n, ast.Call)
                             and _matches_callee(_callee_name(n.func), target)])


def find_stmt_sites(fn, target, stmt_kind):
    """Every statement of kind `stmt_kind` inside `fn` whose own source
    mentions `target`, in source order. `stmt_kind` is REQUIRED and exact:
    an `if` guard and the `raise` inside it both mention the same name, and
    guessing which one the pin meant is not this tool's job."""
    kinds = _STMT_KINDS.get(stmt_kind)
    if kinds is None:
        raise PinUnlocatable("unknown stmt_kind %r (known: %s)"
                             % (stmt_kind, ", ".join(sorted(_STMT_KINDS))))
    out = []
    for node in ast.walk(fn):
        if node is fn or not isinstance(node, kinds):
            continue
        try:
            if target in ast.unparse(node):
                out.append(node)
        except Exception:                       # pragma: no cover - defensive
            continue
    return _in_source_order(out)


# ------------------------------------------------------------------- editing --

def _literal(becomes):
    if becomes not in BECOMES:
        raise PinUnlocatable("unknown becomes %r (known: %s)"
                             % (becomes, ", ".join(sorted(BECOMES))))
    return ast.Constant(value=BECOMES[becomes])


def _splice(source, stmt, new_text):
    """Replace `stmt`'s own line range in `source` with `new_text`, indented
    to `stmt.col_offset`. Every other byte — comments included — survives."""
    lines = source.splitlines(True)
    start, end = stmt.lineno - 1, stmt.end_lineno       # [start, end)
    pad = " " * stmt.col_offset
    body = "\n".join((pad + ln) if ln else "" for ln in new_text.split("\n"))
    tail = "\n" if lines[end - 1].endswith("\n") else ""
    return "".join(lines[:start]) + body + tail + "".join(lines[end:])


def _span(source, node):
    """(prefix, text, suffix) around `node`'s exact source span.

    `col_offset` is a UTF-8 BYTE offset, not a character index — this repo's
    sources are full of em-dashes — so the slice happens on the encoded line
    and is decoded back.
    """
    lines = source.splitlines(True)
    sl, el = node.lineno - 1, node.end_lineno - 1
    first, last = lines[sl].encode("utf-8"), lines[el].encode("utf-8")
    prefix = "".join(lines[:sl]) + first[:node.col_offset].decode("utf-8")
    suffix = last[node.end_col_offset:].decode("utf-8") + "".join(lines[el + 1:])
    if sl == el:
        text = first[node.col_offset:node.end_col_offset].decode("utf-8")
    else:
        text = (first[node.col_offset:].decode("utf-8")
                + "".join(lines[sl + 1:el])
                + last[:node.end_col_offset].decode("utf-8"))
    return prefix, text, suffix


def apply_edit(source, pin):
    """-> (mutated_source, note). Raises PinUnlocatable if the site is gone."""
    tree = ast.parse(source)
    fn = find_function(tree, pin["func"])
    occ = int(pin.get("occurrence", 1))
    edit = pin["edit"]
    if edit == "call_value":
        sites = find_call_sites(fn, pin["target"])
        what = "call %s(" % pin["target"]
    elif edit == "drop_stmt":
        sites = find_stmt_sites(fn, pin["target"], pin.get("stmt_kind", ""))
        what = "%s-statement mentioning %s" % (pin.get("stmt_kind"), pin["target"])
    else:
        raise PinUnlocatable("unknown edit %r (known: %s)" % (edit, ", ".join(EDITS)))
    if len(sites) < occ:
        raise PinUnlocatable("%s in %s(): wanted occurrence %d, found %d"
                             % (what, pin["func"], occ, len(sites)))
    site = sites[occ - 1]

    if edit == "call_value":
        # The call's OWN source span is replaced, not its enclosing
        # statement's. `keep_call`'s replacement is built from the original
        # text, so for a `call_value` edit not one byte outside the call
        # itself changes — no re-unparsing, no renormalised quotes, and above
        # all no deleted comments. That last one is not tidiness: this
        # module's whole job is telling a source-grep pin apart from a
        # behavioural one, and an edit that rewrites the surrounding comments
        # changes the text a source-grep pin reads.
        parents = _stmt_parents(fn)
        stmt = parents.get(id(site))
        keep = bool(pin.get("keep_call", False))
        if keep and isinstance(stmt, ast.Expr) and stmt.value is site:
            raise EquivalentEdit(
                "keep_call on a bare `%s(...)` statement: the value is "
                "discarded either way, so the edit changes nothing. Use "
                "edit=drop_stmt (stmt_kind=expr) to remove the call instead."
                % pin["target"])
        becomes = pin.get("becomes", "none")
        lit = repr(_literal(becomes).value)
        prefix, call_text, suffix = _span(source, site)
        new_text = ("(%s, %s)[1]" % (call_text, lit)) if keep else lit
        mutated = prefix + new_text + suffix
        note = "%s:%d %s -> %s%s" % (
            os.path.basename(pin["path"]), site.lineno, pin["target"], becomes,
            " (call kept, value discarded)" if keep else " (call text removed)")
    else:
        note = "%s:%d drop %s" % (os.path.basename(pin["path"]), site.lineno, what)
        mutated = _splice(source, site, "pass")
    if mutated == source:
        raise PinUnlocatable("edit is a no-op: the file did not change")
    try:
        ast.parse(mutated)
    except SyntaxError as e:                    # pragma: no cover - defensive
        raise PinUnlocatable("edit produced unparseable source: %s" % e)
    return mutated, note


def edit_diff(source, mutated, context=1):
    """The changed lines, for the record. Small on purpose — a pin's diff is
    one statement and a reader should be able to see it in the summary."""
    import difflib
    rel = difflib.unified_diff(source.splitlines(), mutated.splitlines(),
                               "before", "after", n=context, lineterm="")
    return "\n".join(list(rel)[2:])


# ------------------------------------------------------------------- running --

_PYTEST_BASE = ["-q", "-p", "no:cacheprovider", "-rfE", "--no-header"]


def pytest_cmd(target, extra=()):
    return [sys.executable, "-m", "pytest"] + _PYTEST_BASE + list(extra) + [target]


_FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)


def failed_tests(output):
    return _FAILED_RE.findall(output or "")


def default_suite(pin):
    """A pin's suite defaults to the FILE its named test lives in."""
    return pin.get("suite") or pin["test"].split("::", 1)[0]


def suite_args(pin):
    """Extra pytest args for the SUITE runs only.

    Exists for one measured reason: `languages/whence/tests` holds a
    926-second slow tier behind `-m "not whence_slow"`, and a pin whose suite
    is the whole directory would otherwise time out — which
    `classify_mutant_run` scores as a KILL, i.e. as the pin holding. A cap
    that turns "we did not look" into "we looked and it was caught" is the
    round-349 failure with a different clock.
    """
    return list(pin.get("suite_args") or ())


class _Run(object):
    __slots__ = ("status", "returncode", "seconds", "failed", "tail")

    def __init__(self, status, returncode, seconds, failed, tail):
        self.status, self.returncode = status, returncode
        self.seconds, self.failed, self.tail = seconds, failed, tail

    def as_dict(self):
        return {"status": self.status, "returncode": self.returncode,
                "seconds": round(self.seconds, 2), "failed": self.failed[:12],
                "tail": self.tail[-600:]}


def _run_target(root, target, timeout_s, extra=()):
    cmd = pytest_cmd(target, extra)
    r = run_capped(cmd, root, timeout_s)
    if r.timed_out:
        return _Run("killed", -9, r.seconds, [], "timed out after %.0fs" % timeout_s)
    status = classify_mutant_run(r.returncode, r.output, cmd)
    return _Run(status, r.returncode, r.seconds, failed_tests(r.output),
                (r.output or "").strip()[-2000:])


class _Copy(object):
    """A throwaway copy of the project. Nothing here touches the checkout."""

    def __init__(self, root):
        self.tmp = tempfile.mkdtemp(prefix="guardpin-")
        self.dst = os.path.join(self.tmp, "proj")
        _copy_project(root, self.dst)

    def write(self, rel, text):
        with io.open(os.path.join(self.dst, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Baselines(object):
    """Unmutated-copy verdicts, memoised per pytest target.

    Round 349's rule, applied per pin rather than per campaign: a pin whose
    own test is already red proves nothing about the call, and the failure
    direction is flattering (the mutant looks caught). Deduped because a
    registry with ten pins over three files needs three baselines, not ten.
    """

    def __init__(self, root, timeout_s=300.0):
        self.root, self.timeout_s = root, timeout_s
        self._cache, self._lock = {}, threading.Lock()

    def get(self, target, extra=()):
        key = " ".join([target] + list(extra))
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        copy = _Copy(self.root)
        try:
            run = _run_target(copy.dst, target, self.timeout_s, extra=extra)
        finally:
            copy.close()
        with self._lock:
            self._cache.setdefault(key, run)
            return self._cache[key]

    def as_dict(self):
        with self._lock:
            return {k: v.as_dict() for k, v in self._cache.items()}


class PinResult(object):
    def __init__(self, pin):
        self.pin = pin
        self.verdict = None
        self.note = ""
        self.diff = ""
        self.detail = ""
        self.sole_guardian = None       # only computed when the pin asks
        self.runs = {}
        self.seconds = 0.0

    @property
    def id(self):
        return self.pin.get("id", "?")

    def as_dict(self):
        return {"id": self.id, "verdict": self.verdict, "note": self.note,
                "detail": self.detail, "diff": self.diff,
                "path": self.pin.get("path"), "func": self.pin.get("func"),
                "target": self.pin.get("target"), "edit": self.pin.get("edit"),
                "keep_call": bool(self.pin.get("keep_call", False)),
                "test": self.pin.get("test"), "suite": default_suite(self.pin),
                "why": self.pin.get("why", ""),
                "sole_guardian": self.sole_guardian,
                "seconds": round(self.seconds, 2),
                "runs": {k: v.as_dict() for k, v in self.runs.items()}}


HOLDS = ("guarded",)
FINDINGS = ("misattributed", "unguarded", "wrong_reason")
ERRORS = ("nonviable", "inconclusive", "unlocatable", "equivalent")


def run_pin(pin, root, baselines, timeout_s=300.0):
    """(`timeout_s` is a floor: a pin may raise its own with `timeout_s`,
    because one file in this repo — `test_swe_campaign.py` — is ~900 s and a
    cap that silently kills it would be scored as a KILL, i.e. as the pin
    holding. A timeout is only evidence when the run was allowed to finish.)"""
    """One pin, end to end. Cheap when the pin holds: a `guarded` verdict
    costs the named test twice (baseline + mutant) and never runs the suite.
    Only a pin whose named test stays GREEN pays for the wider scope."""
    res = PinResult(pin)
    timeout_s = max(timeout_s, float(pin.get("timeout_s") or 0))
    t0 = time.time()
    try:
        src_path = os.path.join(root, pin["path"])
        with io.open(src_path, encoding="utf-8") as f:
            source = f.read()
        mutated, note = apply_edit(source, pin)
        res.note = note
        res.diff = edit_diff(source, mutated)
    except EquivalentEdit as e:
        res.verdict, res.detail = "equivalent", str(e)
        res.seconds = time.time() - t0
        return res
    except (PinUnlocatable, IOError, OSError, SyntaxError) as e:
        res.verdict, res.detail = "unlocatable", str(e)
        res.seconds = time.time() - t0
        return res

    base = baselines.get(pin["test"])
    res.runs["baseline_test"] = base
    if base.status != "survived":
        res.verdict = "nonviable"
        res.detail = ("the pin's own test is not green UNMUTATED (%s, rc=%s); "
                      "a verdict against it is not evidence"
                      % (base.status, base.returncode))
        res.seconds = time.time() - t0
        return res

    copy = _Copy(root)
    try:
        copy.write(pin["path"], mutated)
        run = _run_target(copy.dst, pin["test"], timeout_s)
        res.runs["mutant_test"] = run
        if run.status == "error":
            res.verdict = "inconclusive"
            res.detail = ("the named test produced no verdict under the edit "
                          "(pytest rc=%s)" % run.returncode)
        elif run.status in ("killed",):
            expect = pin.get("expect_in_failure")
            if expect and expect not in (run.tail or ""):
                res.verdict = "wrong_reason"
                res.detail = ("the named test went RED but its failure text "
                              "does not contain %r" % expect)
            else:
                res.verdict = "guarded"
                res.detail = "the named test went RED under the edit"
            if res.verdict in ("guarded", "wrong_reason") and pin.get("check_sole"):
                # `guarded` says the named test caught it. It does NOT say the
                # named test is the ONLY thing that would have. Round 411's
                # structural pin and a behavioural test can both be red at
                # once, and a record that stops at the first red cannot tell
                # a load-bearing pin from a redundant one. One extra run,
                # asked for per pin, answers it.
                suite = default_suite(pin)
                sbase = baselines.get(suite, suite_args(pin))
                res.runs["baseline_suite"] = sbase
                if sbase.status != "survived":
                    res.detail += ("; sole-guardian check skipped: %s is not "
                                   "green unmutated" % suite)
                else:
                    rest = _run_target(copy.dst, suite, timeout_s,
                                       extra=suite_args(pin) + ["--deselect", pin["test"]])
                    res.runs["mutant_suite_without_named"] = rest
                    if rest.status == "error":
                        res.detail += "; sole-guardian check inconclusive"
                    else:
                        res.sole_guardian = (rest.status == "survived")
                        res.detail += ("; and it is the ONLY test in %s that "
                                       "goes red" % suite if res.sole_guardian
                                       else "; %d other test(s) in %s catch it too: %s"
                                       % (len(rest.failed), suite,
                                          ", ".join(t.split("::")[-1] for t in rest.failed[:3])))
        else:
            suite = default_suite(pin)
            sbase = baselines.get(suite, suite_args(pin))
            res.runs["baseline_suite"] = sbase
            if sbase.status != "survived":
                res.verdict = "nonviable"
                res.detail = ("the named test is green under the edit and the "
                              "wider suite %s is not green UNMUTATED (%s), so "
                              "misattributed/unguarded cannot be told apart"
                              % (suite, sbase.status))
            else:
                srun = _run_target(copy.dst, suite, timeout_s, extra=suite_args(pin))
                res.runs["mutant_suite"] = srun
                if srun.status == "error":
                    res.verdict = "inconclusive"
                    res.detail = ("the suite produced no verdict under the "
                                  "edit (pytest rc=%s)" % srun.returncode)
                elif srun.status == "killed":
                    res.verdict = "misattributed"
                    res.detail = ("the NAMED test stayed green; %d other "
                                  "test(s) in %s went red: %s"
                                  % (len(srun.failed), suite,
                                     ", ".join(t.split("::")[-1] for t in srun.failed[:4])))
                else:
                    res.verdict = "unguarded"
                    res.detail = ("nothing in %s notices the edit" % suite)
    finally:
        copy.close()
    res.seconds = time.time() - t0
    return res


class GuardPinReport(object):
    def __init__(self, results, seconds, baselines=None):
        self.results = results
        self.seconds = seconds
        self.baselines = baselines

    def by_verdict(self, group):
        return [r for r in self.results if r.verdict in group]

    @property
    def holds(self):
        return self.by_verdict(HOLDS)

    @property
    def findings(self):
        return self.by_verdict(FINDINGS)

    @property
    def errors(self):
        return self.by_verdict(ERRORS)

    @property
    def score(self):
        """Pins that hold / pins that produced EVIDENCE. Errors are excluded
        from the denominator on purpose and reported separately: an
        unlocatable pin is a fact about the registry, not about the suite,
        and averaging the two hides both."""
        n = len(self.holds) + len(self.findings)
        return len(self.holds) / n if n else 0.0

    def summary(self):
        lines = ["guardpin: %d pin(s), %d guarded, %d finding(s), %d error(s), "
                 "score %.0f%% (%.0fs)"
                 % (len(self.results), len(self.holds), len(self.findings),
                    len(self.errors), 100 * self.score, self.seconds)]
        for r in self.results:
            lines.append("  %-13s %-6s %s" % (r.verdict, r.id, r.note or r.pin.get("target", "")))
            if r.verdict != "guarded" or r.sole_guardian is not None:
                lines.append("      %s" % r.detail)
        return "\n".join(lines)

    def as_dict(self):
        return {"pins": len(self.results), "guarded": len(self.holds),
                "findings": len(self.findings), "errors": len(self.errors),
                "score": round(self.score, 4), "seconds": round(self.seconds, 1),
                "results": [r.as_dict() for r in self.results],
                "baselines": self.baselines.as_dict() if self.baselines else {}}


REQUIRED_FIELDS = ("id", "path", "func", "edit", "target", "test", "why")


def validate(pins):
    """-> list of complaints. A registry that does not validate never runs:
    a malformed pin that silently mutates nothing would report `guarded` for
    every test in the file."""
    problems, seen = [], set()
    for i, p in enumerate(pins):
        where = p.get("id") or "#%d" % i
        for f in REQUIRED_FIELDS:
            if not p.get(f):
                problems.append("%s: missing %r" % (where, f))
        if p.get("id") in seen:
            problems.append("%s: duplicate id" % where)
        seen.add(p.get("id"))
        if p.get("edit") not in EDITS:
            problems.append("%s: unknown edit %r" % (where, p.get("edit")))
        if p.get("edit") == "call_value" and p.get("becomes", "none") not in BECOMES:
            problems.append("%s: unknown becomes %r" % (where, p.get("becomes")))
        if p.get("edit") == "drop_stmt":
            if p.get("stmt_kind") not in _STMT_KINDS:
                problems.append("%s: drop_stmt needs a known stmt_kind, got %r"
                                % (where, p.get("stmt_kind")))
            if p.get("keep_call"):
                problems.append("%s: keep_call is meaningless for drop_stmt" % where)
        if "::" not in (p.get("test") or ""):
            problems.append("%s: `test` must be a pytest node id (file::test)" % where)
    return problems


def load_registry(path):
    with io.open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["pins"] if isinstance(data, dict) else data


def run_registry(pins, root=REPO_ROOT, workers=3, timeout_s=300.0, on_result=None):
    problems = validate(pins)
    if problems:
        raise ValueError("registry does not validate:\n  " + "\n  ".join(problems))
    baselines = Baselines(root, timeout_s)
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for res in ex.map(lambda p: run_pin(p, root, baselines, timeout_s), pins):
            results.append(res)
            if on_result:
                on_result(res)
    return GuardPinReport(results, time.time() - t0, baselines)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("check", "locate", "run"))
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--root", default=REPO_ROOT)
    ap.add_argument("--only", action="append", default=[],
                    help="pin id (repeatable)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout-s", type=float, default=300.0)
    ap.add_argument("--json")
    a = ap.parse_args(argv)

    reg = a.registry if os.path.isabs(a.registry) else os.path.join(a.root, a.registry)
    pins = load_registry(reg)
    if a.only:
        pins = [p for p in pins if p.get("id") in set(a.only)]
        if not pins:
            print("no pin matched %s" % a.only)
            return 2

    if a.mode == "check":
        problems = validate(pins)
        for p in problems:
            print("INVALID %s" % p)
        print("guardpin check: %d pin(s), %d problem(s)" % (len(pins), len(problems)))
        return 1 if problems else 0

    if a.mode == "locate":
        # Offline and free: resolve every pin and print its diff. Catches a
        # rotted registry without running one test.
        bad = 0
        for p in pins:
            try:
                with io.open(os.path.join(a.root, p["path"]), encoding="utf-8") as f:
                    src = f.read()
                mutated, note = apply_edit(src, p)
                print("OK      %-6s %s" % (p["id"], note))
                print(edit_diff(src, mutated, context=0))
            except Exception as e:
                bad += 1
                print("ROTTED  %-6s %s" % (p.get("id"), e))
        print("guardpin locate: %d pin(s), %d rotted" % (len(pins), bad))
        return 1 if bad else 0

    rep = run_registry(pins, a.root, a.workers, a.timeout_s,
                       on_result=lambda r: print("%-13s %-6s %.0fs"
                                                 % (r.verdict, r.id, r.seconds), flush=True))
    print(rep.summary())
    if a.json:
        with io.open(a.json, "w", encoding="utf-8") as f:
            json.dump(rep.as_dict(), f, indent=1)
    return 1 if (rep.errors or rep.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
