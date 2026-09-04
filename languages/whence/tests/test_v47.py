"""v0.47 (round 482, language C), decision 60 — the sweep decision 58
asked for, and what enumerating found that a list could not.

Decision 58 (round 476) wrote a general rule into the SPEC registry —

    a value this implementation HANDS A CALLER is a surface

— gave `Env` a `__repr__`, and applied it to nothing else. Round 476's own
next-step 2 named eight candidate classes from memory and asked somebody
to sweep. It was carried, un-run, by rounds 477, 478, 479, 480 and 481.

`reprsweep.py` is the sweep. It does not take the list: it crawls the
public object graph from what `Interpreter.run` actually returns, and it
found **11 of 19 reachable classes** in violation at the commit before
this version, against round 476's remembered eight — the extras being
`Interpreter` itself, `MergedProv`, and the whole AST node family. This
file holds every one of those findings open, plus the two defects the
crawl had in its FIRST draft, both of which made it report a clean sweep
while blind.

The tests are grouped by what they would catch:

  * `TestTheRule` — decision 60's four properties against every class the
    crawl reaches, which is the gate that turns red when somebody adds a
    value class and forgets its repr.
  * `TestWhatEnumerationFound` — the specific classes a hand-written list
    missed, each pinned individually so that fixing the sweep's crawl can
    never quietly drop one.
  * `TestTheInstrument` — the crawl's own two failure modes. An audit is
    two claims and one of them is the auditor's.
  * `TestWhatWasDeliberatelyNotChanged` — decision 52's snapshot contract,
    `Prov`'s constructor-shaped repr, and the fact that the WHENCE-level
    surface was already clean. A round that "fixes" any of these three is
    undoing a decision, not a defect.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import reprsweep                                     # noqa: E402
from whence import values as V                       # noqa: E402
from whence.interp import Interpreter                # noqa: E402
from whence.parser import parse                      # noqa: E402
from whence import ast_nodes as A                    # noqa: E402


#: Every class the crawl reaches by a PUBLIC path from `run()`. Pinned as
#: a set, not a count: a count moves for two different reasons (a class
#: added, a class no longer reached) and the diff would not say which.
#: Round 476's next-step 2 listed eight candidates from memory; six are on
#: that list.
#:
#: v0.48 (round 488), decision 62: 19 -> 34, and NOT because anything was
#: added to the language. The probe this pin was taken against was a
#: hand-written program that constructed 7 of the 23 concrete AST node
#: classes, so this set read as "what the language exposes" and measured
#: "what one program happened to build". `reprsweep.PROBE` is now derived
#: from three live tables and `tests/test_v48.py` owns the totality gates;
#: this pin is the SECOND gate, the one that catches a silent shrink.
PINNED_REACHED = {
    ("whence.ast_nodes", "Binary"),
    ("whence.ast_nodes", "Block"),
    ("whence.ast_nodes", "BoolLit"),
    ("whence.ast_nodes", "Call"),
    ("whence.ast_nodes", "Check"),
    ("whence.ast_nodes", "ExprStmt"),
    ("whence.ast_nodes", "FieldAccess"),
    ("whence.ast_nodes", "FnDef"),
    ("whence.ast_nodes", "FnExpr"),
    ("whence.ast_nodes", "If"),
    ("whence.ast_nodes", "Index"),
    ("whence.ast_nodes", "Let"),
    ("whence.ast_nodes", "ListLit"),
    ("whence.ast_nodes", "MissLit"),
    ("whence.ast_nodes", "NameRef"),
    ("whence.ast_nodes", "Num"),
    ("whence.ast_nodes", "RecordLit"),
    ("whence.ast_nodes", "Rescue"),
    ("whence.ast_nodes", "Snip"),
    ("whence.ast_nodes", "Str"),
    ("whence.ast_nodes", "Unary"),
    ("whence.ast_nodes", "Why"),
    ("whence.interp", "Env"),
    ("whence.interp", "Interpreter"),
    ("whence.values", "Builtin"),
    ("whence.values", "Closure"),
    ("whence.values", "Explanation"),
    ("whence.values", "Guess"),
    ("whence.values", "MergedProv"),
    ("whence.values", "Miss"),
    ("whence.values", "PMap"),
    ("whence.values", "Prov"),
    ("whence.values", "Record"),
    ("whence.values", "WList"),
}


class TestTheRule(object):
    """Decision 60's four properties, against live values."""

    def test_no_reachable_class_violates_decision_60(self):
        """The gate. Adding a value class without a repr turns this red in
        the round that adds it, which is the latency decision 58's own
        defect did not have: `Env` printed a heap address for every round
        from v0.1 to round 476, and what finally reported it was a bug
        report from outside this program."""
        rep = reprsweep.audit()
        bad = [(r["class"], r["violations"]) for r in rep["rows"]
               if r["violations"]]
        assert not bad, bad
        assert rep["violations"] == 0, rep["violations"]

    def test_the_reached_set_is_exactly_the_pinned_one(self):
        """A sweep that quietly stops reaching a class reports zero
        violations, which is the same output as a clean tree. The pinned
        set is what tells the two apart."""
        found, _ = reprsweep.reachable()
        assert set(found) == PINNED_REACHED, {
            "unpinned_but_reached": sorted(set(found) - PINNED_REACHED),
            "pinned_but_unreached": sorted(PINNED_REACHED - set(found))}

    def test_r1_the_string_that_caused_a_false_bug_report(self):
        """`<whence.interp.Env object at 0x7d6a91893740>` is the literal
        evidence `CLAUDE.md`'s `CRITICAL MISSION #476` published against
        `b_fold`. No class on the caller's path can produce that shape
        now, and the class that did is only one of nine that could."""
        rep = reprsweep.audit()
        for row in rep["rows"]:
            assert "object at 0x" not in row["repr"], row
            assert "whence." not in row["repr"], row

    def test_r2_is_bounded_at_scale_not_merely_short_in_practice(self):
        """`WList.__repr__` was 156,787 characters for `range(0, 3000)`
        and `PMap.__repr__` 22,986 for a 400-key record. Both were "short
        in practice" for every value anybody had happened to print."""
        rep = reprsweep.audit()
        assert rep["scale"], "scale_cases() produced nothing"
        for case in rep["scale"]:
            assert not case["violations"], case
            assert case["repr_len"] <= V.REPR_CAP, case

    def test_r4_a_constructor_repr_names_its_own_class(self):
        """R4 is the row the sweep found rather than inherited. `Prov` and
        `MergedProv` are the only two constructor-shaped reprs left, so
        this is not a hypothetical rule with no subject."""
        rep = reprsweep.audit()
        ctor = [r for r in rep["rows"]
                if reprsweep._CTOR_RE.match(r["repr"])]
        assert {r["class"] for r in ctor} == {"Prov", "MergedProv"} | {
            n for _, n in PINNED_REACHED if _ == "whence.ast_nodes"}, \
            sorted(r["class"] for r in ctor)
        for r in ctor:
            assert reprsweep._CTOR_RE.match(r["repr"]).group(1) == r["class"], r

    @pytest.mark.whence_slow
    def test_r3_the_same_reprs_in_three_processes(self):
        """Round 481 found a 66-round-old nondeterminism in
        `wiring_audit.best_incoming` by computing one value twice, and
        asked for this shape of check on other derived values. Slow-marked
        because it is three interpreter starts, not because it is
        optional."""
        res = reprsweep.seed_check()
        assert res["ok"], res
        assert res["n_classes"] == len(PINNED_REACHED), res


class TestWhatEnumerationFound(object):
    """The nine classes round 476's remembered list does not name."""

    def test_the_interpreter_itself_was_the_one_nobody_listed(self):
        """`Interpreter()` is line one of every embedding, and it was the
        only class on the public path from `run()` with no repr at all.
        A list of VALUE classes cannot contain it, because it is not a
        value — which is exactly why its repr says so."""
        interp = Interpreter()
        env = interp.run("let a = 1\n")
        assert env.parent.interp is interp
        text = repr(interp)
        assert "object at 0x" not in text
        assert "ENGINE" in text and "run(source)" in text
        assert len(text) <= V.REPR_CAP

    def test_merged_prov_named_itself_prov_and_dropped_its_only_slot(self):
        """It inherited `Prov.__repr__`, which passed R1, R2 and R3. A
        repr that is useless is obviously useless; one that is wrong is
        not, and this one dropped `count` — the entire reason the class
        exists."""
        env = Interpreter().run(
            "fn loop(i, acc) { if i <= 0 { acc } else "
            "{ loop(i - 1, acc + i) } }\nlet looped = loop(50, 0)\n")
        merged = env.get("looped").inputs[0]
        assert isinstance(merged, V.MergedProv)
        text = repr(merged)
        assert text.startswith("MergedProv("), text
        assert "x%d" % merged.count in text, text

    def test_an_ast_node_is_reachable_and_was_bounded_by_the_program(self):
        """`Closure.body` is public, so the parse tree is one attribute
        away from a caller. The generated repr recursed over the whole
        subtree: 15,471 characters for a 400-statement body, and no bound
        at all in principle."""
        body = "\n".join("let v%d = %d" % (i, i) for i in range(400))
        env = Interpreter().run("fn wide() {\n%s\nv0\n}\n" % body)
        node = env.get("wide").payload.body
        assert isinstance(node, A.Node)
        assert len(repr(node)) <= V.REPR_CAP

    def test_the_ast_cut_is_structural_and_keeps_the_shape(self):
        """Depth and breadth, not a character truncation — the same move
        `values.SHOW_NEST` already makes one layer up. A character cut
        would end a node's repr mid-identifier, and the only reason to
        print an AST node is to see its shape."""
        env = Interpreter().run(
            "fn loop(i, acc) { if i <= 0 { acc } else "
            "{ loop(i - 1, acc + i) } }\nlet z = 1\n")
        text = repr(env.get("loop").payload.body)
        assert text.startswith("Block(stmts=["), text
        assert "…" in text, text
        assert text.endswith(")"), text          # not cut mid-token
        wide = Interpreter().run(
            "fn w() {\n%s\nv0\n}\n"
            % "\n".join("let v%d = %d" % (i, i) for i in range(50)))
        assert ", …" in repr(wide.get("w").payload.body)

    def test_nothing_consumed_the_unbounded_ast_repr(self):
        """The justification for bounding it, kept live. The one suite
        that reprs a parse tree is `test_parser_differential.py`, and it
        reprs `canon_host(...)`'s TUPLES rather than these nodes. If that
        ever changes, a differential test would be comparing silently
        truncated serializations, and this assertion is what says so
        first."""
        from tests import test_parser_differential as D
        canon = D.canon_host(parse("let a = 1\nfn f(x) { x + 1 }\n"))
        assert isinstance(canon, tuple), type(canon)
        assert not any(isinstance(x, A.Node) for x in _flatten(canon))

    @pytest.mark.parametrize("name,src,expect", [
        ("Record", "let r = @{a: 1, b: 2}\n", "record @{a: 1, b: 2}"),
        ("Closure", "fn f(x, y) { x }\n", "fn f(x, y)"),
        ("Builtin", "let a = 1\n", None),
        ("Explanation", "let w = why 1\n", "why "),
        ("Guess", 'let q = guess(7, 0.5, "sensor")\n', "guess 0.5 (sensor)"),
        ("Miss", "let m = nosuch(1)\n", "miss: unbound name 'nosuch'"),
    ])
    def test_each_payload_class_renders_its_value(self, name, src, expect):
        """One row per class round 476 DID name, so a regression in any
        single one fails on its own line rather than inside the sweep's
        aggregate."""
        env = Interpreter().run(src)
        if name == "Builtin":
            obj = env.parent.get("map").payload
            assert repr(obj) == "<whence builtin map (2 args)>", repr(obj)
            return
        obj = env.get(list(env.vars)[-1]).payload
        assert type(obj).__name__ == name, (name, type(obj).__name__)
        assert expect in repr(obj), (name, repr(obj))
        assert repr(obj).startswith("<whence "), repr(obj)


class TestTheInstrument(object):
    """`reprsweep.py`'s own two defects, both of which had it reporting a
    clean sweep while blind. Neither was found by reasoning about the
    crawl; both were found by a number that looked wrong."""

    def test_the_crawl_must_retain_every_object_it_has_seen(self):
        """`seen` holds `id()`s, and an id names an object only while that
        object is alive. `Prov.inputs` returns a FRESH tuple whenever
        `_ins` is not already one, so the crawl allocates, records the id,
        drops the object, and then skips a live object CPython handed the
        freed address to. The cost was `MergedProv`.

        Pinned as the PRECONDITION rather than as the symptom, because the
        symptom depends on the allocator: assert that `inputs` really does
        build a new object per access, and that `MergedProv` really is
        reached through it."""
        env = Interpreter().run(
            "fn loop(i, acc) { if i <= 0 { acc } else "
            "{ loop(i - 1, acc + i) } }\nlet looped = loop(50, 0)\n")
        prov = env.get("looped")
        assert not isinstance(prov._ins, tuple), \
            "the fresh-tuple branch of Prov.inputs is no longer taken"
        assert prov.inputs is not prov.inputs
        found, _ = reprsweep.reachable()
        path = found[("whence.values", "MergedProv")]
        assert ".inputs[" in path, path

    def test_the_crawl_stops_at_the_edge_of_the_whence_graph(self):
        """Descending any public attribute walks out through
        `Interpreter`'s into module `__dict__`s and never terminates: the
        first draft ran to its 60,000-step budget and reported 13 of 19
        classes. Every class it reaches is a whence class, and it
        finishes."""
        found, stats = reprsweep.reachable()
        assert not stats["exhausted"], stats
        assert stats["steps"] < stats["limit"] // 10, stats
        assert all(m.startswith("whence") for m, _ in found)

    def test_the_public_path_rule_excludes_exactly_the_avl_node(self):
        """`Record._map` reaches a `PMap` and `PMap._root` a `_PNode`. The
        loose rule would call an AVL tree node a caller surface; the
        strict one reaches the same `PMap` through the public
        `Record.fields` and stops. The delta is measured rather than
        asserted in prose, so a future private slot that exposes something
        real shows up here."""
        public, _ = reprsweep.reachable()
        private, _ = reprsweep.reachable(private=True)
        assert set(public) <= set(private)
        assert {n for _, n in set(private) - set(public)} == {"_PNode"}


class TestWhatWasDeliberatelyNotChanged(object):
    """Three things this version leaves alone on purpose. Each is a
    decision, and a later round 'fixing' one is reversing it."""

    def test_decision_52s_snapshot_contract_is_untouched(self):
        """`show_payload` of a Miss is still the bare word `miss` under a
        limit, and still names the reasons at `limit=None`. `Miss.__repr__`
        diverges from the bounded snapshot ON PURPOSE — a repr is read by
        somebody holding the object and asking what went wrong — and that
        divergence is only legitimate while the snapshot itself is
        unchanged."""
        env = Interpreter().run("let m = nosuch(1)\n")
        miss = env.get("m").payload
        assert V.show_payload(miss) == "miss"
        assert V.show_payload(miss, None).startswith("miss ")
        assert "unbound name 'nosuch'" in repr(miss)
        assert "unbound name 'nosuch'" not in V.show_payload(miss)

    def test_prov_keeps_its_constructor_shaped_repr(self):
        """It passes all four rules. Decision 60's rule is the four
        properties, not a house style — outlawing `Prov(...)` would be an
        aesthetic preference wearing a checker, and `Prov` is the
        provenance NODE rather than a value payload, which is the host's
        own case for a constructor call."""
        env = Interpreter().run("let n = 42\n")
        text = repr(env.get("n"))
        assert text.startswith("Prov('let', 'n', line=1"), text
        bad, _ = reprsweep.check_repr(env.get("n"))
        assert not bad, bad

    def test_the_whence_level_surface_was_already_clean(self):
        """Measured before anything was changed and pinned here: no
        program could get a heap address into a Whence-level rendering.
        The leak was confined to the Python embedding API — which is why
        `test_v12.py`'s and `test_contract_message_differential.py`'s
        `"object at 0x" not in reason` assertions had held for rounds
        while nine classes reprred as addresses one attribute away."""
        prog = ('fn f(x){x}\nprint(f)\nprint(map)\nlet z = f + 1\n'
                'print(z)\nlet r = @{a: 1}\nprint(why r)\n'
                'let g = guess(1, 0.5, "s")\nprint(g)\nprint([f])\n'
                'print(str(f))\nprint(at(r, "zz"))\n')
        path = os.path.join(ROOT, "run.py")
        src = os.path.join(HERE, "_v47_tmp.lang")
        with open(src, "w") as fh:
            fh.write(prog)
        try:
            proc = subprocess.run([sys.executable, path, src],
                                  capture_output=True, text=True, cwd=ROOT)
        finally:
            os.remove(src)
        assert "object at 0x" not in proc.stdout, proc.stdout
        assert "whence." not in proc.stdout, proc.stdout
        assert "<fn f>" in proc.stdout and "<builtin map>" in proc.stdout


def _flatten(obj):
    """Every leaf of a nested tuple/list, for the AST-repr guard."""
    if isinstance(obj, (tuple, list)):
        for item in obj:
            for leaf in _flatten(item):
                yield leaf
    else:
        yield obj
