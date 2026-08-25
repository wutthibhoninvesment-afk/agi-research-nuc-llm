"""Round 113: static survivor triage."""
from swe import triage as TR
from swe.mutation import generate

MOD = '''\
class Interp(object):
    HOST_RESERVE = 250
    FAST_MAX_DEPTH = 100

    def __init__(self):
        self.fast_hits = 0
        self.peak_depth = 0
        self._hleft = -1
        self.depth = 0

    def call(self, f, body):
        if f is None:
            f = self.compile(body)
            self.fast_hits += 1
        cost = body.cdepth + 1
        if self._hleft >= cost:
            self._hleft -= cost
        if self.depth > self.peak_depth:
            self.peak_depth = self.depth
        if len(body.args) != 2:
            return "%s expects %d args" % (f, 2)
        return f(body) + 1

    def compile(self, body):
        return lambda b: b.cdepth
'''


def _survivor_dicts():
    return [dict(m.as_dict(), status="survived") for m in generate(MOD, "mod.py")]


def test_sites_classify_by_enclosing_names_and_shapes():
    sites = TR.sites(MOD)
    by_text = {}
    for s in sites.values():
        by_text.setdefault((s.op, s.text), s)
    assert by_text[("const", "HOST_RESERVE = 250")].kind == "budget"
    assert by_text[("const", "FAST_MAX_DEPTH = 100")].kind == "budget"
    assert by_text[("const", "self.fast_hits += 1")].kind == "counter"
    assert by_text[("const", "self.peak_depth = 0")].kind == "counter"
    assert by_text[("cmp", "self.depth > self.peak_depth")].kind == "counter"
    assert by_text[("ifneg", "self.depth > self.peak_depth")].kind == "counter"
    assert by_text[("const", "cost = body.cdepth + 1")].kind == "budget"
    assert by_text[("arith", "cost = body.cdepth + 1")].kind == "budget"
    assert by_text[("cmp", "self._hleft >= cost")].kind == "budget"
    assert by_text[("ifneg", "f is None")].kind == "none_guard"
    assert by_text[("cmp", "f is None")].kind == "none_guard"
    assert by_text[("arith", "return '%s expects %d args' % (f, 2)")].kind == "error_message"
    assert by_text[("cmp", "len(body.args) != 2")].kind == "other"
    assert by_text[("arith", "return f(body) + 1")].kind == "other"
    # the compound statement's head, never its body, is the text
    assert all("\n" not in s.text for s in sites.values())
    assert by_text[("ifneg", "f is None")].enclosing == "Interp.call"


def test_triage_scores_all_and_behavioural_sets():
    ds = _survivor_dicts()
    # kill everything in `other`/`none_guard`/`error_message` except one, keep counters/budget alive
    sites = TR.sites(MOD)
    killed_other = 0
    for d in ds:
        k = sites[TR.site_index(d["id"])].kind
        if k not in TR.NON_BEHAVIOURAL and killed_other < 6:
            d["status"] = "killed"
            killed_other += 1
    t = TR.triage(ds, {"mod.py": MOD})
    assert sum(t["counts"].values()) == sum(1 for d in ds if d["status"] == "survived")
    assert t["counts"]["counter"] >= 4 and t["counts"]["budget"] >= 5
    assert t["behavioural_killed"] == 6
    assert t["score_behavioural"] > t["score_all"]
    assert t["non_behavioural_survivors"] == t["counts"]["counter"] + t["counts"]["budget"]
    assert all(r["class"] in TR.CLASSES for r in t["survivors"])
    assert "behavioural" in TR.render(t)


def test_cli_triages_a_mutation_json(tmp_path, capsys):
    import json
    root = tmp_path / "proj"
    root.mkdir()
    (root / "mod.py").write_text(MOD)
    mj = tmp_path / "m.json"
    mj.write_text(json.dumps({"mutants": _survivor_dicts()}))
    out = tmp_path / "t.json"
    assert TR.main([str(mj), "--root", str(root), "--json", str(out), "--show"]) == 0
    text = capsys.readouterr().out
    assert "triage:" in text and "counter" in text and "budget" in text
    assert json.loads(out.read_text())["counts"]["none_guard"] >= 2
