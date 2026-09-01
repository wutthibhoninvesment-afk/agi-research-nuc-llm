#!/usr/bin/env python3
"""checkpin — guard pins for the GUEST's own `check` statements.

Round 414 (language C). `state/research-state.md` next-step item 8 carries
round 408's item 2 verbatim:

    A check whose name states a mechanism should fail when the mechanism
    goes. `self_host.lang`'s quote-switching check passed straight through
    the deletion of quote-switching. The sweep is mechanical and cheap:
    every `check "<name>"` in the two guest files whose name asserts a RULE,
    asked whether any program in the file can distinguish that rule from its
    replacement.

`harness/swe/guardpin.py` (round 413) is the same instrument one level up:
it edits HOST Python and requires a named pytest node to go red. It cannot
reach this class at all, because `examples/self_host.lang` is a Whence lexer
and parser written IN WHENCE and its guardians are `check "<label>": expr`
statements, not pytest node ids. Mutating `whence/parser.py` does not touch
the guest parser; mutating the guest parser is not something `ast` can do.

So the three parts of a *check pin* are:

    site        a GUEST function (or a single guest source line)
    edit        a replacement that removes the RULE the label names
    guardian    the `check` label claimed to catch it

and the runner applies the edit to a throwaway copy, runs the file, and
requires that label to go from PASS to FAIL.

Why this is cheaper than the host instrument
--------------------------------------------
`python3 run.py examples/self_host.lang` runs all 154 checks in 3.3 s and
`Interpreter.checks` is a list of `{label, line, ok, note}` records. So ONE
run per pin yields the verdict for the named guardian AND the verdict for
every other check in the file — the co-red census that `guardpin.check_sole`
has to pay a second suite run for. Specificity is free here; see `n_red`.

The verdicts, and why two of them are not credit
------------------------------------------------
`guarded`        the named check went PASS -> FAIL. The claim holds.
`wrong_reason`   it failed, but its note does not contain `expect_in_note`.
                 Round 412's shape: red is two claims stacked (it noticed,
                 and it noticed THIS), and only the second survives a
                 refactor.
`shadowed`       the named check stayed GREEN and other checks went red.
                 Something in the file distinguishes the rule; not the
                 thing the record names. (`guardpin`'s `misattributed`.)
`inert`          the named check stayed green and NOTHING went red. The
                 file cannot tell the rule from its replacement at all.
                 This is round 408's finding, found mechanically.
`collapsed`      the run produced NO check records — a parse error, a lex
                 error, or a crash before the checks. NOT credit: round 408
                 §6.2 found the same second failure channel in
                 `bench/showtok.py`, where the single most direct plant
                 desynchronised the comparison instead of failing it. A
                 verdict machine that scores "the program died" as "the
                 check caught it" is measuring its own edit.
`unreached`      records exist but the named label is not among them: the
                 program stopped between its start and that check. Also not
                 credit, for the same reason.
`nonviable`      the named check is already FAILING at the baseline.
`unlocatable`    the site named by the pin is not in the file.
`equivalent`     the edit produced byte-identical source.

`score` is `guarded / (guarded + findings)` where findings are `inert` +
`shadowed` + `wrong_reason`. Errors (`collapsed`, `unreached`, `nonviable`,
`unlocatable`, `equivalent`) are reported SEPARATELY and excluded from the
denominator on purpose: an unlocatable pin is a fact about the registry and
an inert check is a fact about the suite, and averaging them hides both.
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from whence.lexer import tokenize, LexError            # noqa: E402

#: Every verdict that is a FINDING about the suite (as opposed to an error
#: about the pin or the run). Kept as one name so the reporter, the scorer
#: and the tests cannot drift apart — round 407's "a verdict is a
#: comparison" applied to the verdict SET.
FINDING_VERDICTS = ("inert", "shadowed", "wrong_reason")
ERROR_VERDICTS = ("collapsed", "unreached", "nonviable", "unlocatable",
                  "equivalent")

#: Wall-clock cap for one guest run. `self_host.lang` takes 3.3 s cold on
#: this box; a mutated guest can recurse forever, and round 413's lesson (c)
#: is that a cap firing must never be scored as "the suite went red". A
#: timeout here yields `collapsed`, which is an ERROR, not a finding.
DEFAULT_TIMEOUT_S = 180


class PinError(Exception):
    """Base for every refusal this module makes at pin-application time."""


class PinUnlocatable(PinError):
    """The pin's site is not in the file (or is ambiguous)."""


class EquivalentEdit(PinError):
    """The edit produced source byte-identical to the original."""


# --- locating a guest site, symbolically ----------------------------------
#
# Never by line number. A line number rots silently and would have the tool
# confidently editing whatever moved into its place; `self_host.lang` has
# been rewritten by rounds 302, 332, 350, 360, 368, 402, 408 and 410, and
# `git log --stat` says every one of them moved lines. A name that moved
# raises `PinUnlocatable` and the pin is reported as registry rot.
#
# `whence/ast_nodes.py` nodes carry `line` and nothing else — no column, no
# end position — so the AST cannot give a span. The LEXER can: `Token`
# carries `line` and `col`, `col` advances one per CHARACTER (not per byte)
# and resets to 1 after each newline, so `(line, col)` maps to a `str` index
# through a line-start table with no encoding step at all.

def _line_starts(src):
    """Character index of the first character of each 1-based line."""
    starts = [0]
    for i, ch in enumerate(src):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _offset(starts, line, col):
    return starts[line - 1] + (col - 1)


#: Tokens that OPEN a brace-depth level. `@{` is one token, not `@` + `{`
#: (`whence/lexer.TWO_CHAR_OPS`), and it is closed by a plain `}` — so a
#: depth counter that only knows `{` walks straight out of the function it
#: was measuring the moment the body holds a record literal, which every
#: guest parser function does.
_OPENERS = ("{", "@{")


def fn_span(src, name, occurrence=None):
    """Character span of the guest `fn NAME(...) { ... }` definition.

    Returns `(start, end)` with `end` one past the closing `}`. Refuses an
    ambiguous name outright rather than taking the first definition, which
    is the rule `find_function` follows in `harness/swe/guardpin.py`:
    `occurrence` (0-based) disambiguates a deliberately duplicated name.
    """
    toks = tokenize(src)
    starts = _line_starts(src)
    hits = []
    for i, t in enumerate(toks):
        if t.type != "KW" or t.value != "fn":
            continue
        if i + 1 >= len(toks) or toks[i + 1].type != "NAME":
            continue                      # an anonymous `fn(...)` literal
        if toks[i + 1].value != name:
            continue
        # walk to the first `{` after the parameter list, then match depth
        j = i + 2
        while j < len(toks) and toks[j].type not in _OPENERS:
            j += 1
        if j >= len(toks):
            continue
        depth = 0
        while j < len(toks):
            if toks[j].type in _OPENERS:
                depth += 1
            elif toks[j].type == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            continue
        hits.append((_offset(starts, t.line, t.col),
                     _offset(starts, toks[j].line, toks[j].col) + 1))
    if not hits:
        raise PinUnlocatable("no guest `fn %s` in this source" % name)
    if len(hits) > 1 and occurrence is None:
        raise PinUnlocatable(
            "guest `fn %s` is defined %d times; pass `occurrence`"
            % (name, len(hits)))
    return hits[occurrence or 0]


def line_span(src, needle, occurrence=None):
    """Character span of the whole LINE holding `needle`.

    Round 408 §6.2 found this form the hard way. Its first plants were
    `(old_text, new_text)` pairs — Whence string literals inside Python
    string literals inside a docstring-bearing test — and one of them was
    wrong in a way that PASSED its own `count(old) == 1` guard and then
    planted a real newline into a rendering. Naming one line by a short
    needle and replacing the whole line has no escaping depth at all.
    """
    lines = src.split("\n")
    hits = [k for k, ln in enumerate(lines) if needle in ln]
    if not hits:
        raise PinUnlocatable("no line contains %r" % needle)
    if len(hits) > 1 and occurrence is None:
        raise PinUnlocatable("%d lines contain %r; pass `occurrence`"
                             % (len(hits), needle))
    k = hits[occurrence or 0]
    starts = _line_starts(src)
    return starts[k], starts[k] + len(lines[k])


def apply_edit(src, pin):
    """Return the mutated guest source for one pin.

    Only the site's own span changes — not one byte outside it. That matters
    for the same reason it mattered in round 413: this module's whole job is
    telling a check that reads a RENDERING from one that reads a STRUCTURE,
    and an edit that reflows the file changes the very text a rendering
    check reads.
    """
    kind = pin["edit"]
    if kind == "fn_replace":
        a, b = fn_span(src, pin["target"], pin.get("occurrence"))
        new = src[:a] + pin["becomes"] + src[b:]
    elif kind == "line_replace":
        a, b = line_span(src, pin["needle"], pin.get("occurrence"))
        new = src[:a] + pin["becomes"] + src[b:]
    elif kind == "line_delete":
        a, b = line_span(src, pin["needle"], pin.get("occurrence"))
        new = src[:a] + src[b:]
    else:
        raise PinError("unknown edit kind %r" % kind)
    if new == src:
        raise EquivalentEdit(
            "the edit for %s produced byte-identical source" % pin["id"])
    return new


# --- running a guest program and reading its check records ----------------

_CHILD_SRC = r'''
import json, sys, os
sys.path.insert(0, %(here)r)
from whence.interp import Interpreter
from whence.lexer import LexError
from whence.parser import ParseError
sys.setrecursionlimit(6000)
out = {"checks": [], "error": None}
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        src = f.read()
    interp = Interpreter(out=lambda *a, **k: None, gc_relief=True,
                         direct=True, seed=0)
    try:
        interp.run(src)
    finally:
        out["checks"] = [{"label": c["label"], "line": c["line"],
                          "ok": bool(c["ok"]), "note": str(c.get("note", "")),
                          "why": str(c.get("why", ""))}
                         for c in interp.checks]
except (LexError, ParseError) as e:
    out["error"] = "%%s: %%s" %% (type(e).__name__, e)
except BaseException as e:                       # noqa: BLE001 - reported
    out["error"] = "%%s: %%s" %% (type(e).__name__, e)
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(out, f)
'''


def run_guest(src, timeout_s=DEFAULT_TIMEOUT_S, tmpdir=None):
    """Run guest `src` in a subprocess; return `(records, error, rc)`.

    A SUBPROCESS, not an in-process `Interpreter`, for two reasons that are
    both round 413's: a mutated guest can recurse without bound, and the
    only honest way to stop it is a wall clock the parent owns; and a guest
    that leaves the interpreter in a strange state must not be able to
    contaminate the next pin's run.

    The records come back as JSON through a FILE, not through stdout. Guest
    programs `print`, and `self_host.lang` ends with a `print` of its own —
    a parser that has to separate a program's output from the harness's
    record stream on one channel is the failure `bench/showtok.py` was
    already found making (round 408 §6.2).
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix="checkpin-", dir=tmpdir)
    prog = os.path.join(tmp, "prog.lang")
    outp = os.path.join(tmp, "out.json")
    child = os.path.join(tmp, "child.py")
    try:
        with open(prog, "w", encoding="utf-8") as f:
            f.write(src)
        with open(child, "w", encoding="utf-8") as f:
            f.write(_CHILD_SRC % {"here": _HERE})
        try:
            p = subprocess.run([sys.executable, child, prog, outp],
                               capture_output=True, text=True,
                               timeout=timeout_s)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            return [], "timeout after %ds" % timeout_s, -1
        if not os.path.exists(outp):
            return [], "child produced no record file (rc %d): %s" % (
                rc, (p.stderr or "").strip()[-400:]), rc
        with open(outp, encoding="utf-8") as f:
            data = json.load(f)
        return data["checks"], data["error"], rc
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def index_checks(records):
    """`{label: ok}`, and the labels that appear more than once.

    A duplicate label makes "did the check named X go red" ill-posed, so it
    is reported rather than silently resolved to the first or the last.
    """
    seen, dupes = {}, set()
    for r in records:
        if r["label"] in seen:
            dupes.add(r["label"])
        seen[r["label"]] = r
    return seen, sorted(dupes)


# --- the verdict ----------------------------------------------------------

def run_pin(pin, src, baseline, timeout_s=None):
    """Apply one pin and judge its named guardian. Returns a result dict."""
    res = {"id": pin["id"], "guardian": pin["guardian"],
           "mechanism": pin.get("mechanism", ""), "verdict": None,
           "control": pin.get("control_expect"),
           "n_red": 0, "co_red": [], "note": "", "why": pin.get("why", "")}
    base_idx, base_dupes = baseline["index"], baseline["dupes"]
    if pin["guardian"] in base_dupes:
        res["verdict"] = "unlocatable"
        res["note"] = ("the guardian label appears %d times in the baseline; "
                       "'did it go red' has no single answer"
                       % sum(1 for r in baseline["records"]
                             if r["label"] == pin["guardian"]))
        return res
    if pin["guardian"] not in base_idx:
        res["verdict"] = "unlocatable"
        res["note"] = "no check with this label in the baseline run"
        return res
    if not base_idx[pin["guardian"]]["ok"]:
        res["verdict"] = "nonviable"
        res["note"] = "the guardian is already FAILING unmutated"
        return res

    try:
        mutated = apply_edit(src, pin)
    except EquivalentEdit as e:
        res["verdict"] = "equivalent"
        res["note"] = str(e)
        return res
    except PinError as e:
        res["verdict"] = "unlocatable"
        res["note"] = str(e)
        return res

    records, error, rc = run_guest(
        mutated, timeout_s or pin.get("timeout_s") or DEFAULT_TIMEOUT_S)
    if not records:
        res["verdict"] = "collapsed"
        res["note"] = error or "no check records (rc %d)" % rc
        return res

    idx, _ = index_checks(records)
    red = [r["label"] for r in records
           if not r["ok"] and base_idx.get(r["label"], {}).get("ok")]
    res["n_red"] = len(red)
    res["co_red"] = sorted(l for l in red if l != pin["guardian"])[:12]
    res["n_ran"] = len(records)
    # A check that vanished from the record stream did not "pass": the
    # program stopped before it. Distinguishing this from `inert` is the
    # whole reason `collapsed`/`unreached` exist.
    if pin["guardian"] not in idx:
        res["verdict"] = "unreached"
        res["note"] = ("the run produced %d record(s) but not this one; "
                       "%s" % (len(records), error or "no error reported"))
        return res

    rec = idx[pin["guardian"]]
    if rec["ok"]:
        res["verdict"] = "shadowed" if red else "inert"
        res["note"] = ("the guardian passed under the edit; %d other check(s) "
                       "went red" % len(red)) if red else (
            "the guardian passed and NOTHING in the file went red")
        return res

    # Round 412's discipline, in the only place the guest can express it.
    # `Interpreter._record_check` gives a failing check one of THREE canned
    # notes -- "value was false", "value was miss: ...", "value was <x>, not
    # a boolean" -- so a `check` on a boolean expression cannot say what it
    # expected, and `expect_in_note` is unusable for 22 of this registry's
    # 23 pins. What it CAN say is in `entry["why"]`: `render_why(v)` is the
    # provenance tree of the failing value, and it names the operands, the
    # calls and the lines that produced `false`. That is exactly "the test
    # noticed THIS" in a form the language already computes and nothing has
    # ever read. `expect_in_why` is the guest-native `expect_in_failure`.
    hay = rec["note"] + "\n" + rec.get("why", "")
    for field, want in (("expect_in_note", pin.get("expect_in_note")),
                        ("expect_in_why", pin.get("expect_in_why"))):
        if not want:
            continue
        target = rec["note"] if field == "expect_in_note" else hay
        if want not in target:
            res["verdict"] = "wrong_reason"
            res["note"] = ("went red, but %s does not contain %r"
                           % (field.replace("expect_in_", "the "), want))
            return res
    res["verdict"] = "guarded"
    res["note"] = rec["note"][:220]
    return res


def build_baseline(src, timeout_s=DEFAULT_TIMEOUT_S):
    records, error, rc = run_guest(src, timeout_s)
    idx, dupes = index_checks(records)
    return {"records": records, "index": idx, "dupes": dupes,
            "error": error, "rc": rc,
            "n_failing": sum(1 for r in records if not r["ok"])}


def run_registry(reg, root=None, only=None):
    """Run every pin in a registry dict. One baseline per guest file."""
    root = root or _HERE
    baselines, results = {}, []
    for pin in reg["pins"]:
        if only and pin["id"] not in only:
            continue
        gf = pin["guest_file"]
        if gf not in baselines:
            with open(os.path.join(root, gf), encoding="utf-8") as f:
                baselines[gf] = (f.read(), None)
            src = baselines[gf][0]
            baselines[gf] = (src, build_baseline(src))
        src, base = baselines[gf]
        results.append(run_pin(pin, src, base))
    # A negative control is not a finding and not an error: it is the
    # measurement that says the other verdicts mean anything. Scoring it in
    # the denominator would make an instrument that WORKS look 4% worse for
    # having checked itself, which is the wrong incentive to build in.
    controls = [r for r in results if r.get("control")]
    scored = [r for r in results if not r.get("control")]
    guarded = sum(1 for r in scored if r["verdict"] == "guarded")
    findings = [r for r in scored if r["verdict"] in FINDING_VERDICTS]
    errors = [r for r in scored if r["verdict"] in ERROR_VERDICTS]
    denom = guarded + len(findings)
    return {
        "n_pins": len(scored),
        "controls": [{"id": r["id"], "verdict": r["verdict"],
                      "n_red": r["n_red"], "expected": r["control"],
                      "held": (r["verdict"] == r["control"].get("verdict")
                               and r["n_red"] == r["control"].get("n_red"))}
                     for r in controls],
        "guarded": guarded,
        "findings": len(findings),
        "errors": len(errors),
        "score": (guarded / denom) if denom else None,
        "baselines": {gf: {"n_checks": len(b["records"]),
                           "n_failing": b["n_failing"],
                           "dupes": b["dupes"], "error": b["error"]}
                      for gf, (_, b) in baselines.items()},
        "results": results,
    }


# --- CLI ------------------------------------------------------------------

def _load_registry(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cmd_locate(args):
    """Print the span and the mutated text for each pin WITHOUT running it.

    Round 413's most transferable finding was that its first splice was a
    wrong EXPERIMENT rather than a wrong answer, and that `locate` — reading
    the diffs before running a single test — is what caught it.
    """
    reg = _load_registry(args[0])
    root = _HERE
    for pin in reg["pins"]:
        with open(os.path.join(root, pin["guest_file"]), encoding="utf-8") as f:
            src = f.read()
        print("=" * 70)
        print("%s  %s  (%s)" % (pin["id"], pin.get("mechanism", ""),
                                pin["edit"]))
        try:
            if pin["edit"] == "fn_replace":
                a, b = fn_span(src, pin["target"], pin.get("occurrence"))
            else:
                a, b = line_span(src, pin["needle"], pin.get("occurrence"))
        except PinError as e:
            print("  UNLOCATABLE: %s" % e)
            continue
        print("  span %d..%d (%d chars)" % (a, b, b - a))
        for line in src[a:b].split("\n"):
            print("  - %s" % line)
        try:
            new = apply_edit(src, pin)
        except PinError as e:
            print("  REFUSED: %s" % e)
            continue
        for line in new[a:a + (b - a) + (len(new) - len(src))].split("\n"):
            print("  + %s" % line)
        assert new[:a] == src[:a] and new[len(new) - (len(src) - b):] == src[b:], (
            "the edit changed bytes OUTSIDE the located span")
    return 0


def _cmd_run(args):
    reg = _load_registry(args[0])
    only = set(args[1:]) or None
    out = run_registry(reg, only=only)
    for r in out["results"]:
        print("%-6s %-13s %-34s n_red=%-4s %s"
              % (r["id"], r["verdict"], r["guardian"][:34], r["n_red"],
                 r["note"][:70]))
    for c in out["controls"]:
        print("CONTROL %s: %s (n_red=%d), expected %s -> %s"
              % (c["id"], c["verdict"], c["n_red"], c["expected"],
                 "HELD" if c["held"] else "*** BROKEN: every verdict above "
                 "is void ***"))
    print("\n%d pins: %d guarded, %d finding(s), %d error(s), score %s"
          % (out["n_pins"], out["guarded"], out["findings"], out["errors"],
             "n/a" if out["score"] is None else "%.0f%%" % (100 * out["score"])))
    if len(args) > 0 and os.environ.get("CHECKPIN_JSON"):
        with open(os.environ["CHECKPIN_JSON"], "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print("wrote %s" % os.environ["CHECKPIN_JSON"])
    return 0 if out["findings"] == 0 and out["errors"] == 0 else 1


def main(argv):
    if len(argv) < 3 or argv[1] not in ("locate", "run"):
        print("usage: checkpin.py {locate|run} <registry.json> [pin-id ...]",
              file=sys.stderr)
        return 2
    return {"locate": _cmd_locate, "run": _cmd_run}[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
