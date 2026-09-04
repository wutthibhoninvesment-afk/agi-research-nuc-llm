"""`specreg.py` — the SPEC decision registry audited as a numbering system.

Round 464 (language C).

What is worth testing about this module is not that it counts entries. It is
that the three things it claims are *structural* really are:

  * its notion of "a registry entry" is the SAME one `xref_check` uses, so
    the tree never grows two opinions about which ids are defined;
  * every finding fires on a synthetic document built to trigger it AND
    stays silent on the near-miss beside it — a checker only tested on the
    corpus it was written for is a checker tested on one point;
  * `next_free` is derived from EVERY site. That is the whole mechanism:
    round 462 minted an id in the prose site only, so a round that reads the
    registry to pick the next number picks one that is already taken, and
    the failure surfaces rounds later as a disagreement about what the id
    says rather than as a missing sentence.

The live-corpus assertions are deliberately few and specific. `SPEC.md` is
edited by a language round roughly every four rounds; a test that pins its
shape too tightly is a test that goes red for correct work, and this
workspace has a name for that (see `skills/named-guardian-must-go-red`).
"""

import importlib.util
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import specreg  # noqa: E402

REPO = specreg.REPO
XREF = os.path.join(REPO, "skills", "skill-authoring", "scripts",
                    "xref_check.py")


needs_repo = pytest.mark.skipif(
    not os.path.exists(XREF),
    reason="xref_check.py is outside a bare languages/whence checkout")


def _load_xref():
    spec = importlib.util.spec_from_file_location("xref_check_for_test", XREF)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# synthetic documents
# --------------------------------------------------------------------------

HEAD = "# Spec\n\nintro\n\n## Anti-mainstream design decisions\n"
TAIL = "\n## Syntax\n\nafter the registry\n"


def doc(entries, extra="", reserved=None):
    """A minimal SPEC-shaped document.

    `entries` is [(id, title_with_tag)]; `extra` is appended AFTER the
    registry section, which is where prose `Decision N` sections live in the
    real document.
    """
    body = ""
    if reserved:
        body += "%d-%d. *(reserved — never minted.)*\n" % reserved
    for n, title in entries:
        body += "%d. **%s** body text.\n" % (n, title)
    return HEAD + body + TAIL + extra


def codes(text, **kw):
    kw.setdefault("with_citations", False)
    return sorted(f.code for f in specreg.audit(spec_text=text, **kw)["findings"])


# --------------------------------------------------------------------------
# the two parsers must agree — this is the anti-drift pin
# --------------------------------------------------------------------------

@needs_repo
def test_the_two_registry_parsers_agree_on_the_live_spec():
    """`specreg` needs entry BODIES, which `ordinal_registry` discards, so it
    has its own parse. Two parsers of one registry that agree only by
    inspection drift; this is what stops that."""
    xref = _load_xref()
    ids, status = xref.ordinal_registry(REPO, specreg.SPEC_REL,
                                        specreg.REGISTRY_HEADING)
    assert status == "ok"
    assert specreg.registry_ids() == ids


@needs_repo
def test_the_citation_scope_is_x001s_scope():
    """`specreg` restates X001's scope as a literal so it runs from a bare
    whence checkout. A restatement that is never compared is a copy."""
    xref = _load_xref()
    x001 = next(f for f in xref.FAMILIES if f.code == "X001")
    assert x001.scope_re.pattern == specreg.CITE_SCOPE_RE.pattern


# --------------------------------------------------------------------------
# the live corpus
# --------------------------------------------------------------------------

def test_the_live_spec_registry_has_no_errors():
    res = specreg.audit()
    errs = [str(f) for f in res["findings"] if f.severity == "ERROR"]
    assert errs == [], "\n".join(errs)


def test_decision_56_is_in_the_registry_and_not_only_in_prose():
    """The repair round 464 made. Round 462 wrote the prose section and not
    the entry; `xref_check` caught it only because the section heading is
    accidentally a citation of itself."""
    text = specreg.read_spec()
    assert 56 in specreg.registry_ids(text)
    assert 56 in {s["id"] for s in specreg.parse_sections(text)}


def test_next_free_is_past_every_site_and_past_the_reserved_range():
    text = specreg.read_spec()
    n = specreg.next_free(text)
    minted = specreg.minted_ids(text)
    assert n not in minted
    assert n > max(minted)
    assert not any(lo <= n <= hi for lo, hi, _ in specreg.parse_reserved(text))


def test_the_reserved_range_is_declared_and_is_not_an_entry():
    """Round 348's design: 14-26 is written in a form `ordinal_registry` does
    not count, so a citation of an id inside it still dangles."""
    text = specreg.read_spec()
    assert specreg.parse_reserved(text)[0][:2] == (14, 26)
    assert not (set(range(14, 27)) & specreg.registry_ids(text))


def test_this_module_cites_no_unminted_decision():
    """`specreg.py` lives inside X001's authoritative scope, so an id named
    in its own docstring as an example is a live dangling citation. The
    first draft of the docstring did exactly that."""
    text = specreg.read_spec()
    minted = specreg.minted_ids(text)
    src = open(os.path.join(specreg.HERE, "specreg.py"), encoding="utf-8").read()
    cited = {int(m.group(1)) for m in specreg.CITE_RE.finditer(src)}
    assert cited <= minted, "unminted ids cited: %s" % sorted(cited - minted)


def test_audit_is_cheap_enough_for_a_tier():
    """Wired into `run_tests_fast.sh` via this file, so its cost is the
    tier's cost. The claim in the round file is <5 s; assert an order of
    magnitude of headroom rather than a stopwatch value, which would be a
    flake on a loaded box (`nproc` here is 1)."""
    import time
    t0 = time.time()
    specreg.audit()
    assert time.time() - t0 < 20.0


# --------------------------------------------------------------------------
# S001 — minted in prose, absent from the registry
# --------------------------------------------------------------------------

def test_s001_fires_when_a_prose_section_has_no_registry_entry():
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 2 (round 20): a thing\n\nbody\n")
    assert "S001" in codes(d)


def test_s001_is_silent_when_both_sites_exist():
    d = doc([(1, "One (round 10)"), (2, "Two (round 20)")],
            extra="\n### Decision 2 (round 20): a thing\n\nbody\n")
    assert "S001" not in codes(d)


def test_s001_names_the_number_the_next_round_would_reuse():
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 2 (round 20): a thing\n\nbody\n")
    f = next(x for x in specreg.audit(spec_text=d, with_citations=False)
             ["findings"] if x.code == "S001")
    assert "reuses 2" in f.message
    assert "max is 1" in f.message


def test_a_prose_only_id_still_raises_next_free():
    """The collision guard. Reading the registry alone gives 2; every site
    gives 3."""
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 2 (round 20): a thing\n\nbody\n")
    assert max(specreg.registry_ids(d)) + 1 == 2
    assert specreg.next_free(d) == 3


# --------------------------------------------------------------------------
# S002 — collisions a set-based reader cannot see
# --------------------------------------------------------------------------

def test_s002_fires_on_a_duplicated_registry_entry():
    d = doc([(1, "One (round 10)"), (1, "One again (round 11)")])
    assert "S002" in codes(d)


def test_s002_fires_on_two_prose_sections_for_one_id():
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 1 (round 10): a\n\nb\n"
                  "\n#### Decision 1 (round 10): c\n\nd\n")
    assert "S002" in codes(d)


def test_a_duplicate_is_invisible_to_a_set_based_reader():
    """Why S002 exists at all: the id set is identical with and without the
    duplicate, so membership checking cannot report it."""
    one = doc([(1, "One (round 10)")])
    two = doc([(1, "One (round 10)"), (1, "One again (round 11)")])
    assert specreg.registry_ids(one) == specreg.registry_ids(two)
    assert "S002" in codes(two) and "S002" not in codes(one)


# --------------------------------------------------------------------------
# S003 — undeclared holes
# --------------------------------------------------------------------------

def test_s003_fires_on_an_undeclared_hole():
    d = doc([(1, "One (round 10)"), (3, "Three (round 30)")])
    assert "S003" in codes(d)


def test_s003_is_silent_when_the_hole_is_declared_reserved():
    d = doc([(1, "One (round 10)"), (3, "Three (round 30)")], reserved=(2, 2))
    assert "S003" not in codes(d)


def test_s003_does_not_double_report_an_s001_id():
    """An id minted in prose only is a hole AND an S001. One fact, one
    finding — the louder one."""
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 2 (round 20): a thing\n\nbody\n")
    assert codes(d).count("S003") == 0


# --------------------------------------------------------------------------
# S004 — the tag and the heading it points at
# --------------------------------------------------------------------------

def test_s004_fires_when_the_rounds_disagree():
    d = doc([(1, "One (v0.9, round 10)")],
            extra="") .replace("## Syntax",
                               "## v0.9 (round 11, language C) — x\n\nb\n\n## Syntax")
    assert "S004" in codes(d)


def test_s004_is_silent_when_the_rounds_agree():
    d = doc([(1, "One (v0.9, round 10)")]).replace(
        "## Syntax", "## v0.9 (round 10, language C) — x\n\nb\n\n## Syntax")
    assert "S004" not in codes(d)


def test_s004_fires_when_the_tagged_label_has_no_heading():
    d = doc([(1, "One (v0.9, round 10)")])
    f = [x for x in specreg.audit(spec_text=d, with_citations=False)["findings"]
         if x.code == "S004"]
    assert f and "no `## v0.9 (…)` heading" in f[0].message


def test_s004_checks_an_untagged_label_against_its_prose_section():
    """Decisions 50, 54, 55 and 56 carry `(round N)` with no version. Their
    second site is the `Decision N` heading, not a version heading."""
    bad = doc([(1, "One (round 10)")],
              extra="\n### Decision 1 (round 99): a\n\nb\n")
    good = doc([(1, "One (round 10)")],
               extra="\n### Decision 1 (round 10): a\n\nb\n")
    assert "S004" in codes(bad)
    assert "S004" not in codes(good)


def test_a_round_named_in_an_entry_body_is_not_a_tag():
    """Round 462's rule in this file's key: one predicate, one question. Entry
    bodies quote rounds constantly; only the trailing parenthetical is a
    coordinate claim."""
    d = HEAD + ("1. **One (v0.9, round 10).** Round 338 found it and round "
                "345 wrote it up.\n") + TAIL
    d = d.replace("## Syntax",
                  "## v0.9 (round 10, language C) — x\n\nb\n\n## Syntax")
    assert "S004" not in codes(d)
    assert specreg.parse_registry(d)[0]["tag_round"] == 10


# --------------------------------------------------------------------------
# S005 / S006
# --------------------------------------------------------------------------

def test_s005_fires_above_the_floor_and_not_below():
    below = doc([(1, "One.")])
    above = doc([(specreg.TAG_FLOOR, "Untagged.")])
    assert "S005" not in codes(below)
    assert "S005" in codes(above)


def test_s005_floor_is_a_floor_not_an_allowlist():
    """A new untagged entry must be reported without anyone editing this
    module."""
    d = doc([(specreg.TAG_FLOOR + 99, "Untagged.")])
    assert "S005" in codes(d)


def test_s006_is_a_warning_and_never_an_error():
    res = specreg.audit()
    assert all(f.severity == "WARN"
               for f in res["findings"] if f.code == "S006")


def test_s006_counts_a_cross_reference_from_another_entry_as_a_reader():
    """Entry 42's title names decision 41's table. That is a pointer, not a
    self-mention, and the id it points at is not an orphan."""
    cites = specreg.citations()
    assert cites.get(41), "decision 41 should be cited from elsewhere"
    assert any(rel == specreg.SPEC_REL for rel, _ in cites[41])


# --------------------------------------------------------------------------
# parsing details the findings rest on
# --------------------------------------------------------------------------

@pytest.mark.parametrize("title,label,rnd", [
    ("A type miss names the FIELD (v0.20, round 348).", "v0.20", 348),
    ("A bound has to name the population (round 456).", None, 456),
    ("Recover host state (v0.12/v0.13 guest parity, round 338).",
     "v0.12/v0.13 guest parity", 338),
    ("Histories can be diffed (v0.3).", "v0.3", None),
    ("Tests are statements.", None, None),
])
def test_parse_tag_on_every_form_the_corpus_uses(title, label, rnd):
    assert specreg._parse_tag(title) == (label, rnd)


def test_an_unclosed_bold_does_not_crash_the_audit():
    """A checker that raises on a malformed corpus stops being run."""
    d = HEAD + "1. **One (round 10) and the bold never closes\n" + TAIL
    assert specreg._bold_title("1. **One (round 10) and no close\n") == ""
    codes(d)  # must not raise


def test_the_registry_section_ends_at_the_next_h2():
    d = doc([(1, "One (round 10)")],
            extra="\n### Decision 9 (round 90): after the section\n")
    lo, hi = specreg.registry_span(d)
    assert "## Syntax" not in d[lo:hi]
    assert "Decision 9" not in d[lo:hi]
    assert 9 in {s["id"] for s in specreg.parse_sections(d)}


def test_a_decision_heading_inside_the_registry_is_not_a_second_site():
    """`See § Decision 55.` inside an entry body must not read as a prose
    section, or every entry that points at its own section is an S002."""
    d = HEAD + "1. **One (round 10).** See § Decision 1.\n" + TAIL
    assert specreg.parse_sections(d) == []
    assert "S002" not in codes(d)


def test_version_headings_take_the_first_round_named():
    d = doc([(1, "One (v0.9, round 10)")]).replace(
        "## Syntax",
        "## v0.9 (round 10, landed by round 11; specified round 12) — x\n\n"
        "b\n\n## Syntax")
    assert specreg.parse_versions(d)["v0.9"]["round"] == 10
    assert "S004" not in codes(d)


def test_main_audit_exit_code_is_driven_by_errors_only(tmp_path, capsys):
    """Round 363's rule: warnings never set the exit code."""
    p = tmp_path / "S.md"
    p.write_text(doc([(1, "One (round 10)"), (specreg.TAG_FLOOR, "Untagged.")],
                     reserved=(2, specreg.TAG_FLOOR - 1)),
                 encoding="utf-8")
    rc = specreg.main(["audit", "--spec", str(p)])
    out = capsys.readouterr().out
    assert "S005" in out and "1 warning(s)" in out
    assert rc == 0

    p.write_text(doc([(1, "One (round 10)"), (3, "Three (round 30)")]),
                 encoding="utf-8")  # 2 is a hole nobody declared
    assert specreg.main(["audit", "--spec", str(p)]) == 1


def test_next_subcommand_prints_a_number(capsys):
    assert specreg.main(["next"]) == 0
    assert int(capsys.readouterr().out.strip()) == specreg.next_free()


def test_json_output_round_trips(tmp_path):
    import json
    out = tmp_path / "r.json"
    specreg.main(["audit", "--json", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["next"] == specreg.next_free()
    assert len(d["entries"]) == len(specreg.registry_ids())
    # ROUND 486: was `^S00\d$`, which S010 does not match. The regex was a
    # claim about how many families exist, written where it looks like a claim
    # about their shape -- green until the tenth one lands, then red for a
    # correct reason nobody would guess from the assertion.
    assert all(re.match(r"^S0\d\d$", f["code"]) for f in d["findings"])


# ==========================================================================
# ROUND 486 — the SECOND registry
#
# Everything above this line is about decision ids. SPEC.md mints a second
# ordinal sequence, `## v0.N (round R, …)`, and round 464 built density
# checking for one of the two. These are the four families that ask S001's,
# S003's, S004's and `test_v22`'s questions of the other one.
#
# Same discipline as the block above: every family fires on a synthetic
# document built to trigger it AND stays silent on the near-miss beside it.
# The live-corpus assertions are few and specific.
# ==========================================================================

VHEAD = ("# Spec\n\n*Spec level: **%s** (round 1).*\n\nintro\n\n"
         "## Anti-mainstream design decisions\n")

# A sub-version this document does not define, ASSEMBLED rather than written.
# ROUND 486: the literal form of this string, in this file, is a live `S007`
# against the live SPEC.md -- `tests/test_specreg.py` is inside X001's scope
# and a fixture is not exempt from being read. Writing it as a fixture was the
# fourth time in one round that a file explaining the hazard tripped over it;
# `test_this_module_cites_no_unsectioned_version` covers this file for that
# reason. `VERSION_CITE_RE` needs digits on both sides of the dot, so the
# concatenation below matches nothing.
UNSECTIONED_SUBV = "v0." + "7." + "3"


def vdoc(sections, entries=(), header=None, extra=""):
    """A SPEC-shaped document whose VERSION headings are the subject.

    `sections` is [(label, round)]; the header defaults to the last one, so a
    doc is S010-clean unless a test deliberately makes it otherwise.
    """
    body = "".join("%d. **%s** body.\n" % (n, t) for n, t in entries)
    vs = "".join("\n## %s (round %d) — a level\n\nbody\n" % (l, r)
                 for l, r in sections)
    top = header or (sections[-1][0] if sections else "v0.6")
    return VHEAD % top + body + "\n## Syntax\n\nafter\n" + vs + extra


def vrepo(tmp_path, spec_text, files=None):
    """A minimal repo root: `<root>/languages/whence/{SPEC.md, …}`.

    `audit(repo=…)` needs a real tree because S007 is the one family whose
    input comes from OUTSIDE the document — which is the whole point of
    decision 61, so the tests have to supply an outside.
    """
    root = tmp_path / "repo"
    d = root / "languages" / "whence"
    d.mkdir(parents=True)
    (d / "SPEC.md").write_text(spec_text, encoding="utf-8")
    for name, body in (files or {}).items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return str(root)


def vcodes(tmp_path, spec_text, files=None):
    root = vrepo(tmp_path, spec_text, files)
    res = specreg.audit(repo=root, spec_text=spec_text, with_citations=True)
    return sorted(f.code for f in res["findings"])


# --------------------------------------------------------------------------
# S007 — a version claimed in the code with no section
# --------------------------------------------------------------------------

def test_s007_fires_on_a_version_claimed_with_no_section(tmp_path):
    """The live defect, in miniature: the code mints v0.7, the document
    stops at v0.6."""
    t = vdoc([("v0.6", 20)])
    assert "S007" in vcodes(tmp_path, t,
                            {"m.py": "# v0.7 (round 30) did a thing\n"})


def test_s007_is_silent_when_the_section_exists(tmp_path):
    t = vdoc([("v0.6", 20), ("v0.7", 30)])
    assert "S007" not in vcodes(tmp_path, t,
                                {"m.py": "# v0.7 (round 30) did a thing\n"})


def test_s007_ignores_a_version_below_the_floor(tmp_path):
    """v0.1-v0.5 predate the `## vN` convention and are documented under
    prose-titled headings. A FLOOR, not an allowlist — so the exemption
    expires automatically for everything above it, which the test above
    shows by firing on v0.7."""
    t = vdoc([("v0.6", 20)])
    assert "S007" not in vcodes(tmp_path, t, {"m.py": "see v0.3 and v0.4.1\n"})


def test_s007_ignores_a_foreign_namespace(tmp_path):
    """`VERSION_CITE_RE` over prose is a `vN.N` detector, not a Whence-version
    detector. X001's scope includes all of `knowledge/`, where a NUC round
    names a server v1.7.0 and a skills round names a schema v4.2."""
    t = vdoc([("v0.6", 20)])
    assert "S007" not in vcodes(
        tmp_path, t, {"m.py": "server v1.7.0, schema v4.2, semver v2.0.0\n"})


def test_s007_counts_every_claim_site_not_just_the_first(tmp_path):
    """The message carries the count because the count is what makes the
    finding actionable: 28 places is a repair, 1 is a typo."""
    t = vdoc([("v0.6", 20)])
    root = vrepo(tmp_path, t, {"a.py": "v0.9\n", "b.py": "v0.9\nv0.9\n"})
    res = specreg.audit(repo=root, spec_text=t, with_citations=True)
    f = next(x for x in res["findings"] if x.code == "S007")
    assert "3 place(s)" in f.message
    assert res["version_citations"]["v0.9"] == 3


# --------------------------------------------------------------------------
# S008 — a hole in the minor sequence
# --------------------------------------------------------------------------

def test_s008_fires_on_a_hole_in_the_minor_sequence(tmp_path):
    t = vdoc([("v0.6", 20), ("v0.8", 30)])
    assert "S008" in vcodes(tmp_path, t)


def test_s008_is_silent_on_a_dense_range(tmp_path):
    t = vdoc([("v0.6", 20), ("v0.7", 25), ("v0.8", 30)])
    assert "S008" not in vcodes(tmp_path, t)


def test_s008_does_not_demand_a_dense_sub_version_dimension(tmp_path):
    """v0.14 has fourteen patch levels and v0.15 has none. Asking the third
    component to be dense would invent a hole under every level that never
    needed a patch release."""
    t = vdoc([("v0.6", 20), ("v0.7", 25), (UNSECTIONED_SUBV, 26),
              ("v0.8", 30)])
    assert "S008" not in vcodes(tmp_path, t)


def test_s008_terminates_when_a_foreign_major_is_in_scope(tmp_path):
    """REGRESSION, and it is the reason S008 iterates an explicit `range()`.

    The first draft took `hi = max(known)` over `(major, minor)` tuples and
    walked `n = (n[0], n[1] + 1)` while `n <= hi`. With a `v9.9` anywhere in
    scope `hi` is `(9, 9)`, and `(0, N)` never reaches it for any N, because
    a minor cannot overtake a major. It did not raise — it appended a finding
    per iteration until it was killed.
    """
    t = vdoc([("v0.6", 20), ("v0.7", 25)])
    root = vrepo(tmp_path, t, {"m.py": "another project's v9.9 release\n"})
    res = specreg.audit(repo=root, spec_text=t, with_citations=True)
    assert [f.code for f in res["findings"] if f.code == "S008"] == []
    assert len(res["findings"]) < 50


# --------------------------------------------------------------------------
# S009 — the tag that could point at a version and does not
# --------------------------------------------------------------------------

def test_s009_fires_on_an_unlabelled_tag_whose_round_has_a_version_section():
    """S004 has two branches and only the LABELLED one reaches a version
    heading. Entries 54-60 of the live document all took the other branch,
    which is why S004 could not see three levels go missing."""
    t = vdoc([("v0.6", 20)], entries=[(1, "A decision (round 20).")])
    assert "S009" in codes(t)


def test_s009_is_silent_when_no_version_section_names_that_round():
    """Decisions 54-57's shape: minted at a level somebody else bumped, so
    `(round N)` with no label is CORRECT and must not be nagged."""
    t = vdoc([("v0.6", 20)], entries=[(1, "A decision (round 21).")])
    assert "S009" not in codes(t)


def test_s009_is_silent_when_the_entry_already_carries_the_label():
    t = vdoc([("v0.6", 20)], entries=[(1, "A decision (v0.6, round 20).")])
    assert "S009" not in codes(t)


def test_s009_is_a_warning_and_never_an_error():
    t = vdoc([("v0.6", 20)], entries=[(1, "A decision (round 20).")])
    res = specreg.audit(spec_text=t, with_citations=False)
    assert all(f.severity == "WARN"
               for f in res["findings"] if f.code == "S009")


# --------------------------------------------------------------------------
# S010 — the header, and the second writing of test_v22's assertion
# --------------------------------------------------------------------------

def test_s010_fires_when_the_header_is_not_the_highest_section():
    t = vdoc([("v0.6", 20), ("v0.7", 30)], header="v0.6")
    assert "S010" in codes(t)


def test_s010_is_silent_when_the_header_is_the_highest_section():
    t = vdoc([("v0.6", 20), ("v0.7", 30)])
    assert "S010" not in codes(t)


def test_s010_orders_numerically_and_not_as_a_string():
    """v0.9 sorts above v0.44 as a string. `test_v22`'s own `_ver` helper
    carries a comment saying so; this is the same claim about `vkey`."""
    t = vdoc([("v0.9", 20), ("v0.44", 30)], header="v0.44")
    assert "S010" not in codes(t)
    assert "S010" in codes(vdoc([("v0.9", 20), ("v0.44", 30)], header="v0.9"))


def test_s010_and_test_v22_agree_about_the_live_spec():
    """Two writings of one assertion. Round 464's convention for the two
    registry parsers, applied to the two header checks: they may not share
    the regex, and they may not disagree."""
    text = specreg.read_spec()
    sections = re.findall(r"^## v(\d+\.\d+)", text, re.M)
    v22_highest = "v" + max(sections,
                            key=lambda v: tuple(int(p) for p in v.split(".")))
    vsecs = specreg.version_sections(text)
    assert max(vsecs, key=specreg.vkey) == v22_highest
    res = specreg.audit(with_citations=False)
    assert [f.code for f in res["findings"] if f.code == "S010"] == []


# --------------------------------------------------------------------------
# the two spellings of one level
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("v0.44.0", "v0.44"),
    ("v0.19.0", "v0.19"),
    ("v0.14", "v0.14"),
    ("v0.14.1", "v0.14.1"),
    ("v0.17.1", "v0.17.1"),
    ("v1.7.0", "v1.7"),
])
def test_normalise_collapses_only_a_trailing_zero(raw, want):
    assert specreg._normalise(raw) == want


def test_no_version_section_ends_in_a_zero_patch():
    """`_normalise`'s PRECONDITION, asserted rather than trusted.

    Collapsing `v0.44.0` -> `v0.44` is safe only because a third component in
    this document always means a real patch release and none of them is `.0`.
    The day somebody mints a section whose label ends in a zero patch, the
    normalisation starts merging two distinct levels and this goes red first.
    """
    bad = [l for l in specreg.version_sections(specreg.read_spec())
           if re.fullmatch(r"v\d+\.\d+\.0", l)]
    assert bad == [], "normalisation would merge these with their parent: %s" % bad


def test_the_changelog_spelling_is_counted_against_the_spec_spelling():
    """`CHANGELOG.md` writes `## [v0.44.0]`; SPEC.md writes `## v0.44`. One
    level. Not a claim about `CHANGELOG.md`'s authorship — it is a tracked
    file this program does not own — only that the two spellings meet."""
    res = specreg.audit()
    assert "v0.44.0" not in res["version_citations"]
    assert res["version_citations"].get("v0.44", 0) > 0


# --------------------------------------------------------------------------
# scope, and this module's own citations
# --------------------------------------------------------------------------

def test_the_citation_scope_excludes_a_vendored_tree(tmp_path):
    """ROUND 486. `languages/whence/.venv/` exists, it is a dotfile, and
    `_in_scope_files` walked it for 22 rounds: 1452 files yielded, 984 of
    them (67.8 %) third-party. Inert for S001-S006 by luck; not inert for
    S007, where three vendored files name versions."""
    root = vrepo(tmp_path, vdoc([("v0.6", 20)]),
                 {".venv/lib/site-packages/x.py": "v0.9\n",
                  "research-env/y.py": "v0.9\n",
                  "real.py": "v0.9\n"})
    files = list(specreg._in_scope_files(root))
    assert not [f for f in files if ".venv" in f or "research-env" in f]
    assert "languages/whence/real.py" in files


def test_this_module_cites_no_unsectioned_version():
    """The mirror of `test_this_module_cites_no_unminted_decision`, which has
    guarded the DECISION dimension since round 464 and was never generalised.

    `specreg.py` AND this file are inside X001's scope, so a version written
    in either as an example is a live S007. Round 486 tripped this four times — in the
    `SKIP_DIRS` comment about false citations, in `_normalise`'s docstring,
    and in the sentence about `_normalise`'s precondition — each time in the
    paragraph explaining the hazard. Write such a level without its `v`.
    """
    text = specreg.read_spec()
    have = set(specreg.version_sections(text))
    cited = set()
    for rel in ("specreg.py", os.path.join("tests", "test_specreg.py")):
        src = open(os.path.join(specreg.HERE, rel), encoding="utf-8").read()
        cited |= {specreg._normalise("v" + m.group(1))
                  for m in specreg.VERSION_CITE_RE.finditer(src)}
    k = specreg.vkey
    live = {l for l in cited
            if k(l) and k(l)[0] == specreg.VERSION_FLOOR[0]
            and k(l) >= specreg.VERSION_FLOOR}
    assert live <= have, "unsectioned versions cited: %s" % sorted(live - have)


# --------------------------------------------------------------------------
# the live corpus
# --------------------------------------------------------------------------

def test_the_live_spec_version_registry_has_no_errors():
    """The repair round 486 landed. Green means: every version the tree
    claims has a section, the minor range is dense, and the header is the
    top of it."""
    res = specreg.audit()
    errs = [str(f) for f in res["findings"]
            if f.severity == "ERROR" and f.code in ("S007", "S008", "S010")]
    assert errs == [], "\n".join(errs)


def test_the_three_retrofitted_levels_exist_and_parent_their_decisions():
    """Rounds 476, 480 and 482 minted v0.45/v0.46/v0.47 in code and wrote no
    section; decisions 58, 59 and 60 were `###` children of `## v0.44`, a
    level minted by round 452. This pins the reparenting, not the prose."""
    text = specreg.read_spec()
    vsecs = specreg.version_sections(text)
    for label, rnd, dec in (("v0.45", 476, 58), ("v0.46", 480, 59),
                            ("v0.47", 482, 60)):
        assert label in vsecs, "%s has no `## %s` section" % (label, label)
        assert vsecs[label]["round"] == rnd
        sec = next(s for s in specreg.parse_sections(text) if s["id"] == dec)
        assert sec["line"] > vsecs[label]["line"], (
            "decision %d is not under `## %s`" % (dec, label))
        nearer = [v for v in vsecs.values()
                  if vsecs[label]["line"] < v["line"] < sec["line"]]
        assert not nearer, "a later `## vN` sits between them"


def test_decisions_54_to_57_stay_under_v0_44():
    """The other half of the same claim, and the reason the repair is honest
    rather than cosmetic. Rounds 456-468 minted decisions and claimed no
    version anywhere in the tree, so they were decided AT v0.44 and belong
    there. Only the three whose rounds claimed a number moved."""
    text = specreg.read_spec()
    v44 = specreg.version_sections(text)["v0.44"]["line"]
    v45 = specreg.version_sections(text)["v0.45"]["line"]
    for dec in (54, 55, 56, 57):
        sec = next(s for s in specreg.parse_sections(text) if s["id"] == dec)
        assert v44 < sec["line"] < v45, "decision %d moved" % dec


def test_decision_61_is_minted_at_both_sites():
    """Round 462's failure was minting in prose only. The registry's own
    instruction says to append in the SAME round.

    ROUND 488: the third assertion used to read `next_free(text) == 62`,
    which is a claim about the TOP of the range and not about decision 61
    at all -- so minting decision 62 (in both sites, correctly) turned this
    test red and named the wrong subject. It is now derived: whatever the
    highest minted id is, `next_free` is one past it. The test that catches
    a prose-only mint is the pair of `in` assertions above, and those are
    what this test is named for."""
    text = specreg.read_spec()
    assert 61 in specreg.registry_ids(text)
    assert 61 in {s["id"] for s in specreg.parse_sections(text)}
    assert specreg.next_free(text) == max(specreg.registry_ids(text)) + 1


def test_decision_62_is_minted_at_both_sites():
    """v0.48, round 488. Same shape as decision 61's: the registry entry
    and the `See § Decision 62` prose section land in the same round."""
    text = specreg.read_spec()
    assert 62 in specreg.registry_ids(text)
    assert 62 in {s["id"] for s in specreg.parse_sections(text)}
