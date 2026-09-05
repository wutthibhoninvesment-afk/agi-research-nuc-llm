"""`builtinlive.py` — is a builtin live IN WHENCE, not in Python?

Round 504 (language C). The module's provocation is in its own docstring;
what this file pins is the part that can silently drift: the shadowing model
(which is a claim about `interp.eval_Block`, not a heuristic), the
call/ref split, and the two failure modes that must never be confused —
a program this repo cannot PARSE (a fact about the corpus) versus a program
this module cannot WALK (a bug here, which round 504 shipped for one run and
which reported itself as 23 unparseable examples).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import builtinlive as BL            # noqa: E402
from whence import interp as I      # noqa: E402


NAMES = BL.builtin_names()


def scan(src):
    return BL.uses_in(src)


def counts(src):
    uses, naive, shadows = scan(src)
    return ([(u.name, u.kind) for u in uses],
            [(u.name, u.kind) for u in naive],
            [(s.name, s.binder) for s in shadows])


# ------------------------------------------------------------ the roster

def test_the_roster_is_the_interpreters_own_registry():
    assert len(NAMES) == len(I._make_builtin_table())
    assert "print" in NAMES and "fold" in NAMES and "contrast" in NAMES
    assert len(set(NAMES)) == len(NAMES)


def test_every_registered_builtin_is_installed_into_a_fresh_env():
    """The premise the whole module rests on: reachability in PYTHON is not
    the interesting question here, because `_install_builtins` defines all of
    them into every environment unconditionally."""
    interp = I.Interpreter()
    for n in NAMES:
        assert interp.globals.get(n) is not None, n


# ------------------------------------------------------------ use kinds

def test_a_call_is_a_call():
    uses, _, _ = scan("print(1)")
    assert [(u.name, u.kind, u.line) for u in uses] == [("print", "call", 1)]


def test_a_bare_name_is_a_ref_because_a_builtin_is_a_value():
    uses, _, _ = scan("let p = print\np(1)")
    assert [(u.name, u.kind) for u in uses] == [("print", "ref")]


def test_a_builtin_passed_to_a_higher_order_builtin_is_both_kinds():
    uses, _, _ = scan("print(map(str, [1, 2]))")
    assert sorted((u.name, u.kind) for u in uses) == [
        ("map", "call"), ("print", "call"), ("str", "ref")]


def test_a_field_named_like_a_builtin_is_not_a_use():
    uses, _, _ = scan('let r = @{len: 1}\nprint(r.len)')
    assert [(u.name, u.kind) for u in uses] == [("print", "call")]


def test_a_string_containing_a_builtin_name_is_not_a_use():
    uses, _, _ = scan('let s = "len(x) and fold(f, a, xs)"')
    assert uses == []


# ------------------------------------------------------------ shadowing

def test_a_let_shadows_the_builtin_for_the_rest_of_its_scope():
    resolved, naive, shadows = counts("let len = 1\nlet n = len + 2")
    assert resolved == []
    assert naive == [("len", "ref")]
    assert shadows == [("len", "let")]


def test_a_use_before_the_binding_is_still_the_builtin():
    """`eval_Block` populates its `inner` Env as it goes: nothing is
    hoisted, so a `let` binds only for the statements after it."""
    resolved, naive, _ = counts("let a = len([1])\nlet len = 1\nlet b = len")
    assert resolved == [("len", "call")]
    assert len(naive) == 2


def test_a_shadow_inside_a_block_does_not_leak_out_of_it():
    src = ("let x = if true { let len = 0\nlen } else { 1 }\n"
           "let y = len([1, 2])")
    resolved, naive, shadows = counts(src)
    # Shape first, magnitude last: `assertshadow.py` reddens a test where a
    # count assert can shadow a shape assert below it, and the shape is the
    # claim this node is named for.
    assert resolved == [("len", "call")]
    assert shadows == [("len", "let")]
    assert len(naive) == 2


def test_a_parameter_shadows_over_the_whole_body():
    resolved, naive, shadows = counts("fn f(str) { str }\nlet r = f(1)")
    assert resolved == []
    assert naive == [("str", "ref")]
    assert shadows == [("str", "param")]


def test_a_function_name_shadows_inside_its_own_body_because_it_recurses():
    src = "fn len(xs) { if true { 0 } else { len(xs) } }\nlet n = len([1])"
    resolved, naive, shadows = counts(src)
    assert resolved == []
    assert shadows == [("len", "fn")]
    assert len(naive) == 2


def test_shadowing_can_only_remove_uses_never_add_them():
    for src in ("let len = 1\nlen",
                "fn f(len) { len }",
                "print(len([1]))",
                "let a = len([1])\nlet len = 2\nlet b = len"):
        resolved, naive, _ = counts(src)
        assert len(resolved) <= len(naive), src


# --------------------------------------------------- the walker's own limit

def test_a_three_thousand_term_chain_walks_without_a_recursionerror():
    """`tests/test_v04.py:241` builds this program, the interpreter runs it
    on a trampoline, and round 504's first (recursive) walker raised
    `RecursionError` on it and filed the result as an UNPARSEABLE corpus
    program. The expression spine is walked iteratively for this reason."""
    src = "let result = 1" + " + 1" * 3000 + "\nprint(result)"
    res = BL.scan_program(src)
    assert res["ok"], res["error"]
    assert [(u.name, u.kind) for u in res["uses"]] == [("print", "call")]


# ------------------------------------------------- parse vs walk failures

def test_an_unparseable_program_is_a_parse_failure_and_says_so():
    res = BL.scan_program("let x = @{a: 1")
    assert res["ok"] is False
    assert res["error_kind"] == "parse"
    assert "ParseError" in res["error"]


def test_a_bug_in_the_walker_is_a_walk_failure_not_a_corpus_defect(monkeypatch):
    def boom(self, seq, bound):
        raise AttributeError("'_Walk' object has no attribute 'other'")
    monkeypatch.setattr(BL._Walk, "stmts", boom)
    res = BL.scan_program("print(1)")
    assert res["ok"] is False
    assert res["error_kind"] == "walk"


def test_the_census_refuses_to_publish_when_the_walker_failed(monkeypatch,
                                                             tmp_path):
    (tmp_path / "a.lang").write_text("print(len([1]))\n")

    def boom(self, seq, bound):
        raise RuntimeError("walker is broken")
    monkeypatch.setattr(BL._Walk, "stmts", boom)
    c = BL.census(include_tests=False, directory=str(tmp_path))
    assert c["n_walk_errors"] == 1
    assert c["n_unparseable"] == 0
    text = "\n".join(BL.census_lines(c))
    assert "WALK-ERROR" in text
    assert "REFUSING TO PUBLISH" in text


def test_uses_in_raises_a_failure_that_still_names_the_side():
    with pytest.raises(BL._Failed) as exc:
        BL.uses_in("let x = @{a: 1")
    assert exc.value.kind == "parse"


# ------------------------------------------------------------- the census

def test_a_directory_census_splits_example_from_unused(tmp_path):
    (tmp_path / "a.lang").write_text("print(len([1, 2]))\n")
    c = BL.census(include_tests=False, directory=str(tmp_path))
    assert c["n_programs"] == 1 and c["n_parsed"] == 1
    by = dict((r["name"], r["verdict"]) for r in c["rows"])
    assert by["print"] == BL.VERDICT_EXAMPLE
    assert by["len"] == BL.VERDICT_EXAMPLE
    assert by["contrast"] == BL.VERDICT_UNUSED
    assert c["counts"][BL.VERDICT_UNUSED] == len(NAMES) - 2


def test_test_only_is_a_verdict_of_its_own(tmp_path):
    (tmp_path / "a.lang").write_text("print(1)\n")
    progs = [{"origin": "example", "where": "a.lang", "src": "print(1)"},
             {"origin": "test", "where": "t.py:1", "src": "let n = len([1])"}]
    c = BL.census(programs=progs)
    by = dict((r["name"], r["verdict"]) for r in c["rows"])
    assert by["print"] == BL.VERDICT_EXAMPLE
    assert by["len"] == BL.VERDICT_TEST_ONLY
    assert by["fold"] == BL.VERDICT_UNUSED


def test_an_unparseable_program_is_reported_not_dropped(tmp_path):
    (tmp_path / "ok.lang").write_text("print(1)\n")
    (tmp_path / "bad.lang").write_text("let x = @{a: 1\n")
    c = BL.census(include_tests=False, directory=str(tmp_path))
    assert c["n_programs"] == 2 and c["n_parsed"] == 1
    assert [u["where"] for u in c["unparseable"]] == ["bad.lang"]
    assert "UNPARSEABLE" in "\n".join(BL.census_lines(c))


# ---------------------------------------------------------------- ledger

def test_the_ledger_check_reports_a_moved_verdict(tmp_path):
    progs = [{"origin": "example", "where": "a.lang", "src": "print(1)"}]
    c1 = BL.census(programs=progs)
    path = str(tmp_path / "ledger.json")
    BL._write(path, BL.ledger_view(c1))
    findings, _ = BL.check(c1, path)
    assert findings == []

    progs.append({"origin": "test", "where": "t.py:1",
                  "src": "let n = len([1])"})
    c2 = BL.census(programs=progs)
    findings, _ = BL.check(c2, path)
    # ROUND 518: `counts` moves with the verdict, and until this round
    # NOTHING compared it -- this assertion is the one that had to change
    # when B002 landed, which is itself the finding. B001 stays first and
    # keeps naming the builtin.
    assert findings == [
        ("B001", "len", "verdict moved unused -> used_by_test_only"),
        ("B002", "counts", "2 value(s) moved (unused, used_by_test_only)")]


def test_a_missing_ledger_is_a_finding_not_a_crash(tmp_path):
    c = BL.census(programs=[{"origin": "example", "where": "a.lang",
                             "src": "print(1)"}])
    findings, rec = BL.check(c, str(tmp_path / "nope.json"))
    assert rec is None and findings[0][0] == "B000"


# ------------------------------------------------- claims about THIS corpus

@pytest.mark.whence_slow
def test_the_live_corpus_walks_with_no_walker_error():
    c = BL.census()
    assert c["n_walk_errors"] == 0, c["walk_errors"]
    assert c["n_parsed"] > 800


@pytest.mark.whence_slow
def test_no_documented_builtin_is_dead_surface():
    """Round 504's headline, and a real ratchet rather than a pinned count:
    a builtin added to the registry and demonstrated by no program in
    `examples/` turns this red, which is the correct time to hear about it.
    `scopecall` reported all 37 of these as not-live; every one is called by
    a program this language SHIPS."""
    c = BL.census()
    assert c["counts"][BL.VERDICT_UNUSED] == 0, c["by_verdict"]["unused"]
    assert c["counts"][BL.VERDICT_TEST_ONLY] == 0, \
        c["by_verdict"]["used_by_test_only"]
    assert c["counts"][BL.VERDICT_EXAMPLE] == len(NAMES)


@pytest.mark.whence_slow
def test_every_unparseable_corpus_program_is_a_parse_error_on_purpose():
    """`examples/` holds machine-written programs that do not parse (see
    `curecheck.py`). They must fail as ParseError with a Whence diagnostic,
    not as some other exception leaking out of the lexer or parser."""
    c = BL.census()
    assert c["n_unparseable"] > 0
    for u in c["unparseable"]:
        assert u["origin"] == "example", u
        assert u["error"].startswith("ParseError:"), u


# --------------------------------------------------- the ledger GATE (518) --

def _b_pinned(tmp_path):
    import json                                       # noqa: PLC0415
    c = BL.census(programs=[{"origin": "example", "where": "a.lang",
                             "src": "print(1)"}])
    path = str(tmp_path / "ledger.json")
    BL._write(path, BL.ledger_view(c))
    assert BL.check(c, path)[0] == []
    return c, path, json


def test_b002_sees_the_three_keys_b001_does_not(tmp_path):
    """ROUND 516 measured this verb at 1 of its ledger's 4 top-level keys.
    B001 reads `by_verdict`; nothing read `counts`, `n_builtins` or the
    `_regenerate` command the artefact declares about itself."""
    c, path, json = _b_pinned(tmp_path)
    for key in ("counts", "n_builtins", "_regenerate"):
        doc = json.load(open(path, encoding="utf-8"))
        doc.pop(key)
        BL._write(path, doc)
        findings, _rec = BL.check(c, path)
        assert [(code, subj) for code, subj, _w in findings] == \
            [("B002", key)], (key, findings)
        BL._write(path, BL.ledger_view(c))


def test_b001_still_owns_by_verdict_and_b002_does_not_repeat_it(tmp_path):
    """The exclusion is safe because B001 sees the key DELETED: an empty
    `was` map reports every builtin as `None -> <verdict>`."""
    c, path, json = _b_pinned(tmp_path)
    doc = json.load(open(path, encoding="utf-8"))
    doc.pop("by_verdict")
    BL._write(path, doc)
    findings, _rec = BL.check(c, path)
    codes = set(code for code, _s, _w in findings)
    assert codes == {"B001"}, findings
    assert len(findings) == c["n_builtins"]


def test_a_ledger_with_no_findings_has_no_residual_either(tmp_path):
    c, path, _json = _b_pinned(tmp_path)
    assert BL.check(c, path)[0] == []
