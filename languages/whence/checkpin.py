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
`redundant`      (round 416) `inert`, AND the pin named a wider pin in
                 `redundant_with` that removes every copy of the same rule,
                 and THAT one went red. The file could not see this edit
                 because the rule is implemented more than once, not
                 because nothing guards it. Scored out, like a control.
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
`redundant` is excluded for a third reason: it is a fact about the CODE,
and counting it would make a file that defends a rule twice score worse for
having done so.

A pin also carries, from round 416, the two fields that campaign was built
to compare: `dir` ("-" the rule does less / "+" the rule does more) and
`predicate` (the SHAPE of the guardian's expression). A guardian whose
predicate is one-sided — `missed(X)`, `contains(X, s)`, `len(X) > 0`,
`not is_num(X)` — is monotone in one of those directions and cannot go red
there however badly the rule is broken. Mutating each rule in only ONE
direction measures the direction the registry author happened to pick.
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

#: Round 422. `equivalent` above is a SYNTACTIC test — `apply_edit` produced
#: byte-identical source — and it cannot see the case round 422 hit: an edit
#: that changes the text, parses, and is UNREACHABLE. `CP10p` added `"\n"` to
#: the guest lexer's whitespace arm, and the `"\n"` arm above it means no
#: input ever reaches the line that changed. The verdict was `inert`, which
#: reads "nothing in this file guards the rule" — a finding about the SUITE,
#: charged to the file, for a defect in the PIN.
#:
#: So `inert` has a THIRD cause, and round 416's argument for splitting off
#: `redundant` applies unchanged: two causes under one verdict that want
#: opposite responses. A pin separates them by carrying a `witness` — a guest
#: expression that is TRUE unmutated and must go FALSE under the edit. The
#: witness is appended as an extra `check` to the mutated source (and, for the
#: baseline, to a single combined run), so it costs no extra guest run.
#:
#:   witness moves   + guardian green + nothing red -> `inert`  (a real gap)
#:   witness HOLDS   + guardian green + nothing red -> `unreachable`
#:   no witness given                               -> `inert_unwitnessed`
#:
#: `unreachable` is scored OUT, like a control and like `redundant`: the file
#: is not worse for failing to notice an edit nothing can observe.
#: `inert_unwitnessed` is an ERROR rather than a finding for the reason round
#: 417 gave — an unmeasured claim must not be counted as a measured one.
UNREACHABLE_VERDICT = "unreachable"

#: Labels of witness checks are prefixed so they can never be mistaken for a
#: guardian, and are excluded from `n_red`/`co_red`: a witness going red is
#: the instrument working, not the suite noticing.
WITNESS_PREFIX = "__witness__ "

#: Round 416. `inert` answers "the guardian stayed green and nothing else
#: went red", and that sentence has TWO causes which want opposite
#: responses: nothing in the file can see this rule (write a check), or the
#: rule has more than one implementation and this pin removed one of them
#: (write nothing — the suite is right that the behaviour did not change).
#: A pin says which by naming, in `redundant_with`, a WIDER pin that removes
#: every copy. `inert` here + `guarded` there demotes this pin to
#: `redundant`, which is neither a finding nor an error and is scored out,
#: for the same reason a control is: counting a correctly-redundant rule as
#: a suite defect would make a file that defends a rule twice look worse for
#: having done so.
REDUNDANT_VERDICT = "redundant"

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


def _apply_one(src, spec):
    """Apply ONE edit spec (`edit` + its site fields) and return the source."""
    kind = spec["edit"]
    if kind == "fn_replace":
        a, b = fn_span(src, spec["target"], spec.get("occurrence"))
        return src[:a] + spec["becomes"] + src[b:]
    if kind == "line_replace":
        a, b = line_span(src, spec["needle"], spec.get("occurrence"))
        return src[:a] + spec["becomes"] + src[b:]
    if kind == "line_delete":
        a, b = line_span(src, spec["needle"], spec.get("occurrence"))
        return src[:a] + src[b:]
    raise PinError("unknown edit kind %r" % kind)


def apply_edit(src, pin):
    """Return the mutated guest source for one pin.

    Only the site's own span changes — not one byte outside it. That matters
    for the same reason it mattered in round 413: this module's whole job is
    telling a check that reads a RENDERING from one that reads a STRUCTURE,
    and an edit that reflows the file changes the very text a rendering
    check reads.

    `also` (round 416) is a list of ADDITIONAL edit specs applied on top of
    the pin's own, in order. It exists because `inert` was found conflating
    two different facts:

      * nothing in the file can see this rule; and
      * the rule has more than one implementation, and this pin removed one
        of them.

    Both read `guardian green, n_red == 0`, and they call for opposite
    responses — the first wants a new check, the second wants none, because
    the suite is right that the behaviour did not change. A pin that names
    every copy of its rule in `also` is the only thing that tells them
    apart: if the WIDER edit goes `guarded`, the rule was redundant, not
    unguarded. Each extra edit is located in the source produced by the
    previous one, so an `also` may target text the pin's own edit wrote.
    """
    new = _apply_one(src, pin)
    for extra in pin.get("also", ()):
        new = _apply_one(new, extra)
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

def witness_check(pin):
    """The guest `check` line that carries this pin's witness, or ``""``."""
    if not pin.get("witness"):
        return ""
    return 'check "%s%s": %s' % (WITNESS_PREFIX, pin["id"], pin["witness"])


def run_pin(pin, src, baseline, timeout_s=None):
    """Apply one pin and judge its named guardian. Returns a result dict."""
    res = {"id": pin["id"], "guardian": pin["guardian"],
           "mechanism": pin.get("mechanism", ""), "verdict": None,
           "control": pin.get("control_expect"),
           "n_red": 0, "co_red": [], "note": "", "why": pin.get("why", ""),
           "witness": pin.get("witness") or None, "witness_moved": None}
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

    wline = witness_check(pin)
    if wline:
        mutated = mutated + "\n" + wline + "\n"
    records, error, rc = run_guest(
        mutated, timeout_s or pin.get("timeout_s") or DEFAULT_TIMEOUT_S)
    if not records:
        res["verdict"] = "collapsed"
        res["note"] = error or "no check records (rc %d)" % rc
        return res

    idx, _ = index_checks(records)
    if wline:
        wrec = idx.get(WITNESS_PREFIX + pin["id"])
        res["witness_moved"] = (wrec is not None and not wrec["ok"])
    red = [r["label"] for r in records
           if not r["ok"] and base_idx.get(r["label"], {}).get("ok")
           and not r["label"].startswith(WITNESS_PREFIX)]
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
        if red:
            res["verdict"] = "shadowed"
            res["note"] = ("the guardian passed under the edit; %d other "
                           "check(s) went red" % len(red))
        elif not wline:
            res["verdict"] = "inert"
            res["note"] = ("the guardian passed and NOTHING in the file went "
                           "red -- UNWITNESSED, so whether the edit changes "
                           "any observable behaviour was not measured")
        elif res["witness_moved"]:
            res["verdict"] = "inert"
            res["note"] = ("the guardian passed and NOTHING in the file went "
                           "red, yet the witness went red: the edit IS "
                           "observable and this file cannot see it")
        else:
            res["verdict"] = UNREACHABLE_VERDICT
            res["note"] = ("the witness held under the edit: nothing this "
                           "pin can observe changed, so the file is right "
                           "that nothing went red. The PIN is the defect")
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
                src = f.read()
            # Round 422. Every witness in this registry for this guest file is
            # appended to ONE baseline run, so a witness costs no extra guest
            # process. A witness that is already FALSE unmutated is not a
            # witness -- it cannot "go" red -- and its pin is failed rather
            # than silently judged, which is round 413's `BaselineNotGreen`
            # rule one level down.
            wlines = [witness_check(p2) for p2 in reg["pins"]
                      if p2["guest_file"] == gf and p2.get("witness")]
            probe = src + ("\n" + "\n".join(wlines) + "\n" if wlines else "")
            baselines[gf] = (src, build_baseline(probe))
        src, base = baselines[gf]
        wlab = WITNESS_PREFIX + pin["id"]
        if pin.get("witness") and not base["index"].get(wlab, {}).get("ok"):
            results.append({
                "id": pin["id"], "guardian": pin["guardian"],
                "mechanism": pin.get("mechanism", ""), "verdict": "nonviable",
                "control": pin.get("control_expect"), "n_red": 0,
                "co_red": [], "why": pin.get("why", ""),
                "witness": pin["witness"], "witness_moved": None,
                "note": ("the witness is not TRUE on the unmutated file, so "
                         "it cannot witness anything: %s"
                         % (base["index"].get(wlab, {}).get("note")
                            or "no such record"))})
            continue
        results.append(run_pin(pin, src, base))
    # A negative control is not a finding and not an error: it is the
    # measurement that says the other verdicts mean anything. Scoring it in
    # the denominator would make an instrument that WORKS look 4% worse for
    # having checked itself, which is the wrong incentive to build in.
    # Round 416: resolve `redundant_with` before scoring. A pin can only be
    # demoted if the wider pin actually RAN — under `--only` it stays
    # `inert`, which is the conservative answer.
    by_id = {r["id"]: r for r in results}
    for pin in reg["pins"]:
        r = by_id.get(pin["id"])
        wider = pin.get("redundant_with")
        if not r or not wider or r["verdict"] != "inert":
            continue
        w = by_id.get(wider)
        if w is not None and w["verdict"] == "guarded":
            r["verdict"] = REDUNDANT_VERDICT
            r["note"] = (
                "the guardian stayed green and nothing went red, but the "
                "wider edit %s — the same rule with every copy removed — "
                "went red. The rule is redundantly implemented, not "
                "unguarded." % wider)
    controls = [r for r in results if r.get("control")]
    redundant = [r for r in results
                 if r["verdict"] == REDUNDANT_VERDICT and not r.get("control")]
    unreachable = [r for r in results
                   if r["verdict"] == UNREACHABLE_VERDICT
                   and not r.get("control")]
    scored = [r for r in results
              if not r.get("control")
              and r["verdict"] not in (REDUNDANT_VERDICT,
                                       UNREACHABLE_VERDICT)]
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
        "redundant": [{"id": r["id"], "wider": next(
            p["redundant_with"] for p in reg["pins"] if p["id"] == r["id"])}
            for r in redundant],
        "unreachable": [{"id": r["id"], "witness": r["witness"]}
                        for r in unreachable],
        # Round 417's denominator rule: an `inert` verdict that was never
        # witnessed has not been shown to be a gap rather than an unreachable
        # edit, and the summary says how many of each there are.
        "inert_total": sum(1 for r in scored if r["verdict"] == "inert"),
        "inert_witnessed": sum(1 for r in scored if r["verdict"] == "inert"
                               and r.get("witness")),
        "findings": len(findings),
        "errors": len(errors),
        "score": (guarded / denom) if denom else None,
        "baselines": {gf: {"n_checks": sum(
                               1 for r in b["records"]
                               if not r["label"].startswith(WITNESS_PREFIX)),
                           "n_witnesses": sum(
                               1 for r in b["records"]
                               if r["label"].startswith(WITNESS_PREFIX)),
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
        cur, refused = src, False
        # The pin's own edit, then each `also` edit, each located in the
        # source the previous one produced. The span invariant is asserted
        # PER EDIT rather than over the whole file, because an `also` pin
        # changes more than one span on purpose.
        for n, spec in enumerate([pin] + list(pin.get("also", ()))):
            try:
                if spec["edit"] == "fn_replace":
                    a, b = fn_span(cur, spec["target"], spec.get("occurrence"))
                else:
                    a, b = line_span(cur, spec["needle"],
                                     spec.get("occurrence"))
            except PinError as e:
                print("  UNLOCATABLE%s: %s" % ("" if not n else " (also %d)" % n, e))
                refused = True
                break
            print("  %sspan %d..%d (%d chars)"
                  % ("" if not n else "also %d: " % n, a, b, b - a))
            for line in cur[a:b].split("\n"):
                print("  - %s" % line)
            nxt = _apply_one(cur, spec)
            for line in nxt[a:a + (b - a) + (len(nxt) - len(cur))].split("\n"):
                print("  + %s" % line)
            assert nxt[:a] == cur[:a] and \
                nxt[len(nxt) - (len(cur) - b):] == cur[b:], (
                    "edit %d of %s changed bytes OUTSIDE its located span"
                    % (n, pin["id"]))
            cur = nxt
        if refused:
            continue
        if cur == src:
            print("  REFUSED: the edit produced byte-identical source")
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
    for r in out["redundant"]:
        print("REDUNDANT %s: inert, but the wider edit %s went red — the rule "
              "has more than one implementation" % (r["id"], r["wider"]))
    for r in out["unreachable"]:
        print("UNREACHABLE %s: the guardian stayed green, nothing went red, "
              "AND the witness `%s` held — the edit changes no observable "
              "behaviour, so this is a defect in the pin and is scored out"
              % (r["id"], (r["witness"] or "")[:60]))
    print("\n%d pins: %d guarded, %d finding(s), %d error(s), "
          "%d redundant, %d unreachable, score %s; %d of %d inert verdict(s) "
          "witnessed"
          % (out["n_pins"], out["guarded"], out["findings"], out["errors"],
             len(out["redundant"]), len(out["unreachable"]),
             "n/a" if out["score"] is None else "%.0f%%" % (100 * out["score"]),
             out["inert_witnessed"], out["inert_total"]))
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
