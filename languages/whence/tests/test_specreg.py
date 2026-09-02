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
    assert all(re.match(r"^S00\d$", f["code"]) for f in d["findings"])
