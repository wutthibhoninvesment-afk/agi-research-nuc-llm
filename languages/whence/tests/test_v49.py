#!/usr/bin/env python3
"""v0.49 (round 492, language C) — decision 63: the inputs, and who sizes
them.

v0.48 derived the PROBE from three live tables and varied three tokens in
it: a string literal's body, an identifier, a run of digits. Those are the
three things a Whence PROGRAM can make arbitrarily long, and every probe
this implementation has ever run is a program. Round 488's own next-step 1
asked the question that framing cannot answer — *list the inputs each repr
interpolates and say which of them an author sizes* — and the answer is
that one of them is not in the language at all. `Interpreter.__repr__`
interpolates `self.max_depth`, a PUBLIC constructor argument of the
embedding API: `repr(Interpreter(max_depth=10 ** 500))` was 645 characters
against a `REPR_CAP` of 240, and no program of any size moves it.

Two instruments find it independently and neither subsumes the other:
`routing_manifest()` is static and total (`Interpreter.__repr__` was the
one repr whose delegate closure did not contain `values._cap`), and
`cap_response()` is behavioural (lower the cap, re-take every repr) and
reports its own `vacuous` rows rather than counting them as passes.

Widening the universe from three hand-listed modules to the whole package
found the second defect: `timetravel.TimeTravelDebugger` reprred as
`<whence.timetravel.TimeTravelDebugger object at 0x...>` — decision 58's
ORIGINAL failure string — and its `snapshot()` raised `TypeError` against
every real `Env`, under eleven green tests that all pass a double.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import reprsweep                                      # noqa: E402
from whence import values as V                        # noqa: E402
from whence.interp import Interpreter                 # noqa: E402
from whence.timetravel import TimeTravelDebugger      # noqa: E402

BIG_NAME = "z" * 400


@pytest.fixture(scope="module")
def manifest():
    return reprsweep.axis_manifest()


@pytest.fixture(scope="module")
def routing():
    return reprsweep.routing_manifest()


@pytest.fixture(scope="module")
def caps():
    return reprsweep.cap_response()


# --------------------------------------------------------------------- #
class TestTheEnumeration(object):
    """The subject is the EXPRESSIONS, derived from the source."""

    def test_every_interpolated_input_has_an_axis(self, manifest):
        """An expression that becomes characters and that nobody has said
        who sizes is the v0.48 failure with the names changed."""
        assert manifest["unclassified"] == [], manifest["unclassified"]

    def test_no_axis_row_is_stale(self, manifest):
        """The keys are the unparsed expression TEXT, so editing a repr
        expires its own classification. This gate fired for real inside
        round 492: adding `_clip` around `self.max_depth` changed the key
        from `self.max_depth` to `_clip(str(self.max_depth))`, and the
        table reported one stale row and one unclassified one."""
        assert manifest["stale"] == [], manifest["stale"]

    def test_every_author_sized_axis_has_a_witness(self, manifest):
        """A row in `AXES` claiming an author sizes something, with
        nothing that makes it large, is a table claiming coverage it does
        not have — which is exactly what v0.48's identifier axis was."""
        assert manifest["axes_without_witness"] == []
        assert manifest["witnesses_without_axis"] == []

    def test_every_axis_used_is_declared(self, manifest):
        assert manifest["unknown_axis"] == []

    def test_the_counts(self, manifest):
        """Pinned so that adding a repr, or an interpolation, is visible
        in this file even when the same commit classifies it."""
        assert manifest["sources"] == 19, manifest["sources"]
        assert manifest["inputs"] == 89, manifest["inputs"]
        assert manifest["by_family"] == {
            "text": 15, "structure": 23, "constant": 13,
            "internal": 36, "embedding": 2}, manifest["by_family"]
        assert len(manifest["author_sized_axes"]) == 13

    def test_the_deriver_catches_a_bare_returned_repr(self):
        """`ast_nodes._node_field` ends in `return repr(v)` — no format,
        no concatenation — and that is where a 5,000-character string
        literal entered the AST repr in v0.48. A deriver that only reads
        `%` operands misses the input that had the defect."""
        inputs = reprsweep.repr_inputs()["whence.ast_nodes._node_field"]
        assert "repr(v)" in inputs
        assert reprsweep.INPUT_AXIS[
            ("whence.ast_nodes._node_field", "repr(v)")] == "text.node_scalar"

    def test_the_delegate_closure_sees_a_method(self):
        """`_simple.<locals>.__repr__` is `_cap(self._repr_at(0))`, and
        `_repr_at` is a closure in the class dict, not a module global. A
        resolver that reads module globals only stopped at `__repr__` and
        never reached `_node_field` — the function v0.48's own violation
        was fixed in."""
        from whence import ast_nodes as A
        closure = reprsweep.delegate_closure(A.Num.__dict__["__repr__"],
                                             A.Num)
        assert "whence.ast_nodes._node_field" in closure, sorted(closure)

    def test_the_delegate_closure_sees_a_function_local_import(self):
        """The same repr reaches `_cap` by `from whence.values import _cap`
        INSIDE its body. Without that branch it looks exactly like
        `Interpreter.__repr__` did — a repr that calls nothing — and the
        two must not look alike."""
        from whence import ast_nodes as A
        closure = reprsweep.delegate_closure(A.Num.__dict__["__repr__"],
                                             A.Num)
        assert "whence.values._cap" in closure, sorted(closure)

    def test_the_boundary_is_not_descended_into(self):
        """`show_payload` is declared a boundary, so its own inputs are not
        enumerated here — but what CROSSES the boundary is named."""
        sources = reprsweep.repr_sources()
        assert "whence.values.show_payload" not in sources
        guess = reprsweep.repr_inputs()["whence.values.Guess.__repr__"]
        assert "show_payload(self, SHOW_LIMIT * 2)" in guess

    def test_every_boundary_entry_is_load_bearing(self):
        """A boundary naming a function nothing calls is a stale excuse."""
        called = set()
        for key, fn in reprsweep.repr_sources().items():
            src = reprsweep._fn_source(fn)
            for boundary in reprsweep.DELEGATE_BOUNDARY:
                if boundary.rsplit(".", 1)[-1] + "(" in src:
                    called.add(boundary)
        assert called == set(reprsweep.DELEGATE_BOUNDARY), {
            "declared": sorted(reprsweep.DELEGATE_BOUNDARY),
            "actually_called": sorted(called)}


# --------------------------------------------------------------------- #
class TestTheAxisThatWasNotInTheProgram(object):
    """The embedding family: inputs no Whence source text can move."""

    def test_the_pre_fix_interpreter_repr_was_over_the_cap(self):
        """The magnitude, recomputed rather than remembered."""
        interp = Interpreter(max_depth=10 ** 500)
        n = len(interp.globals.vars)
        v048 = ("<whence interpreter: %d builtin%s, max_depth %s — the "
                "ENGINE, not a value or a scope; run(source) executes a "
                "program and returns its top-level Env>"
                % (n, "" if n == 1 else "s", interp.max_depth))
        assert len(v048) == 645, len(v048)
        assert len(v048) > V.REPR_CAP

    def test_the_interpreter_repr_is_bounded_at_any_max_depth(self):
        for exponent in (0, 3, 100, 500):
            interp = Interpreter(max_depth=10 ** exponent)
            assert len(repr(interp)) <= V.REPR_CAP, (exponent,
                                                     len(repr(interp)))

    def test_the_sentence_survives_the_cut(self):
        """`_cap` alone left 240 characters of the author's integer and ate
        the tail. `_clip` is the design and `_cap` the backstop — decision
        62's rule, applied one class over."""
        text = repr(Interpreter(max_depth=10 ** 500))
        assert text.endswith("returns its top-level Env>"), text[-60:]
        assert "…" in text
        assert len(text) == 184, len(text)

    def test_the_default_repr_is_byte_identical_to_v048(self):
        """The fix must not move the ordinary rendering."""
        text = repr(Interpreter())
        assert text == ("<whence interpreter: 37 builtins, max_depth 20000 "
                        "— the ENGINE, not a value or a scope; run(source) "
                        "executes a program and returns its top-level Env>")
        assert len(text) == 149

    def test_no_program_can_move_the_embedding_axis(self):
        """The reason a derived, program-shaped probe could never have
        found this. `derive_probe(scale=True)` renders every node class and
        every builtin with 5,000-character tokens; every `Interpreter` it
        reaches still has the DEFAULT `max_depth`, because `max_depth` is
        not a thing Whence source can say."""
        found = reprsweep.instances(reprsweep.SCALE_PROBE)
        interp = found[("whence.interp", "Interpreter")][0]
        assert interp.max_depth == Interpreter.DEFAULT_MAX_DEPTH
        assert "max_depth" not in reprsweep.SCALE_PROBE

    def test_the_embedding_family_has_exactly_two_inputs(self, manifest):
        assert manifest["by_axis"]["embedding.max_depth"] == 1
        assert manifest["by_axis"]["embedding.global_count"] == 1

    def test_the_global_count_witness_actually_moves_the_count(self):
        cases = dict(reprsweep.axis_cases())
        interp = cases["embedding.global_count/%d"
                       % reprsweep._GLOBAL_PAD]
        assert len(interp.globals.vars) == reprsweep._GLOBAL_PAD + 37
        assert "10037 builtins" in repr(interp), repr(interp)


# --------------------------------------------------------------------- #
class TestTheTwoCapChecks(object):
    """Round 488's next-step 4: replace a source regex with something
    behavioural. It took TWO checks, because neither one is enough."""

    def test_every_reached_repr_routes_through_cap(self, routing):
        assert routing["unrouted"] == [], routing["unrouted"]

    def test_the_static_check_catches_a_repr_that_stops_routing(self):
        """Falsification: put v0.48's `Interpreter.__repr__` back and the
        static check must name it. A gate nobody has seen fail is a gate
        nobody has tested."""
        original = Interpreter.__repr__

        def unrouted(self):
            n = len(self.globals.vars)
            return ("<whence interpreter: %d builtin%s, max_depth %s>"
                    % (n, "" if n == 1 else "s", self.max_depth))
        try:
            Interpreter.__repr__ = unrouted
            rep = reprsweep.routing_manifest()
            assert ["whence.interp", "Interpreter"] in rep["unrouted"]
        finally:
            Interpreter.__repr__ = original
        assert reprsweep.routing_manifest()["unrouted"] == []

    def test_the_behavioural_check_catches_it_too(self):
        """And independently: lowering `REPR_CAP` finds the same repr
        without reading a line of source."""
        original = Interpreter.__repr__

        def unrouted(self):
            n = len(self.globals.vars)
            return ("<whence interpreter: %d builtin%s, max_depth %s>"
                    % (n, "" if n == 1 else "s", self.max_depth))
        try:
            Interpreter.__repr__ = unrouted
            rep = reprsweep.cap_response()
            assert "class:interp.Interpreter" in rep["failing"], rep["failing"]
        finally:
            Interpreter.__repr__ = original

    def test_the_static_check_is_blind_to_a_discarded_cut(self):
        """`routes_through_cap` asks whether `_cap` is in the delegate
        closure. A repr that CALLS it and throws the result away passes
        the static check and fails the behavioural one — which is why
        both exist and neither is called 'the' cap test."""
        original = Interpreter.__repr__

        def calls_and_discards(self):
            from whence.values import _cap
            _cap("ignored")
            return "x" * 300
        try:
            Interpreter.__repr__ = calls_and_discards
            assert reprsweep.routing_manifest()["unrouted"] == []
            rep = reprsweep.cap_response()
            assert "class:interp.Interpreter" in rep["failing"]
        finally:
            Interpreter.__repr__ = original

    def test_the_behavioural_check_is_blind_to_a_short_repr(self):
        """And the other way round: a repr shorter than the lowest cap
        passes behaviourally without demonstrating anything. That is
        reported as `vacuous`, not as a pass — a gate that passes on an
        input it never exercised is worth what round 490's
        `sar --strict`-on-zero-captures was worth."""
        original = Interpreter.__repr__

        def always_short(self):
            return "<whence i>"
        try:
            Interpreter.__repr__ = always_short
            rep = reprsweep.cap_response()
            assert "class:interp.Interpreter" not in rep["failing"]
            vacuous = [r["subject"] for r in rep["rows"] if r["vacuous"]]
            assert "class:interp.Interpreter" in vacuous
            assert reprsweep.routing_manifest()["unrouted"] == [
                ["whence.interp", "Interpreter"]]
        finally:
            Interpreter.__repr__ = original

    def test_the_vacuous_count_is_reported_and_nonzero(self, caps):
        """Reported honestly rather than hidden: 11 of 64 subjects are
        already under the lowest cap. If this ever becomes 0 the check got
        stronger; if it approaches 64 the check has stopped meaning
        anything, and either way it is on the CLI."""
        assert caps["vacuous"] == 11, caps["vacuous"]
        assert caps["subjects"] == 64, caps["subjects"]
        assert caps["failing"] == []

    def test_the_old_regex_gate_still_holds(self):
        """v0.48's `test_cap_is_the_only_place_repr_cap_is_compared` is
        NOT deleted. It is a different claim — that the CUT is written
        once — and it stays green; the two new checks answer a question it
        never asked, which is whether every repr goes through it."""
        import re
        cut = re.compile(r"\s*if len\(.*REPR_CAP")
        hits = []
        for name in sorted(os.listdir(os.path.join(ROOT, "whence"))):
            if name.endswith(".py"):
                with open(os.path.join(ROOT, "whence", name)) as fh:
                    hits += [(name, i) for i, line in enumerate(fh, 1)
                             if cut.match(line)]
        assert len(hits) == 1 and hits[0][0] == "values.py", hits


# --------------------------------------------------------------------- #
class TestTheWitnesses(object):
    """A witness that does not move its own axis is the v0.48 failure:
    `Env`'s scale case ran for six rounds with its axis switched off."""

    def test_the_scope_depth_witness_really_is_deep(self):
        env, depth = reprsweep.scope_depth_witness()
        assert depth == 39, depth
        assert "39 enclosing" in repr(env), repr(env)

    def test_scope_depth_needs_nested_definitions_not_recursion(self):
        """Whence scopes are LEXICAL, so a recursive call does not deepen
        the chain — a call Env's parent is the closure's DEFINING Env.
        This is why the axis needed a witness of its own shape."""
        src = ("fn down(n) { if n <= 0 { fn() { 1 } } else "
               "{ down(n - 1) } }\nlet f = down(200)\n")
        closure = Interpreter().run(src).get("f").payload
        depth, env = 0, closure.env
        while env.parent is not None:
            depth += 1
            env = env.parent
        assert depth <= 3, depth

    def test_the_merge_count_witness_really_merges(self):
        cases = dict(reprsweep.axis_cases())
        node = cases["structure.merge_count/loop-%d"
                     % reprsweep._MERGE_COUNT]
        assert type(node).__name__ == "MergedProv"
        # N + 1: the outer call plus N tail recursions are ONE merged node
        assert node.count == reprsweep._MERGE_COUNT + 1, node.count
        assert "x%d" % (reprsweep._MERGE_COUNT + 1) in repr(node), repr(node)

    def test_the_reason_count_witness_overflows_the_listing(self):
        miss = reprsweep._reason_count_witness()
        assert len(miss.reasons) > V._MISS_REPR_REASONS
        assert "more)" in repr(miss), repr(miss)

    def test_the_identifier_witness_actually_lists_the_long_name(self):
        cases = dict(reprsweep.axis_cases())
        env = cases["text.identifier/env-400"]
        assert "zzz" in repr(env), repr(env)
        assert len(repr(env)) <= V.REPR_CAP

    def test_the_arity_witness_covers_the_spellings_that_exist(self):
        """`Builtin.__repr__` renders three spellings and its comment said
        "all three spellings appear in `_install_builtins`". Measured over
        the live global scope: 33 int, 4 pair, ZERO None. The witness
        covers the two that exist; the third is reachable only by
        constructing a `Builtin`, which the next test does."""
        live = {}
        for name, value in Interpreter().globals.vars.items():
            builtin = getattr(value, "payload", None)
            if type(builtin).__name__ == "Builtin":
                arity = builtin.arity
                key = ("none" if arity is None else
                       "pair" if isinstance(arity, tuple) else "int")
                live.setdefault(key, []).append(name)
        assert sorted(live) == ["int", "pair"], sorted(live)
        assert len(live["int"]) == 33 and len(live["pair"]) == 4
        assert sorted(live["pair"]) == ["contrast", "diverge", "range",
                                        "steps"]
        cases = dict(reprsweep.axis_cases())
        seen = set()
        for name in ("len", "guess", "note"):
            arity = cases["structure.arity/builtin-%s" % name].arity
            seen.add("pair" if isinstance(arity, tuple) else "int")
        assert "int" in seen

    def test_the_any_arity_branch_renders(self):
        """The one spelling no builtin in this tree uses. Kept because
        "None for any" is `Builtin.__slots__`'s stated contract; tested
        because an untested branch of a repr is how `MergedProv`
        introduced itself as a `Prov` for six rounds."""
        builtin = V.Builtin("anything", None, lambda i, a, l: None)
        assert repr(builtin) == "<whence builtin anything (any arity)>"
        pair = V.Builtin("ranged", (1, 2), lambda i, a, l: None)
        assert repr(pair) == "<whence builtin ranged (1-2 args)>"
        one = V.Builtin("single", 1, lambda i, a, l: None)
        assert repr(one) == "<whence builtin single (1 arg)>"

    def test_every_axis_witness_is_bounded(self):
        over = [(label, len(repr(obj)))
                for label, obj in reprsweep.axis_cases()
                if len(repr(obj)) > V.REPR_CAP]
        assert over == [], over


# --------------------------------------------------------------------- #
class TestTheUniverseIsThePackage(object):
    """v0.48's `gaps: 0` was scoped to three of the package's seven
    modules, and the set of modules was itself a hand-written list."""

    def test_the_universe_is_every_class_in_the_package(self):
        man = reprsweep.probe_manifest()
        assert man["universe"] == 48, man["universe"]
        assert len(reprsweep.package_classes()) == 48

    def test_the_widening_added_exactly_six_classes(self):
        old = ({("whence.ast_nodes", c) for c in reprsweep.node_classes()}
               | reprsweep.runtime_classes())
        added = reprsweep.package_classes() - old
        assert added == {
            ("whence.ast_nodes", "Node"),
            ("whence.lexer", "Token"),
            ("whence.lexer", "LexError"),
            ("whence.parser", "Parser"),
            ("whence.parser", "ParseError"),
            ("whence.timetravel", "TimeTravelDebugger")}, sorted(added)

    def test_no_gaps_and_no_stale_exceptions(self):
        man = reprsweep.probe_manifest()
        assert man["gaps"] == [], man["gaps"]
        assert man["stale_exceptions"] == [], man["stale_exceptions"]

    def test_nothing_reached_is_outside_the_universe(self):
        """The direction `probe_manifest` never computed. It is 0 at HEAD
        — a negative CONTROL, not a finding — and it is the check that
        would have said so if a reached class lived in a module the
        universe did not contain."""
        assert reprsweep.probe_manifest()["outside_universe"] == []

    def test_the_five_new_unreachable_entries_are_really_unreachable(self):
        found, _stats = reprsweep.reachable()
        for key in [("whence.ast_nodes", "Node"), ("whence.lexer", "Token"),
                    ("whence.lexer", "LexError"),
                    ("whence.parser", "Parser"),
                    ("whence.parser", "ParseError")]:
            assert key in reprsweep.UNREACHABLE, key
            assert key not in found, key

    def test_the_constructed_surface_is_audited_like_a_crawled_one(self):
        rep = reprsweep.audit()
        row = [r for r in rep["rows"]
               if r["class"] == "TimeTravelDebugger"]
        assert len(row) == 1, [r["class"] for r in rep["rows"]]
        assert row[0]["violations"] == []
        assert row[0]["path"] == "constructed by the caller"


# --------------------------------------------------------------------- #
class TestTheClassNobodyEnumerated(object):
    """`timetravel.TimeTravelDebugger` — five rounds after decision 58
    outlawed the string, still printing it."""

    def test_the_repr_has_no_host_leak(self):
        text = repr(reprsweep._ttd_witness())
        for marker in reprsweep.LEAK_MARKERS:
            assert marker not in text, (marker, text[:120])

    def test_the_repr_is_bounded_at_scale(self):
        assert len(repr(reprsweep._ttd_witness())) <= V.REPR_CAP

    def test_the_repr_keeps_the_count_whole(self):
        """Same rule `Env` follows: the listing is cut, the count is not,
        because the count is the one thing a reader can act on."""
        ttd = reprsweep._ttd_witness(n_checkpoints=9, name_len=400)
        assert "9 checkpoints" in repr(ttd), repr(ttd)
        assert ", ...5 more" in repr(ttd), repr(ttd)

    def test_an_empty_debugger_reprs_without_a_listing(self):
        text = repr(TimeTravelDebugger())
        assert "0 checkpoints" in text
        assert "(" not in text.split("—")[0], text

    def test_snapshot_works_against_a_real_env(self):
        """The defect the witness found. `snapshot` read the name as
        `env.get('_last_snap_name', 'unnamed')` and `Env.get` takes ONE
        argument, so this raised `TypeError` for every real `Env` — under
        eleven green tests that all pass a double."""
        env = Interpreter().run("let a = 1\n")
        ttd = TimeTravelDebugger()
        assert ttd.snapshot(env) == "snap('unnamed') ✓"
        assert ttd.creation_order == ["unnamed"]
        assert ttd.checkpoints["unnamed"]["vars"].keys() == env.vars.keys()

    def test_snapshot_names_a_checkpoint_from_a_whence_binding(self):
        env = Interpreter().run('let _last_snap_name = "before"\n'
                                'let a = 1\n')
        ttd = TimeTravelDebugger()
        assert ttd.snapshot(env) == "snap('before') ✓"
        assert ttd.creation_order == ["before"]

    def test_the_existing_doubles_still_work(self):
        """The fix must not break the eleven tests that were green — they
        name their checkpoints through a `get(key, default)` the real
        `Env` does not have, and that path is deliberately kept."""
        class NamedEnv(object):
            def __init__(self, name):
                self.vars = {"a": 1}
                self._name = name

            def get(self, key, default=None):
                return self._name if key == "_last_snap_name" else default
        ttd = TimeTravelDebugger()
        assert ttd.snapshot(NamedEnv("step1")) == "snap('step1') ✓"
        assert ttd.creation_order == ["step1"]


# --------------------------------------------------------------------- #
class TestTheClassificationsThatWereMeasured(object):

    def test_prov_op_is_a_fixed_vocabulary(self):
        """`constant.op_token` is a classification, so it is measured. The
        day an op embeds an author's identifier this fails, and the row in
        `AXES` is wrong rather than quietly stale."""
        env = Interpreter().run(reprsweep.PROBE)
        ops, seen, queue = set(), set(), list(env.vars.values())
        while queue:
            node = queue.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            if type(node).__name__ in ("Prov", "MergedProv"):
                ops.add(node.op)
                queue.extend(node.inputs)
        assert len(ops) == 45, sorted(ops)
        assert max(len(op) for op in ops) == 10, sorted(ops, key=len)[-3:]
        assert all(" " not in op for op in ops), sorted(ops)

    def test_the_whole_sweep_is_clean(self):
        rep = reprsweep.audit()
        assert rep["violations"] == 0, [
            (r.get("case") or r["class"], r["violations"])
            for r in rep["rows"] + rep["scale"] + rep["axes"]
            if r["violations"]]

    def test_the_cli_exits_nonzero_on_a_bad_axis_table(self):
        """`--inputs` is a gate, not a report."""
        original = dict(reprsweep.INPUT_AXIS)
        try:
            reprsweep.INPUT_AXIS[("whence.values.Prov.__repr__",
                                  "self.no_such_field")] = "text.identifier"
            assert reprsweep.main(["--inputs"]) == 1
        finally:
            reprsweep.INPUT_AXIS.clear()
            reprsweep.INPUT_AXIS.update(original)
        assert reprsweep.main(["--inputs"]) == 0
