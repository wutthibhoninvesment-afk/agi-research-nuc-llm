"""Round 414 (language C) — guard pins for the GUEST's own `check` statements.

`state/research-state.md` next-step item 8 has carried round 408's item 2
since round 408:

    A check whose name states a mechanism should fail when the mechanism
    goes. `self_host.lang`'s quote-switching check passed straight through
    the deletion of quote-switching. The sweep is mechanical and cheap:
    every `check "<name>"` in the two guest files whose name asserts a RULE,
    asked whether any program in the file can distinguish that rule from its
    replacement.

`checkpin.py` is that sweep. It is NOT `harness/swe/guardpin.py` (round 413)
with a different file extension: `guardpin` edits host Python and requires a
named PYTEST node to go red, and no edit it can make touches
`examples/self_host.lang`'s guest lexer and parser, which are written in
Whence and guarded by `check` labels. The two instruments cannot reach each
other's defects.

WHAT THE FIRST RUN FOUND (22 scored pins over 16 guest mechanisms, 89 s):

    20 guarded, 2 findings, 0 errors, score 91%

  * `CP02` — **round 408's own replacement is HALF inert.** Round 408 §6.1
    deleted the quote-switching rule, found the check named for it green
    either way, and replaced it with a PAIR it said "CAN tell the two rules
    apart". Putting the switching rule back: the keyword/string half goes
    red (`CP01 guarded`) and the half labelled *"a string in the got slot is
    a Whence literal, always double-quoted"* stays GREEN, because its probe
    value `"a'b"` is exactly the string the two rules render IDENTICALLY.
    A one-probe check cannot carry the word "always".

  * `CP11` — the guest's own `\r`-escape decoder was deletable with all 154
    checks green. The label *"the \r escape decodes, so a CR can be written
    down at all"* is about the HOST escape (that is what made the probe
    writable at all, round 350); the probe it hands the guest is a RAW
    carriage return, which never reaches `lex_str_body`'s escape arm.

Both killers are in `examples/self_host.lang` next to the checks they
extend, and re-running the registry gives **22 guarded, 0 findings**.

These tests are the instrument's own pins. They run on a THREE-LINE guest
written to a tmpdir, not on `self_host.lang`, so the whole file costs about
a second: the campaign is a `whence_slow` artefact, the machine that runs it
is not.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import checkpin as C                                            # noqa: E402
import curecheck as _C                                          # noqa: E402

#: Round 419: resolved from `curecheck.AGI_ROOT` (which prefers
#: `AGI_RESEARCH_ROOT`, exported by `harness/swe/proc.py` into every test
#: subprocess) rather than from this file's own `__file__`. Under a
#: `harness/swe/mutation.py` copy of `languages/whence` alone, `ROOT/../..`
#: is `/tmp`, and the three tests below opened
#: `/tmp/state/whence/round-414/check-pins.json` -> FileNotFoundError ->
#: `baseline_check` red -> `mutation_test` raised `BaselineNotGreen` before
#: generating a single mutant. Round 413 fixed six sites of exactly this and
#: wrote the rule in `curecheck.AGI_ROOT`'s comment; rounds 414 and 416 added
#: these two. See `harness/swe/copyparity.py`, which now measures it.
REGISTRY = os.path.join(_C.AGI_ROOT, "state", "whence", "round-414",
                        "check-pins.json")
#: Round 416's registry, over the guest EVALUATOR half of
#: `examples/self_eval.lang`. Kept as a second entry rather than merged into
#: the first: the two guest files have separate baselines, and a pin that
#: rots should name which registry it rotted in.
REGISTRY_EVAL = os.path.join(_C.AGI_ROOT, "state", "whence", "round-416",
                             "eval-pins.json")
#: Round 422's PLUS half of the FIRST registry — the same nineteen mechanisms
#: `REGISTRY` mutates, mutated in the opposite direction. Two entries, not one
#: merged file, for the reason the `REGISTRY_EVAL` comment gives and one more:
#: the repointed copy differs from the as-written copy in TWENTY guardian
#: LABELS and nothing else, so keeping both is what makes "repointing alone
#: moved the score" checkable rather than asserted. (Round 435: this said
#: `nineteen` while `test_the_repointed_registry_changes_labels_and_nothing_
#: else`, 590 lines below, has asserted `moved == 20` since round 423. The
#: `nineteen` in the sentence ABOVE is correct and is a different quantity --
#: 19 of the 20 `+` mechanisms match a `-` mechanism in `REGISTRY` verbatim;
#: the twentieth, `a shape cannot reference itself`, differs by the
#: parenthetical `(SAME edit as CP20)`.)
REGISTRY_PLUS = os.path.join(_C.AGI_ROOT, "state", "whence", "round-422",
                             "host-pins-plus.json")
REGISTRY_PLUS_REPOINTED = os.path.join(
    _C.AGI_ROOT, "state", "whence", "round-422",
    "host-pins-plus-repointed.json")
REGISTRIES = ((REGISTRY, "self_host.lang"), (REGISTRY_EVAL, "self_eval.lang"),
              (REGISTRY_PLUS, "self_host.lang"),
              (REGISTRY_PLUS_REPOINTED, "self_host.lang"))

#: A whole guest program, small enough that a full run is ~0.3 s. Every unit
#: test below edits THIS, not `self_host.lang`.
TOY = '''fn twice(n) { n * 2 }
fn boxed(n) { @{v: twice(n)} }
check "twice doubles": twice(3) == 6
check "boxed carries the doubling": (boxed(4)).v == 8
check "unrelated arithmetic": 1 + 1 == 2
'''


# --- locating a site symbolically ----------------------------------------

def test_fn_span_is_exactly_the_definition():
    a, b = C.fn_span(TOY, "twice")
    assert TOY[a:b] == "fn twice(n) { n * 2 }"


def test_a_record_literal_does_not_end_the_span_early():
    """`@{` is ONE token, closed by a plain `}`.

    A depth counter that only knows `{` sees `boxed`'s body open once and
    close twice, and returns a span ending at the record's `}` — half a
    function, which `apply_edit` would then splice a replacement over. Every
    guest parser function in `self_host.lang` returns a record literal, so
    this is not a corner case: it is the common case.
    """
    a, b = C.fn_span(TOY, "boxed")
    assert TOY[a:b] == "fn boxed(n) { @{v: twice(n)} }"
    assert TOY[a:b].count("{") == 2 and TOY[a:b].endswith("}")


def test_an_absent_function_is_unlocatable_not_a_wrong_answer():
    with pytest.raises(C.PinUnlocatable):
        C.fn_span(TOY, "nosuchfn")


def test_a_duplicated_name_is_refused_rather_than_resolved_to_the_first():
    """`guardpin.find_function`'s rule, and the reason a line number is not
    an acceptable substitute for a name: a tool that silently takes the
    first definition edits whichever one happens to be earlier in the file."""
    two = TOY + "\nfn twice(n) { n * 2 }\n"
    with pytest.raises(C.PinUnlocatable) as e:
        C.fn_span(two, "twice")
    assert "defined 2 times" in str(e.value)
    assert C.fn_span(two, "twice", occurrence=1)[0] > C.fn_span(
        two, "twice", occurrence=0)[0]


def test_an_ambiguous_needle_is_refused_too():
    with pytest.raises(C.PinUnlocatable):
        C.line_span(TOY + TOY, "fn twice(n)")


def test_an_anonymous_fn_literal_is_not_mistaken_for_a_definition():
    src = 'let f = fn(n) { n * 2 }\ncheck "x": f(1) == 2\n'
    with pytest.raises(C.PinUnlocatable):
        C.fn_span(src, "f")


# --- applying an edit -----------------------------------------------------

def test_the_edit_changes_nothing_outside_its_own_span():
    """The property that makes a RENDERING pin distinguishable from a
    STRUCTURE pin. Round 413's first draft re-unparsed the whole enclosing
    statement, which deleted comments and renormalised strings — not a wrong
    answer but a wrong EXPERIMENT, because this module's subject is exactly
    the text a rendering check reads."""
    pin = {"id": "T", "edit": "fn_replace", "target": "twice",
           "becomes": "fn twice(n) { n * 3 }"}
    a, b = C.fn_span(TOY, "twice")
    new = C.apply_edit(TOY, pin)
    assert new[:a] == TOY[:a]
    assert new[a + len(pin["becomes"]):] == TOY[b:]


def test_a_byte_identical_replacement_is_an_error_not_a_finding():
    """An edit that changes nothing and is reported as `inert` would be a
    finding-shaped artefact of the tool. `guardpin.EquivalentEdit`'s rule."""
    pin = {"id": "T", "edit": "fn_replace", "target": "twice",
           "becomes": "fn twice(n) { n * 2 }"}
    with pytest.raises(C.EquivalentEdit):
        C.apply_edit(TOY, pin)


# --- the verdicts ---------------------------------------------------------

def _run(pin, src=TOY):
    base = C.build_baseline(src)
    assert base["n_failing"] == 0, base
    return C.run_pin(pin, src, base)


def test_a_named_guardian_that_goes_red_is_guarded():
    r = _run({"id": "T1", "edit": "fn_replace", "target": "twice",
              "becomes": "fn twice(n) { n * 3 }",
              "guardian": "twice doubles"})
    assert r["verdict"] == "guarded"
    assert r["n_red"] == 2                       # `boxed` notices as well
    assert r["co_red"] == ["boxed carries the doubling"]


def test_a_guardian_that_stays_green_while_others_go_red_is_shadowed():
    """The verdict round 411's `check_paths` bug and round 414's CP02 share:
    something guards the rule, but not the thing the record names."""
    r = _run({"id": "T2", "edit": "fn_replace", "target": "twice",
              "becomes": "fn twice(n) { n * 3 }",
              "guardian": "unrelated arithmetic"})
    assert r["verdict"] == "shadowed"
    assert r["n_red"] == 2


def test_a_guardian_that_stays_green_with_nothing_red_is_inert():
    """CP11's verdict, and NC01's. `n_red == 0` is what makes it a statement
    about the FILE rather than about the guardian."""
    r = _run({"id": "T3", "edit": "line_replace",
              "needle": "fn twice(n) { n * 2 }",
              "becomes": "fn twice(n) { n + n }",
              "guardian": "twice doubles"})
    assert r["verdict"] == "inert" and r["n_red"] == 0


def test_a_program_that_does_not_parse_is_collapsed_and_not_credit():
    """The failure channel round 408 §6.2 found in `bench/showtok.py`: the
    most direct plant on a renderer desynchronised the comparison instead of
    failing it. A verdict machine that scores "the program died" as "the
    check caught it" is measuring its own edit."""
    r = _run({"id": "T4", "edit": "fn_replace", "target": "twice",
              "becomes": "fn twice(n) { n * }",
              "guardian": "twice doubles"})
    assert r["verdict"] == "collapsed"
    assert r["verdict"] in C.ERROR_VERDICTS
    assert r["verdict"] not in C.FINDING_VERDICTS


def test_a_guardian_that_is_already_failing_is_nonviable():
    """Round 349's rule, per pin: a red baseline is no evidence at all."""
    src = TOY + 'check "already broken": 1 == 2\n'
    base = C.build_baseline(src)
    r = C.run_pin({"id": "T5", "edit": "fn_replace", "target": "twice",
                   "becomes": "fn twice(n) { n * 3 }",
                   "guardian": "already broken"}, src, base)
    assert r["verdict"] == "nonviable"


def test_a_guardian_label_that_is_not_in_the_file_is_unlocatable():
    r = _run({"id": "T6", "edit": "fn_replace", "target": "twice",
              "becomes": "fn twice(n) { n * 3 }",
              "guardian": "no check is called this"})
    assert r["verdict"] == "unlocatable"


def test_a_duplicated_guardian_label_has_no_single_answer():
    src = TOY + 'check "twice doubles": 1 == 1\n'
    base = C.build_baseline(src)
    assert base["dupes"] == ["twice doubles"]
    r = C.run_pin({"id": "T7", "edit": "fn_replace", "target": "twice",
                   "becomes": "fn twice(n) { n * 3 }",
                   "guardian": "twice doubles"}, src, base)
    assert r["verdict"] == "unlocatable"
    assert "no single answer" in r["note"]


def test_a_check_that_never_ran_is_unreached_and_not_credit():
    """`unreached` cannot be provoked from a guest program — misses are
    total in Whence, so a program keeps going — which is exactly why it is
    tested against a stubbed run rather than left unpinned. A verdict whose
    only path is an interpreter crash is still a verdict the reporter must
    get right the day it fires."""
    src = TOY
    base = C.build_baseline(src)
    real = C.run_guest
    try:
        C.run_guest = lambda *a, **k: (
            [{"label": "unrelated arithmetic", "line": 5, "ok": True,
              "note": "", "why": ""}], None, 0)
        r = C.run_pin({"id": "T8", "edit": "fn_replace", "target": "twice",
                       "becomes": "fn twice(n) { n * 3 }",
                       "guardian": "twice doubles"}, src, base)
    finally:
        C.run_guest = real
    assert r["verdict"] == "unreached"
    assert r["verdict"] in C.ERROR_VERDICTS


# --- round 412's discipline, in the only place the guest can express it ---

def test_a_failing_check_cannot_say_what_it_expected_but_its_why_tree_can():
    """`Interpreter._record_check` gives a failing check one of THREE canned
    notes. `"value was false"` is every boolean check's whole failure text,
    so round 412's `expect_in_failure` — "it went red, and it went red on
    THIS" — is not expressible against the note at all.

    `entry["why"]` is. `render_why` is the provenance tree of the value that
    came out false, and it names the calls and lines that produced it. The
    language has computed that on every failing check since v0.1 and no
    instrument in this repo had ever read it.
    """
    pin = {"id": "T9", "edit": "fn_replace", "target": "twice",
           "becomes": "fn twice(n) { n * 3 }", "guardian": "twice doubles"}
    assert _run(dict(pin, expect_in_note="twice"))["verdict"] == "wrong_reason"
    assert _run(dict(pin, expect_in_why="twice"))["verdict"] == "guarded"
    bad = _run(dict(pin, expect_in_why="a phrase no why-tree holds"))
    assert bad["verdict"] == "wrong_reason"
    assert bad["verdict"] in C.FINDING_VERDICTS


# --- the registry itself --------------------------------------------------

def _registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def test_every_pin_in_the_registry_still_locates():
    """Pin rot, checked without running anything. A pin that names a guest
    function some later round renamed is a fact about the REGISTRY, and it
    should surface here rather than as a mysterious error in the campaign."""
    reg = _registry()
    src = open(os.path.join(ROOT, "examples", "self_host.lang"),
               encoding="utf-8").read()
    for pin in reg["pins"]:
        C.apply_edit(src, pin)             # raises PinUnlocatable if it rots


def test_every_guardian_label_is_a_real_check_in_the_guest_file():
    reg = _registry()
    src = open(os.path.join(ROOT, "examples", "self_host.lang"),
               encoding="utf-8").read()
    for pin in reg["pins"]:
        assert 'check "%s"' % pin["guardian"] in src, pin["id"]


def test_the_registry_carries_a_negative_control():
    """Round 408 §6.2's rule — "a negative control has to name which one it
    expects" — applied to this instrument. Without a pin that MUST come back
    `inert`, an `inert` verdict anywhere else is unfalsifiable: it could
    equally mean the runner never applied the edit."""
    controls = [p for p in _registry()["pins"] if p.get("control_expect")]
    assert controls, "no negative control in the registry"
    for c in controls:
        assert c["control_expect"] == {"verdict": "inert", "n_red": 0}


@pytest.mark.whence_slow
def test_the_negative_control_holds_against_the_real_guest_file():
    reg = _registry()
    ctrl = [p for p in reg["pins"] if p.get("control_expect")][0]
    src = open(os.path.join(ROOT, "examples", "self_host.lang"),
               encoding="utf-8").read()
    r = C.run_pin(ctrl, src, C.build_baseline(src))
    assert r["verdict"] == "inert" and r["n_red"] == 0


@pytest.mark.whence_slow
def test_the_two_killers_this_round_added_actually_kill():
    """The round's own result, re-measured rather than asserted from the
    write-up. `state/whence/round-414/run-before.json` records both as
    findings against `git show HEAD~:...`; here they must be `guarded`."""
    reg = {p["id"]: p for p in _registry()["pins"]}
    src = open(os.path.join(ROOT, "examples", "self_host.lang"),
               encoding="utf-8").read()
    base = C.build_baseline(src)
    for pid in ("CP02", "CP11"):
        r = C.run_pin(reg[pid], src, base)
        assert r["verdict"] == "guarded", (pid, r)


# --- round 416: `also`, and the `redundant` verdict -----------------------

#: A toy whose rule has TWO implementations, which is the situation round
#: 416 found twice in `self_eval.lang` (`guest_kind`'s ordering plus each
#: probe's own guard; `check_ret`'s early-out plus `check_contract`'s).
TOY_REDUNDANT = (
    "fn belt(n) { if n < 0 { 0 } else { n } }\n"
    "fn braces(n) { if belt(n) < 0 { 0 } else { belt(n) } }\n"
    'check "never negative": braces(-5) == 0\n'
    'check "unrelated arithmetic": 1 + 1 == 2\n'
)


def _run_registry_over(reg, src):
    """`run_registry` against an in-memory guest file rather than a path."""
    import tempfile
    d = tempfile.mkdtemp(prefix="checkpin-test-")
    with open(os.path.join(d, "toy"), "w", encoding="utf-8") as f:
        f.write(src)
    return C.run_registry(reg, root=d)


def test_also_applies_every_edit_and_each_locates_in_the_previous_result():
    """`also` edits are chained, not applied to the original source, so a
    later edit may target text an earlier one wrote."""
    new = C.apply_edit(TOY, {
        "id": "A1", "edit": "fn_replace", "target": "twice",
        "becomes": "fn twice(n) { n * 3 }",
        "also": [{"edit": "line_replace", "needle": "fn twice(n) { n * 3 }",
                  "becomes": "fn twice(n) { n * 4 }"}]})
    assert "fn twice(n) { n * 4 }" in new
    assert "n * 2" not in new and "n * 3" not in new


def test_an_also_chain_that_cancels_itself_out_is_equivalent_not_a_finding():
    """Two edits whose net effect is nothing must be refused for the same
    reason one such edit is: a pin whose source did not change measures the
    tool, and every check would 'pass' it."""
    with pytest.raises(C.EquivalentEdit):
        C.apply_edit(TOY, {
            "id": "A2", "edit": "fn_replace", "target": "twice",
            "becomes": "fn twice(n) { n * 3 }",
            "also": [{"edit": "line_replace",
                      "needle": "fn twice(n) { n * 3 }",
                      "becomes": "fn twice(n) { n * 2 }"}]})


def test_removing_one_copy_of_a_redundant_rule_reads_as_inert():
    """The defect the `redundant` verdict exists for: the narrow edit is
    invisible, and `inert` alone says 'write a check', which is the wrong
    advice -- the behaviour genuinely did not change."""
    r = _run({"id": "R1", "edit": "fn_replace", "target": "belt",
              "becomes": "fn belt(n) { n }",
              "guardian": "never negative"}, src=TOY_REDUNDANT)
    assert r["verdict"] == "inert" and r["n_red"] == 0


def test_removing_every_copy_of_the_same_rule_is_guarded():
    r = _run({"id": "R2", "edit": "fn_replace", "target": "belt",
              "becomes": "fn belt(n) { n }",
              "also": [{"edit": "fn_replace", "target": "braces",
                        "becomes": "fn braces(n) { belt(n) }"}],
              "guardian": "never negative"}, src=TOY_REDUNDANT)
    assert r["verdict"] == "guarded"


def test_redundant_with_demotes_inert_and_is_scored_out():
    """`inert` + a WIDER pin that went red = `redundant`: a fact about the
    code, not about the suite. It must not count against the score, or a
    file that defends a rule twice scores worse for having done so."""
    reg = {"pins": [
        {"id": "R1", "guest_file": "toy", "edit": "fn_replace",
         "target": "belt", "becomes": "fn belt(n) { n }",
         "guardian": "never negative", "redundant_with": "R2"},
        {"id": "R2", "guest_file": "toy", "edit": "fn_replace",
         "target": "belt", "becomes": "fn belt(n) { n }",
         "also": [{"edit": "fn_replace", "target": "braces",
                   "becomes": "fn braces(n) { belt(n) }"}],
         "guardian": "never negative"},
    ]}
    out = _run_registry_over(reg, TOY_REDUNDANT)
    verdicts = {r["id"]: r["verdict"] for r in out["results"]}
    assert verdicts == {"R1": C.REDUNDANT_VERDICT, "R2": "guarded"}
    assert out["findings"] == 0
    assert out["redundant"] == [{"id": "R1", "wider": "R2"}]
    assert out["score"] == 1.0
    assert out["n_pins"] == 1               # the redundant pin is scored out


def test_redundant_with_does_not_demote_when_the_wider_pin_is_absent():
    """The conservative direction, and the one `--only` hits: if the wider
    pin did not run, or did not go red, `inert` must stand."""
    reg = {"pins": [
        {"id": "R1", "guest_file": "toy", "edit": "fn_replace",
         "target": "belt", "becomes": "fn belt(n) { n }",
         "guardian": "never negative", "redundant_with": "R9"},
    ]}
    out = _run_registry_over(reg, TOY_REDUNDANT)
    assert out["results"][0]["verdict"] == "inert"
    assert out["redundant"] == []
    assert out["findings"] == 1


# --- round 416: the eval registry ----------------------------------------

@pytest.mark.parametrize("path,guest", REGISTRIES)
def test_every_pin_in_every_registry_still_locates(path, guest):
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    src = open(os.path.join(ROOT, "examples", guest), encoding="utf-8").read()
    for pin in reg["pins"]:
        assert pin["guest_file"] == "examples/" + guest, pin["id"]
        C.apply_edit(src, pin)


@pytest.mark.parametrize("path,guest", REGISTRIES)
def test_every_guardian_label_in_every_registry_is_a_real_check(path, guest):
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    src = open(os.path.join(ROOT, "examples", guest), encoding="utf-8").read()
    for pin in reg["pins"]:
        assert 'check "%s"' % pin["guardian"] in src, (pin["id"], guest)


@pytest.mark.parametrize("path,guest", REGISTRIES)
def test_every_mutated_source_still_parses(path, guest):
    """Round 416's prediction A5, kept as a test. A `collapsed` verdict
    caused by a syntax error in the pin's OWN replacement text is the tool
    measuring itself; a `collapsed` caused by the mutated SEMANTICS is a
    result. Only the second may happen at run time."""
    from whence.parser import parse
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    src = open(os.path.join(ROOT, "examples", guest), encoding="utf-8").read()
    for pin in reg["pins"]:
        parse(C.apply_edit(src, pin))     # raises ParseError if it does not


def test_the_eval_registry_pairs_directions_under_one_guardian():
    """Round 414's item 3 ("give every rule with two opposite falsifying
    edits both of them") is what this registry is FOR, so the pairing is
    pinned rather than left to the write-up."""
    with open(REGISTRY_EVAL, encoding="utf-8") as f:
        pins = json.load(f)["pins"]
    dirs = {}
    for p in pins:
        if p.get("control_expect"):
            continue
        assert p["dir"] in ("-", "+"), p["id"]
        assert p.get("predicate"), p["id"]
        dirs.setdefault(p["mechanism"].split()[0], set()).add(p["dir"])
    both = [m for m, d in dirs.items() if d == {"-", "+"}]
    assert len(both) >= 12, sorted(dirs.items())


@pytest.mark.whence_slow
def test_the_round_416_killers_actually_kill():
    """The round's own result, re-measured rather than asserted from the
    write-up. `state/whence/round-416/run-before.json` records each of these
    as a finding; after the killers each must be `guarded`."""
    with open(REGISTRY_EVAL, encoding="utf-8") as f:
        reg = {p["id"]: p for p in json.load(f)["pins"]}
    src = open(os.path.join(ROOT, "examples", "self_eval.lang"),
               encoding="utf-8").read()
    base = C.build_baseline(src)
    for pid in ("EP01p", "EP02p", "EP04p", "EP06p", "EP09p",
                "EP13m", "EP13p", "EP14m"):
        r = C.run_pin(reg[pid], src, base)
        assert r["verdict"] == "guarded", (pid, r)


@pytest.mark.whence_slow
def test_the_two_redundant_rules_are_redundant_and_not_unguarded():
    """Both halves, because either alone is an assertion. The NARROW edit
    must be invisible (the rule has a second copy) and the WIDE edit must go
    red (it is guarded once every copy is gone)."""
    with open(REGISTRY_EVAL, encoding="utf-8") as f:
        reg = {p["id"]: p for p in json.load(f)["pins"]}
    src = open(os.path.join(ROOT, "examples", "self_eval.lang"),
               encoding="utf-8").read()
    base = C.build_baseline(src)
    for narrow, wide in (("EP07m", "EP07m2"), ("EP12m", "EP12m2")):
        assert reg[narrow]["redundant_with"] == wide
        assert C.run_pin(reg[narrow], src, base)["verdict"] == "inert"
        assert C.run_pin(reg[wide], src, base)["verdict"] == "guarded"


# --- round 422: the witness, and the third cause of `inert` ---------------

#: A guest program with a branch that cannot be reached. `pick(n)`'s second
#: arm repeats the first arm's condition, so no input evaluates it.
TOY_UNREACHABLE = '''fn pick(n) {
  if n > 0 { "pos" }
  else if n > 0 { "never" }
  else { "neg" }
}
fn label(n) { "n=" + str(n) }
check "pick is positive": pick(1) == "pos"
check "pick is negative": pick(0 - 1) == "neg"
'''


def test_a_pin_with_no_witness_still_reads_inert():
    """Backwards compatibility is the point: the two registries written
    before `witness` existed must keep the verdicts they were scored with."""
    reg = {"pins": [{"id": "U0", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "edit": "line_replace",
                     "needle": 'else if n > 0 { "never" }',
                     "becomes": '  else if n > 0 { "changed" }'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    r = out["results"][0]
    assert r["verdict"] == "inert"
    assert "UNWITNESSED" in r["note"]
    assert out["inert_total"] == 1 and out["inert_witnessed"] == 0
    assert out["unreachable"] == []


def test_a_witness_that_holds_makes_an_unreachable_edit_say_so():
    reg = {"pins": [{"id": "U1", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "witness": 'pick(1) == "pos" and pick(0 - 1) == "neg"',
                     "edit": "line_replace",
                     "needle": 'else if n > 0 { "never" }',
                     "becomes": '  else if n > 0 { "changed" }'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    r = out["results"][0]
    assert r["verdict"] == C.UNREACHABLE_VERDICT
    assert r["witness_moved"] is False
    # scored OUT: not a finding, not an error, not in the denominator.
    assert out["findings"] == 0 and out["errors"] == 0
    assert out["n_pins"] == 0 and out["score"] is None
    assert [x["id"] for x in out["unreachable"]] == ["U1"]


def test_a_witness_that_moves_leaves_a_real_gap_as_inert():
    """Same shape as above but a REACHABLE edit no check covers: the witness
    goes red, so `inert` keeps its original meaning — a gap in the suite."""
    reg = {"pins": [{"id": "U2", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "witness": 'label(1) == "n=1"',
                     "edit": "line_replace",
                     "needle": 'fn label(n)',
                     "becomes": 'fn label(n) { "N=" + str(n) }'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    r = out["results"][0]
    assert r["verdict"] == "inert", r
    assert r["witness_moved"] is True
    assert out["inert_total"] == 1 and out["inert_witnessed"] == 1
    assert out["unreachable"] == []


def test_a_witness_that_is_false_unmutated_fails_its_own_pin():
    """Round 413's `BaselineNotGreen` one level down: an instrument that
    cannot distinguish anything must say so rather than judge."""
    reg = {"pins": [{"id": "U3", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "witness": 'pick(1) == "NOPE"',
                     "edit": "line_replace",
                     "needle": 'else if n > 0 { "never" }',
                     "becomes": '  else if n > 0 { "changed" }'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    r = out["results"][0]
    assert r["verdict"] == "nonviable"
    assert "not TRUE on the unmutated file" in r["note"]


def test_a_witness_going_red_is_never_counted_as_the_suite_noticing():
    """`n_red`/`co_red` must exclude witness labels — a witness firing is the
    instrument working, and counting it would turn every witnessed `inert`
    into a `shadowed` with the tool as its own co-red."""
    reg = {"pins": [{"id": "U4", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "witness": 'label(1) == "n=1"',
                     "edit": "line_replace",
                     "needle": 'fn label(n)',
                     "becomes": 'fn label(n) { "N=" + str(n) }'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    r = out["results"][0]
    assert r["n_red"] == 0 and r["co_red"] == []
    assert not any(l.startswith(C.WITNESS_PREFIX) for l in r["co_red"])


def test_the_witness_label_prefix_cannot_collide_with_a_guardian():
    """A guest file whose own check is named like a witness would make
    `did the guardian go red` ill-posed."""
    for path, guest in REGISTRIES:
        src = open(os.path.join(ROOT, "examples", guest),
                   encoding="utf-8").read()
        assert C.WITNESS_PREFIX not in src, guest


def test_every_witness_in_the_round_422_registry_is_true_unmutated():
    """The single most expensive way to be wrong here is a witness that was
    never true: it makes every `unreachable` verdict unearned. One baseline
    run answers it for the whole registry."""
    with open(REGISTRY_PLUS, encoding="utf-8") as f:
        reg = json.load(f)
    pins = [p for p in reg["pins"] if p.get("witness")]
    assert len(pins) == len(reg["pins"]), "every pin must carry a witness"
    src = open(os.path.join(ROOT, "examples", "self_host.lang"),
               encoding="utf-8").read()
    probe = src + "\n" + "\n".join(C.witness_check(p) for p in pins) + "\n"
    base = C.build_baseline(probe)
    bad = [p["id"] for p in pins
           if not base["index"].get(C.WITNESS_PREFIX + p["id"], {}).get("ok")]
    assert not bad, bad
    assert base["n_failing"] == 0


def test_the_repointed_registry_changes_labels_and_nothing_else():
    """Round 420's claim, made checkable: repointing moved the score with
    ZERO change to any edit, witness or guest line."""
    with open(REGISTRY_PLUS, encoding="utf-8") as f:
        a = {p["id"]: p for p in json.load(f)["pins"]}
    with open(REGISTRY_PLUS_REPOINTED, encoding="utf-8") as f:
        b = {p["id"]: p for p in json.load(f)["pins"]}
    assert set(a) == set(b)
    moved = 0
    for pid in a:
        for field in ("edit", "target", "needle", "becomes", "witness",
                      "dir", "occurrence", "guest_file"):
            assert a[pid].get(field) == b[pid].get(field), (pid, field)
        if a[pid]["guardian"] != b[pid]["guardian"]:
            moved += 1
            assert b[pid]["repointed_from"] == a[pid]["guardian"]
    # Round 422 repointed 20 guardians, not the 19 its own in-flight pin
    # update said; the twentieth is CP22p2, the pin round 422's
    # predictions file describes as deliberately planted to violate
    # round 420's law. Re-derived by round 423, not adjusted to fit.
    assert moved == 20, moved


def test_the_dir_registry_is_round_414s_registry_plus_one_authored_column():
    """`check-pins-dir.json`'s own header, made checkable.

    It claimed for fifteen rounds to be "Derived from ...check-pins.json;
    regenerate, do not hand-edit", and nothing in the tree has ever
    regenerated it -- the `dir` column is a per-pin judgement and is in no
    derivation, so the instruction named a producer that cannot exist. Round
    435 replaced the instruction with the part that IS re-derivable, and this
    is where it gets re-derived: same ids, same order, every other field
    byte-identical, `dir` added to every directional pin and to no control.
    """
    with open(REGISTRY, encoding="utf-8") as f:
        base = json.load(f)["pins"]
    with open(os.path.join(_C.AGI_ROOT, "state", "whence", "round-420",
                           "check-pins-dir.json"), encoding="utf-8") as f:
        dirreg = json.load(f)["pins"]
    assert [p["id"] for p in base] == [p["id"] for p in dirreg]
    for a, b in zip(base, dirreg):
        assert set(b) - set(a) == {"dir"} or set(b) == set(a), a["id"]
        for field in a:
            assert a[field] == b[field], (a["id"], field)
    directional = [p for p in dirreg if "dir" in p]
    assert len(directional) == 22
    assert [p["id"] for p in dirreg if "dir" not in p] == ["NC01"]
    assert {p["dir"] for p in directional} == {"-", "~"}


def test_deleting_a_CHECK_is_itself_an_unobservable_edit():
    """Found while writing the test above, and worth pinning: an edit whose
    only effect is to rename a `check` away changes no BEHAVIOUR, so the
    witness holds and the verdict is `unreachable`. That is the right answer
    — the pin measured the suite's own text rather than the rule — and it is
    the failure mode `guardpin`'s `misattributed` cannot express either."""
    reg = {"pins": [{"id": "U5", "guest_file": "toy",
                     "guardian": "pick is positive",
                     "witness": 'pick(0 - 1) == "neg"',
                     "edit": "line_replace",
                     "needle": 'check "pick is negative"',
                     "becomes": 'check "renamed away": 1 == 1'}]}
    out = _run_registry_over(reg, TOY_UNREACHABLE)
    assert out["results"][0]["verdict"] == C.UNREACHABLE_VERDICT


def test_n_ran_counts_the_guests_checks_and_not_the_instruments_own():
    """Round 432, closing round 428's item 4.

    That item asked whether `polarity.classify_file`'s **161** or `checkpin
    run`'s **n_ran: 162** was right, "rather than making them agree". The
    answer is that 161 is right and 162 was not a second valid population:
    `run_pin` appends this pin's WITNESS line to the mutated source and then
    counted the record it produces, while `n_red` three lines below had
    always excluded `WITNESS_PREFIX`. The instrument was in its own
    denominator.

    Both numbers now come from the guest alone, and the probe is reported
    under `n_witness` instead of being folded into the total."""
    import polarity as PO
    with open(REGISTRY_PLUS, encoding="utf-8") as f:
        reg = json.load(f)
    out = C.run_registry(reg, only={"CP18p"})
    res = (out["results"] if isinstance(out, dict) else out)[0]
    static = len(PO.classify_file(
        os.path.join(ROOT, "examples", "self_host.lang")))
    assert res["n_witness"] == 1
    assert res["n_ran"] == static
    assert res["n_ran"] + res["n_witness"] == static + 1
