"""v0.48 (round 488, language C), decision 62 — the probe is DERIVED, and
what the axis nobody varied was hiding.

Round 482 shipped `reprsweep.py`, which does not take its list of CLASSES
from anybody — it crawls. Its own next-step 3 named the half it could not
derive: *"`PROBE` is a hand-written program — the one list left in this
design. A value kind no line of it constructs is not audited; the crawl is
exhaustive over what the probe BUILDS, not over what the language can
build."* That was carried by rounds 483-487.

The measurement: the hand-written probe reached 7 of the language's 23
concrete AST node classes and 19 of 42 classes overall, and
`test_v47.py::test_the_reached_set_is_exactly_the_pinned_one` was GREEN on
all nineteen — a pin measures the probe, not the language.

The derived probe reaches 34 of 42, with the other 8 declared unreachable
WITH REASONS and checked in both directions. It found two live R2
violations in the two classes decisions 58 and 60 were written for:

    Env    559 characters at ONE 400-character name (1,783 at sixty)
    Prov   442 characters at a 400-character `let` name

Neither is a value being large. `scale_cases()` made every VALUE huge — a
3,000-element list, a 400-key record, a 5,000-character string — and every
NAME short, and an identifier is part of a rendering and is exactly as
large as the author types it. `values.REPR_CAP`'s own comment cited
`Env`'s repr as evidence the cap was already met, "(its own
`_ENV_REPR_NAMES` cut does the bounding)", and `_frame`'s docstring said
`Prov` was compliant because "all four of its fields are already bounded".
Both sentences were written by the round that introduced the rule, in the
same two files, and both were false.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import reprsweep                                      # noqa: E402
from whence import ast_nodes as A                     # noqa: E402
from whence import values as V                        # noqa: E402
from whence.interp import (Interpreter, Env,          # noqa: E402
                           _ENV_REPR_NAMES, _ENV_REPR_LISTING)

BIG_NAME = "z" * 400


# --------------------------------------------------------------------- #
class TestTheDerivation(object):
    """Each axis comes off a live table, and omission is loud."""

    def test_every_concrete_node_class_has_a_probe_line(self):
        universe = reprsweep.node_classes()
        declared = {c for (m, c) in reprsweep.UNREACHABLE
                    if m == "whence.ast_nodes"}
        assert set(reprsweep.NODE_SOURCE) | declared == universe, {
            "no_probe_line": sorted(universe - set(reprsweep.NODE_SOURCE)
                                    - declared),
            "probe_line_for_a_class_that_is_gone":
                sorted(set(reprsweep.NODE_SOURCE) - universe)}

    def test_the_node_universe_is_twentythree(self):
        """Pinned so that ADDING a node class is visible in this file even
        when somebody also adds its probe line in the same commit."""
        assert len(reprsweep.node_classes()) == 23
        assert len(reprsweep.NODE_SOURCE) == 22   # every one but Program

    def test_every_builtin_gets_a_call(self):
        probe = reprsweep.derive_probe()
        missing = [n for n in reprsweep.builtin_sigs()
                   if ("let b_%s = %s(" % (n, n)) not in probe]
        assert not missing, missing

    def test_the_builtin_universe_is_thirtyseven(self):
        assert len(reprsweep.builtin_sigs()) == 37

    def test_every_runtime_class_is_reached_or_declared_unreachable(self):
        """`gaps` is the whole point of the manifest: a class in the
        universe that the sweep neither reaches nor explains."""
        man = reprsweep.probe_manifest()
        assert man["gaps"] == [], man["gaps"]
        assert man["universe"] == 42, man
        assert man["reached"] == 34, man
        assert man["declared_unreachable"] == 8, man

    def test_no_declared_exception_is_stale(self):
        """The OTHER direction. A class that becomes reachable expires its
        own excuse instead of keeping it forever."""
        man = reprsweep.probe_manifest()
        assert man["stale_exceptions"] == [], man["stale_exceptions"]

    def test_every_unreachable_entry_carries_a_reason(self):
        for key, why in reprsweep.UNREACHABLE.items():
            assert isinstance(why, str) and len(why) > 40, key

    @pytest.mark.parametrize("cls", sorted(reprsweep.NODE_SOURCE))
    def test_every_node_source_line_reaches_its_own_class(self, cls):
        """Not "there is a line for it" — the line CONSTRUCTS it. A
        grammar change that makes a snippet parse to something else fails
        here and names the class."""
        src = "fn probe() {\n  %s\n}\n" % reprsweep._sub(
            reprsweep.NODE_SOURCE[cls], reprsweep._SMALL)
        found, _ = reprsweep.reachable(source=src)
        assert ("whence.ast_nodes", cls) in found, sorted(
            c for (m, c) in found if m == "whence.ast_nodes")

    @pytest.mark.parametrize("name", sorted(reprsweep.ARG_OVERRIDE))
    def test_every_argument_override_is_load_bearing(self, name):
        """Round 482's lesson, applied to this table: a list can be wrong
        in BOTH directions. Drop the override and the generic call derived
        from the signature kinds must miss — otherwise the entry is dead
        weight claiming a builtin needs special handling it does not."""
        sig = reprsweep.builtin_sigs()[name]
        generic = ", ".join(reprsweep.KIND_ARG.get(k, "1")
                            for _p, k in sig)
        env = Interpreter().run("let g = %s(%s)\n" % (name, generic))
        assert isinstance(env.get("g").payload, V.Miss), (
            "%s(%s) does not miss — ARG_OVERRIDE[%r] is no longer needed"
            % (name, generic, name))

    def test_no_probe_binding_is_an_accidental_miss(self):
        """A probe line that binds a miss is probing the miss path. Two
        `VALUE_SOURCE` rows did exactly that while the sweep reported a
        clean 34, because both classes had a second door — see that
        table's comment on insertion order."""
        env = Interpreter().run(reprsweep.PROBE)
        declared = {"v_miss", "v_miss2"}
        bad = []
        for name, val in env.vars.items():
            if name in declared or not (name.startswith("b_")
                                        or name.startswith("v_")):
                continue
            if isinstance(val.payload, V.Miss):
                bad.append((name, val.payload.reasons))
        assert not bad, bad


# --------------------------------------------------------------------- #
class TestAgainstTheHandWrittenProbe(object):
    """The derived probe must not lose what the list had."""

    def test_the_legacy_probe_reaches_seven_of_twentythree_node_classes(self):
        """The measurement this round exists for. Green in `test_v47.py`
        the whole time it was true."""
        found, _ = reprsweep.reachable(source=reprsweep.LEGACY_PROBE)
        ast = {c for (m, c) in found if m == "whence.ast_nodes"}
        assert len(ast) == 7, sorted(ast)
        assert len(found) == 19, len(found)

    def test_the_derived_probe_reaches_everything_the_hand_written_one_did(
            self):
        """A superset, not a bigger number. The FIRST derived probe
        written here reached 34 classes and LOST `values.Miss` — a miss is
        produced by FAILURE and is named by neither the builtin table nor
        the node table, so two derivations covered more and still covered
        less."""
        legacy, _ = reprsweep.reachable(source=reprsweep.LEGACY_PROBE)
        derived, _ = reprsweep.reachable()
        assert set(legacy) <= set(derived), sorted(set(legacy)
                                                   - set(derived))
        assert ("whence.values", "Miss") in derived


# --------------------------------------------------------------------- #
class TestWhatTheNameAxisFound(object):
    """Two live R2 violations, in the two classes the rule was for."""

    def test_env_repr_is_bounded_by_name_LENGTH_not_only_name_count(self):
        env = Interpreter().run("let %s = 1\n" % BIG_NAME)
        assert len(repr(env)) <= V.REPR_CAP, len(repr(env))
        # what the v0.47 formula produced, recomputed here so the
        # magnitude is pinned rather than remembered
        names = list(env.vars)
        v047 = ("<whence %s: %d name%s%s, %d enclosing — a SCOPE, not a "
                "value; Interpreter.run() returns this, and the program's "
                "results are the names INSIDE it (env.get(\"x\"))>"
                % ("scope", len(names), "" if len(names) == 1 else "s",
                   " (%s)" % ", ".join(names[:_ENV_REPR_NAMES]), 1))
        assert len(v047) == 559, len(v047)

    def test_env_repr_is_bounded_with_sixty_long_names(self):
        src = "".join("let %s%d = 1\n" % (BIG_NAME, i) for i in range(60))
        env = Interpreter().run(src)
        assert len(repr(env)) <= V.REPR_CAP, len(repr(env))
        assert ", ...56 more" in repr(env), repr(env)

    def test_the_exact_count_survives_the_cut(self):
        """`, ...N more` is appended AFTER the listing cut on purpose: the
        count is the one thing in that string a reader can act on."""
        src = "".join("let %s%d = 1\n" % (BIG_NAME, i) for i in range(9))
        assert repr(Interpreter().run(src)).count(", ...5 more") == 1

    def test_prov_repr_is_bounded_when_detail_is_a_long_identifier(self):
        env = Interpreter().run("let %s = 1\n" % BIG_NAME)
        prov = env.get(BIG_NAME)
        assert len(repr(prov)) <= V.REPR_CAP, len(repr(prov))
        # `_clip` is the design and `_cap` the backstop: the useful tail
        # must survive, which a bare final cut would have eaten
        assert repr(prov).endswith("value=1)"), repr(prov)
        v047 = "Prov(%r, %r, line=%r, %d inputs, value=%s)" % (
            prov.op, prov.detail, prov.line, len(prov.inputs), prov.show)
        assert len(v047) == 442, len(v047)

    def test_mergedprov_repr_is_bounded_when_the_called_fn_is_long(self):
        src = ("fn %s(i, acc) { if i <= 0 { acc } else "
               "{ %s(i - 1, acc + i) } }\nlet r = %s(50, 0)\n"
               % (BIG_NAME, BIG_NAME, BIG_NAME))
        env = Interpreter().run(src)
        merged = [n for n in env.get("r").inputs
                  if isinstance(n, V.MergedProv)]
        assert merged, "no MergedProv in this tail loop"
        assert len(repr(merged[0])) <= V.REPR_CAP, len(repr(merged[0]))
        assert repr(merged[0]).startswith("MergedProv(")

    def test_the_whole_sweep_is_clean_at_scale(self):
        rep = reprsweep.audit()
        bad = [(c["case"], c["violations"]) for c in rep["scale"]
               if c["violations"]]
        assert not bad, bad
        assert rep["violations"] == 0


# --------------------------------------------------------------------- #
class TestR2LivesInOneFunction(object):
    """Decision 62's structural half."""

    def test_cap_is_the_only_place_repr_cap_is_compared(self):
        """Three copies of one cut is a rule that can be right in two of
        them, which is what happened. `_cap` is the only comparison
        against `REPR_CAP` left in the implementation."""
        import re
        cut = re.compile(r"\s*if len\(.*REPR_CAP")
        hits = []
        for name in sorted(os.listdir(os.path.join(ROOT, "whence"))):
            if not name.endswith(".py"):
                continue
            path = os.path.join(ROOT, "whence", name)
            with open(path) as fh:
                for i, line in enumerate(fh, 1):
                    if cut.match(line):
                        hits.append((name, i, line.strip()))
        assert len(hits) == 1, hits
        assert hits[0][0] == "values.py", hits[0]

    @pytest.mark.parametrize("cls,mk", [
        ("Prov", lambda: Interpreter().run("let %s = 1\n" % BIG_NAME)
                                      .get(BIG_NAME)),
        ("Env", lambda: Interpreter().run("let %s = 1\n" % BIG_NAME)),
        ("Block", lambda: Interpreter().run(
            'fn f() {\n  "%s"\n}\n' % ("x" * 5000)).get("f").payload.body),
        ("Record", lambda: Interpreter().run(
            "let r = @{%s: 1}\n" % BIG_NAME).get("r").payload),
    ])
    def test_every_repr_shape_obeys_the_one_cap(self, cls, mk):
        obj = mk()
        assert len(repr(obj)) <= V.REPR_CAP, (cls, len(repr(obj)))

    def test_clip_keeps_the_tail_and_cap_is_the_backstop(self):
        assert V._clip("abc", 10) == "abc"
        assert len(V._clip("a" * 100, 10)) == 10
        assert V._clip("a" * 100, 10).endswith("…")
        assert len(V._cap("a" * 1000)) == V.REPR_CAP
        assert V._cap("a" * 1000, ">").endswith("…>")
        assert len(V._cap("a" * 1000, ">")) == V.REPR_CAP
        assert V._cap("short") == "short"


# --------------------------------------------------------------------- #
class TestTheInstrument(object):
    """An audit is two claims and one of them is the auditor's."""

    def test_the_scale_pass_keeps_the_worst_instance_not_the_first(self):
        """The reason the first version of this round's own fix could not
        be falsified: `instances()` keeps the FIRST object of each class
        the crawl hits, and on the scale probe that is a 58-character
        `Prov` for `v_list`, not the 400-character-named one. Checking one
        arbitrary member of a class checks the class only if every member
        reprs the same length — which is exactly what a variable-length
        field makes false."""
        first = reprsweep.instances(reprsweep.SCALE_PROBE)
        worst = reprsweep.worst_instances(reprsweep.SCALE_PROBE)
        key = ("whence.values", "Prov")
        assert len(repr(worst[key][0])) > len(repr(first[key][0]))

    def test_reverting_the_three_reprs_turns_the_sweep_red(self):
        """The falsifier. Restores in a `finally` — round 481 left a
        mutant applied to `harness/wiring_audit.py` when its round was
        killed and cost round 482 a health check to work out why."""
        def v047_prov(self):
            return "Prov(%r, %r, line=%r, %d inputs, value=%s)" % (
                self.op, self.detail, self.line, len(self.inputs),
                self.show)

        def v047_merged(self):
            return ("MergedProv(%r, %r, line=%r, x%d, %d inputs, value=%s)"
                    % (self.op, self.detail, self.line, self.count,
                       len(self.inputs), self.show))

        def v047_env(self):
            names = list(self.vars)
            shown = names[:_ENV_REPR_NAMES]
            listing = ", ".join(shown)
            extra = len(names) - len(shown)
            if extra > 0:
                listing += ", ...%d more" % extra
            depth, e = 0, self.parent
            while e is not None:
                depth, e = depth + 1, e.parent
            return ("<whence %s: %d name%s%s, %d enclosing — a SCOPE, not "
                    "a value; Interpreter.run() returns this, and the "
                    "program's results are the names INSIDE it "
                    "(env.get(\"x\"))>"
                    % ("globals" if self.interp is not None else "scope",
                       len(names), "" if len(names) == 1 else "s",
                       " (%s)" % listing if names else "", depth))

        keep = (V.Prov.__repr__, V.MergedProv.__repr__, Env.__repr__)
        try:
            V.Prov.__repr__ = v047_prov
            V.MergedProv.__repr__ = v047_merged
            Env.__repr__ = v047_env
            rep = reprsweep.audit()
            killed = sorted(c["case"] for c in rep["scale"]
                            if c["violations"])
            assert killed == ["derived/Env", "derived/MergedProv",
                              "derived/Prov"], killed
            assert rep["violations"] == 3, rep["violations"]
        finally:
            V.Prov.__repr__, V.MergedProv.__repr__, Env.__repr__ = keep
        assert reprsweep.audit()["violations"] == 0

    def test_reachable_does_not_bind_the_probe_as_a_default_argument(self):
        """`def reachable(source=PROBE, ...)` binds the module string ONCE
        at def time, so a caller who rebinds `reprsweep.PROBE` keeps
        auditing the old program and gets a plausible answer. Cost one
        wrong measurement in this round before it was noticed."""
        keep = reprsweep.PROBE
        try:
            reprsweep.PROBE = "let only = 1\n"
            found, _ = reprsweep.reachable()
            assert ("whence.ast_nodes", "Block") not in found, sorted(found)
        finally:
            reprsweep.PROBE = keep
        assert ("whence.ast_nodes", "Block") in reprsweep.reachable()[0]

    def test_value_source_rows_are_emitted_first_and_in_insertion_order(self):
        """`Env.__repr__` lists `_ENV_REPR_NAMES` (4) names in DECLARATION
        order. With the value rows last, the scale probe's 400-character
        name sat at position 74 and was never listed, so the pass that
        exists to exercise the name axis ran with it switched off."""
        scale = reprsweep.SCALE_PROBE
        env = Interpreter().run(scale)
        listed = list(env.vars)[:_ENV_REPR_NAMES]
        assert any(BIG_NAME in n for n in listed), listed
        # the LISTING is itself cut, so the 400 characters do not all
        # survive into the repr — what must survive is that the long name
        # is the one being listed at all
        assert "vzzzzzzzzzz" in repr(env), repr(env)[:120]
        assert _ENV_REPR_LISTING == 60

    def test_the_crawl_still_completes(self):
        _found, stats = reprsweep.reachable()
        assert not stats["exhausted"], stats
        _found, stats = reprsweep.reachable(source=reprsweep.SCALE_PROBE)
        assert not stats["exhausted"], stats


# --------------------------------------------------------------------- #
class TestWhatWasDeliberatelyNotChanged(object):

    def test_the_ast_family_had_no_violation_at_any_scale(self):
        """The negative result, and it is the point of enumerating: 16 of
        the 23 node classes had never been audited, all 23 share ONE
        generated `__repr__`, and the enlarged probe found nothing wrong
        with any of them at 5,000-character literals, 400-character
        identifiers and 3,000-digit numerals. Decision 60's fix was
        general even though the evidence for it was not."""
        rep = reprsweep.audit()
        ast_rows = [c for c in rep["scale"]
                    if c["case"].startswith("derived/")
                    and c["class"] in reprsweep.node_classes()]
        assert len(ast_rows) == 22, len(ast_rows)
        assert not [c for c in ast_rows if c["violations"]]

    def test_a_short_name_env_repr_is_unchanged_from_v045(self):
        """Decision 58's own wording, still exact. The new cuts fire only
        on names longer than the listing budget."""
        env = Interpreter().run("let nums = [1]\nlet total = 1\n")
        assert repr(env).startswith(
            "<whence scope: 2 names (nums, total), 1 enclosing")

    def test_prov_keeps_its_constructor_shaped_repr(self):
        """Round 482 settled that outlawing `Prov(...)` would be an
        aesthetic preference wearing a checker. v0.48 bounds it; it does
        not reshape it."""
        env = Interpreter().run("let x = 1 + 2\n")
        assert repr(env.get("x")).startswith("Prov('let', 'x', line=1,")

    def test_miss_repr_still_diverges_from_show_payload(self):
        """Decision 52's snapshot contract, pinned as unchanged for the
        second round running."""
        env = Interpreter().run('let m = num("3O")\n')
        assert "miss:" in repr(env.get("m").payload)
        assert V.show_payload(env.get("m").payload) == "miss"


class TestTheCLI(object):
    """`--manifest` exists so the coverage of each derived axis is
    readable without importing anything — the number this round's finding
    turns on (19 of 42) was invisible from the CLI in v0.47."""

    def _run(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "reprsweep.py")] + list(args),
            cwd=ROOT, capture_output=True, text=True)

    def test_manifest_reports_the_universe_and_exits_zero(self):
        proc = self._run("--manifest")
        assert proc.returncode == 0, proc.stderr[-600:]
        assert "universe 42, reached 34" in proc.stdout, proc.stdout
        assert "gaps 0" in proc.stdout, proc.stdout

    def test_manifest_json_is_the_same_object_the_audit_carries(self):
        import json
        proc = self._run("--manifest", "--json")
        assert proc.returncode == 0, proc.stderr[-600:]
        assert json.loads(proc.stdout) == reprsweep.probe_manifest()

    def test_the_default_audit_leads_with_the_coverage_line(self):
        proc = self._run()
        assert proc.returncode == 0, proc.stderr[-600:]
        assert proc.stdout.startswith("derived probe: universe 42, reached 34")
        assert proc.stdout.rstrip().endswith("violations: 0")
