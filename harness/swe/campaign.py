"""Resumable, checkpointed SWE campaign: mutate -> recheck -> corpus-kill ->
verify -> model-kill -> review -> report (round 29).

Rounds 17 and 23 both drove this pipeline by hand and died mid-way leaving
nothing measurable: a mutation log with no score, an empty review output,
unscored predictions. The fix is structural, not behavioural — every stage
writes its artifact to `out/` and records itself in `out/campaign.json`;
re-running the same command skips finished stages and resumes unfinished
ones at the finest granularity that has a checkpoint (per mutant for
mutation and model kills). A round that dies leaves a manifest that says
exactly where, and the next run picks up from there.

Stages and artifacts (all under --out):
  mutation   mutation.json (+ mutation.partial.jsonl per-mutant checkpoint)
             or --adopt-mutation PATH to take an existing report.
  recheck    mutation-rechecked.json — every `timeout` from the parallel run
             re-run SERIALLY with a longer budget on the now-idle machine;
             flips (timeout -> killed | survived) are recorded, because a
             timeout under 5-worker load is not evidence of an infinite loop.
  corpus     killers.json + <root>/<test_file_corpus>: differential search over
             examples + generated programs (+ --extra-programs) for every
             survivor; kills are shrunk and pinned as tests.
  verify     verify-corpus.json — each pinned mutant re-run against ONLY the
             pinned test file (a pin that kills there kills in the suite).
  live_kill  live-kill.json (+ live-kill.partial.jsonl): the model attempts a
             sample of `no_killer` survivors (swe.review.kill_task); kills are
             pinned to <test_file_model> and verified the same way.
  review     review.json: oracle-gated model review with the region tools.
  coverage   coverage.json (round 101): settrace line coverage of the mutated
             files under the suite; every survivor is triaged as
             `uncovered` (the suite never runs the line: a test gap) or
             `covered` (weak assertion or equivalent). Killed-on-uncovered
             is the instrument's self-check.
  repair     repair.json (+ repair.partial.jsonl, round 101): killed mutants
             injected as bugs; the model repairs from the failing-test
             signal; scored green / localized / exact (swe.repair).
  report     report.json + report.md: the metrics, including a projected
             final score = (baseline kills + verified new pins) / total.
"""

import json
import os
import random
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import coverage as CV
from . import killers as K
from . import oraclekill as OK
from . import triage as TR
from . import repair as RP
from . import prioritize as PR
from . import review as R
from .fuzz import WHENCE_ROOT
from .mutation import (DEFAULT_TEST_CMD, Mutant, MutationReport, _copy_project,
                       generate, run_mutant)

STAGES = ("mutation", "recheck", "coverage", "corpus", "verify", "triage", "oracle_kill",
          "live_kill", "review", "repair", "report")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append_jsonl(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def pinned_test_cmd(test_file):
    return [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test_file]


class Campaign(object):
    def __init__(self, out, root=WHENCE_ROOT, files=("whence/interp.py",),
                 test_cmd=DEFAULT_TEST_CMD, log=None, prioritizer=None, coverage_map=None):
        self.prioritizer = prioritizer     # swe.prioritize.Prioritizer / MapPrioritizer or None
        self.coverage_map = coverage_map   # by-file coverage dict (round 113) or None
        self.out = os.path.abspath(out)
        os.makedirs(self.out, exist_ok=True)
        self.root = os.path.realpath(root)
        self.files = tuple(files)
        # stage_coverage's "derive the % + triage from the reused by-file
        # map, no second run" shortcut is the SAME staleness hazard
        # MapPrioritizer guards against (a line-keyed map from an earlier
        # commit answers for whatever code used to be at line N) — computed
        # once here so both consumers of self.coverage_map agree.
        self.coverage_map_stale = (CV.stale_files(coverage_map, self.root)
                                   if coverage_map is not None else [])
        self.test_cmd = list(test_cmd)
        self.log = log or (lambda s: print(s, flush=True))
        self.manifest_path = self.path("campaign.json")
        self.manifest = _load_json(self.manifest_path) or {
            "created": _now(), "root": self.root, "files": list(self.files), "stages": {}}
        _dump_json(self.manifest_path, self.manifest)

    # ------------------------------------------------------------ manifest --
    def path(self, name):
        return os.path.join(self.out, name)

    def _sync(self):
        """Re-read the manifest from disk so two processes driving different
        stages of the same campaign (e.g. a live review while the mutation
        baseline is still running) never clobber each other's marks: every
        write is read-modify-write of the stage being touched only."""
        disk = _load_json(self.manifest_path)
        if disk:
            self.manifest["stages"] = disk.get("stages", {})
        return self.manifest

    def done(self, stage):
        return self._sync()["stages"].get(stage, {}).get("status") == "done"

    def _mark(self, stage, status, **info):
        self._sync()
        st = self.manifest["stages"].setdefault(stage, {})
        st["status"] = status
        if status == "running":
            st["started"] = _now()
        else:
            st["finished"] = _now()
        if info:
            st.setdefault("info", {}).update(info)
        _dump_json(self.manifest_path, self.manifest)

    def force(self, stages):
        self._sync()
        for s in stages:
            self.manifest["stages"].pop(s, None)
        _dump_json(self.manifest_path, self.manifest)

    # ------------------------------------------------------------ helpers --
    def _snapshot_dir(self):
        return self.path("snapshot")

    def _snapshot_files(self):
        """Freeze `self.files`' CURRENT on-disk content once, idempotently,
        so every later stage that reconstructs Mutant objects from
        mutation.json's ids (recheck/corpus/verify/triage/oracle_kill)
        regenerates the SAME source `stage_mutation` assigned those ids
        against — even if a concurrent session edits the real file while
        this campaign runs for the next hour. Round 125: a concurrent
        language-track edit to interp.py landed mid-campaign and every
        `_mutants_by_id` lookup for the rest of that run silently matched
        NOTHING (rebuild_mutants regenerates ids from the live file, which
        had changed shape) — corpus/oracle_kill reported 0 attempted in 0.0s
        and the recheck stage's "exhaustive" subset verification finished in
        13s instead of the expected tens of minutes, both mis-read as "ran
        clean" because a skipped `continue` looks identical to a genuine
        negative result. See knowledge/round-131."""
        snap = self._snapshot_dir()
        for rel in self.files:
            dst = os.path.join(snap, rel)
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(self.root, rel), dst)

    def _original_project_dir(self):
        """A full project copy (tests, other modules: LIVE) with `self.files`
        pinned to the snapshot — built once per campaign, reused by every
        stage that imports the true 'original' (unmutated) package to diff
        mutant behaviour against. Without the pin, a mutant (built from the
        snapshot) and a live-loaded 'original' can differ by unrelated tree
        drift instead of by the mutation alone, producing false killers."""
        self._snapshot_files()
        dst = self.path("orig-proj")
        if not os.path.isdir(dst):
            tmp = dst + ".tmp"
            if os.path.isdir(tmp):
                shutil.rmtree(tmp)
            _copy_project(self.root, tmp)
            for rel in self.files:
                shutil.copyfile(os.path.join(self._snapshot_dir(), rel), os.path.join(tmp, rel))
            os.replace(tmp, dst)
        return dst

    def _mutants_by_id(self, dicts):
        self._snapshot_files()
        ms = K.rebuild_mutants(self._snapshot_dir(), dicts)
        return dict((m.id, m) for m in ms)

    def _run_mutants(self, mutants, workers, timeout_s, partial_path):
        """Run mutants against the suite with a per-mutant checkpoint."""
        done = dict((d["id"], d) for d in _read_jsonl(partial_path))
        todo = [m for m in mutants if m.id not in done]
        if done:
            self.log("resuming: %d of %d mutants already checkpointed" % (len(done), len(mutants)))
        pr = self.prioritizer

        def one(m):
            cmd = pr.cmd_for(m, self.test_cmd) if pr else self.test_cmd
            run_mutant(m, self.root, cmd, timeout_s)
            return m

        with ThreadPoolExecutor(max_workers=workers) as ex:
            for m in ex.map(one, todo):
                d = m.as_dict()
                if pr:
                    order = pr.order_for(m.path, m.lineno, m.op)
                    d["first_file"] = order[0] if order else None
                    if hasattr(pr, "basis_for"):
                        d.update(pr.basis_for(m))
                d["killed_by"] = PR.killed_by(m.detail) if m.status == "killed" else None
                _append_jsonl(partial_path, d)
                done[m.id] = d
                self.log("%-8s %s %.1fs" % (m.status, m.id, m.seconds or 0))
        for m in mutants:
            d = done[m.id]
            m.status, m.seconds, m.detail = d["status"], d.get("seconds"), d.get("detail", "")
        return mutants

    # ------------------------------------------------------------- stages --
    def stage_mutation(self, workers=4, timeout_s=240.0, limit=None, adopt=None, ops=None):
        art = self.path("mutation.json")
        if self.done("mutation"):
            return _load_json(art)
        self._mark("mutation", "running")
        if adopt:
            shutil.copyfile(adopt, art)
            data = _load_json(art)
            # best-effort: the adopted report's ids describe whatever the OTHER
            # campaign's tree looked like, which this snapshot cannot recover;
            # freezing now at least stops this campaign's own later stages from
            # drifting further out from under it.
            self._snapshot_files()
            self._mark("mutation", "done", adopted_from=os.path.abspath(adopt),
                       total=data["total"], killed=data["killed"], survived=data["survived"],
                       score=data["score"])
            return data
        mutants = []
        for rel in self.files:
            with open(os.path.join(self.root, rel), encoding="utf-8") as f:
                src = f.read()
            mutants.extend(generate(src, rel, ops=ops))
            # freeze the exact text mutant ids were just derived from, BEFORE
            # the (possibly hours-long) mutation run gives a concurrent editor
            # a chance to change it out from under every later stage.
            dst = os.path.join(self._snapshot_dir(), rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(src)
        if limit:
            mutants = mutants[:limit]
        t0 = time.time()
        done = dict((d["id"], d) for d in _read_jsonl(self.path("mutation.partial.jsonl")))  # noqa: F841 (refreshed below)
        self._run_mutants(mutants, workers, timeout_s, self.path("mutation.partial.jsonl"))
        done = dict((d["id"], d) for d in _read_jsonl(self.path("mutation.partial.jsonl")))
        rep = MutationReport(mutants, time.time() - t0)
        data = rep.as_dict()
        # carry the per-mutant ordering/basis fields into the report (round 113:
        # the recheck's subset self-check and the map-fidelity check read them)
        for d in data["mutants"]:
            src = done.get(d["id"]) if done else None
            if src:
                for k in ("first_file", "killed_by", "basis", "files_run"):
                    if k in src:
                        d[k] = src[k]
        data["test_cmd"] = self.test_cmd
        data["workers"] = workers
        data["timeout_s"] = timeout_s
        _dump_json(art, data)
        self._mark("mutation", "done", total=data["total"], killed=data["killed"],
                   survived=data["survived"], score=data["score"], seconds=data["seconds"])
        return data

    def stage_recheck(self, timeout_s=600.0, subset_check=200, seed=0):
        """Timeouts re-run serially with a longer budget; and (round 113,
        widened round 125) EVERY subset-basis survivor is re-run under the
        FULL suite — the instrument self-check of covering-subset verdicts.
        `subset_check` is a CAP, not a sample size: with <= subset_check
        subset-basis survivors every one of them is verified; only a set
        LARGER than the cap falls back to a seeded sample, and whatever is
        left unchecked is marked `subset_unverified` (never silently
        reported as a plain `survived`).

        Round 113 sampled 20 of 32 subset-basis survivors and found
        20/20 flipped to killed — not 1 or 2 as predicted. The cause (round
        125 forensics) is structural, not a fluke: `whence/interp.py`
        builds its builtin table as a process-wide lazy singleton (each
        `@register(name, arity)` line executes exactly ONCE per pytest
        process, whichever test happens to construct the first
        `Interpreter`), so the by-file coverage map attributes a mutation
        there to one arbitrary file while its effect is visible to every
        later test in the process; separately, `tests/test_examples.py`
        runs every example through `run.py` as a SUBPROCESS, invisible to
        the in-process `sys.settrace` map entirely. Both mean a mutant's
        true covering set can be strictly larger than what the map shows,
        so `subset=True` must never trust an unverified `survived` verdict.
        The remaining 12 of round 113's 32 were never checked at all (the
        old sample cap of 20) — this method no longer leaves that gap."""
        art = self.path("mutation-rechecked.json")
        if self.done("recheck"):
            return _load_json(art)
        self._mark("recheck", "running")
        data = _load_json(self.path("mutation.json"))
        sub_flips, sub_sample = [], []
        subset_survivors = [d for d in data["mutants"]
                            if d["status"] == "survived" and d.get("basis") == "subset"]
        unverified = 0
        if subset_survivors and subset_check:
            if len(subset_survivors) <= subset_check:
                sub_sample = sorted(subset_survivors, key=lambda d: d["id"])
            else:
                rng = random.Random(seed)
                sub_sample = sorted(rng.sample(subset_survivors, subset_check),
                                    key=lambda d: d["id"])
                checked_ids = set(d["id"] for d in sub_sample)
                unverified = len(subset_survivors) - len(sub_sample)
                for d in subset_survivors:
                    if d["id"] not in checked_ids:
                        d["subset_unverified"] = True
            by_id = self._mutants_by_id(sub_sample)
            for d in sub_sample:
                m = by_id.get(d["id"])
                if m is None:
                    continue
                run_mutant(m, self.root, self.test_cmd, timeout_s)
                self.log("subset-check %-8s %s (%d files -> full) %.0fs"
                         % (m.status, m.id, d.get("files_run", 0), m.seconds or 0))
                if m.status != "survived":
                    rec = {"id": m.id, "files_run": d.get("files_run"), "after": m.status,
                           "killed_by": PR.killed_by(m.detail), "detail": (m.detail or "")[-200:]}
                    sub_flips.append(rec)
                    d["status"] = m.status
                    d["subset_check"] = rec
                    d["detail"] = m.detail
                    d["basis"] = "full"
                else:
                    d["subset_check"] = {"id": m.id, "files_run": d.get("files_run"),
                                         "after": "survived"}
        timeouts = [d for d in data["mutants"] if d["status"] == "timeout"]
        by_id = self._mutants_by_id(timeouts) if timeouts else {}
        flips = []
        t0 = time.time()
        for d in timeouts:
            m = by_id.get(d["id"])
            if m is None:
                continue
            run_mutant(m, self.root, self.test_cmd, timeout_s)
            rec = {"id": m.id, "before": "timeout", "after": m.status,
                   "seconds": round(m.seconds or 0, 1), "detail": (m.detail or "")[-200:]}
            self.log("recheck %-8s -> %-8s %s %.0fs" % ("timeout", m.status, m.id, m.seconds or 0))
            if m.status != "timeout":
                flips.append(rec)
                d["status"] = m.status
                d["recheck"] = rec
                d["seconds"] = m.seconds
                d["detail"] = m.detail
        killed = sum(1 for d in data["mutants"] if d["status"] in ("killed", "timeout"))
        data["killed"] = killed
        data["survived"] = sum(1 for d in data["mutants"] if d["status"] == "survived")
        data["score"] = round(killed / data["total"], 4) if data["total"] else 0.0
        data["recheck"] = {"timeouts": len(timeouts), "flips": flips,
                           "timeout_s": timeout_s, "seconds": round(time.time() - t0, 1),
                           "subset_checked": len(sub_sample), "subset_flips": sub_flips,
                           "subset_survivors": len(subset_survivors),
                           "subset_unverified": unverified}
        _dump_json(art, data)
        self._mark("recheck", "done", timeouts=len(timeouts), flips=len(flips),
                   score=data["score"], survived=data["survived"],
                   subset_checked=len(sub_sample), subset_flips=len(sub_flips))
        return data

    def stage_coverage(self, pytest_args=("-q", "-p", "no:cacheprovider", "tests"), targeted=True,
                       killed_sample=60, seed=0):
        """Targeted by default: trace only code objects holding a survivor
        line (+ `killed_sample` killed lines for the instrument self-check);
        full tracing of an interpreter is 10-30x slower than its suite."""
        art = self.path("coverage.json")
        if self.done("coverage"):
            return CV.load(art)
        self._mark("coverage", "running")
        data = _load_json(self.path("mutation-rechecked.json")) or _load_json(self.path("mutation.json"))
        interest = None
        if self.coverage_map is not None and not self.coverage_map_stale:
            # a full by-file map already exists (round 113): collapse it —
            # no second run, and a FULL (not targeted) coverage picture
            cov = CV.collapse(self.coverage_map)
            self.log("coverage: derived from the by-file map (full trace, %d test files)"
                     % len(self.coverage_map.get("_durations") or {}))
        else:
            if self.coverage_map is not None:
                self.log("coverage: by-file map is stale for %s -- ignoring it, running fresh "
                         "(round 137: a stale map here misclassifies killed-on-uncovered too)"
                         % ", ".join(self.coverage_map_stale))
            if targeted and data:
                interest = CV.interest_from_mutants(data["mutants"], killed_sample, seed)
                self.log("coverage: targeted run over %s lines of interest"
                         % {k: len(v) for k, v in interest.items()})
            cov = CV.collect(self.root, self.files, pytest_args, interest=interest)
        CV.save(cov, art)
        summaries = [CV.file_summary(self.root, rel, cov) for rel in self.files]
        for sm in summaries:
            self.log(CV.render_summary(sm))
        tri = CV.triage(data["mutants"], cov) if data else None
        _dump_json(self.path("coverage-summary.json"),
                   {"files": summaries, "triage": tri, "meta": cov["_meta"]})
        info = {"seconds": cov["_meta"]["seconds"], "returncode": cov["_meta"]["returncode"],
                "pct": dict((sm["file"], sm["pct"]) for sm in summaries)}
        info["targeted"] = interest is not None
        info["from_map"] = self.coverage_map is not None and not self.coverage_map_stale
        info["map_stale"] = list(self.coverage_map_stale)
        if tri:
            info.update(survived_uncovered=tri["survived_uncovered"],
                        survived_covered=tri["survived_covered"],
                        survived_unknown=tri["survived_unknown"],
                        killed_traced=tri["killed_traced"],
                        killed_on_uncovered=tri["killed_on_uncovered"])
        self._mark("coverage", "done", **info)
        return cov

    def coverage_split(self, ids):
        """{'covered': [...], 'uncovered': [...]} for mutant ids, using the
        coverage artifact when present (else everything is 'unknown')."""
        art = self.path("coverage.json")
        out = {"covered": [], "uncovered": [], "unknown": []}
        if not os.path.exists(art):
            out["unknown"] = list(ids)
            return out
        cov = CV.load(art)
        data = _load_json(self.path("mutation-rechecked.json")) or _load_json(self.path("mutation.json"))
        by_id = dict((d["id"], d) for d in CV.annotate_mutants(data["mutants"], cov))
        for i in ids:
            d = by_id.get(i)
            if d is None:
                out["unknown"].append(i)
            else:
                out["covered" if d["covered"] else "uncovered"].append(i)
        return out

    def survivors(self):
        data = _load_json(self.path("mutation-rechecked.json")) or _load_json(self.path("mutation.json"))
        return [d for d in data["mutants"] if d["status"] == "survived"]

    def stage_corpus(self, seed=0, corpus_n=300, extra_programs=(),
                     test_file="tests/test_generated_killers_r29.py", include_examples=True):
        art = self.path("killers.json")
        if self.done("corpus"):
            return _load_json(art)
        self._mark("corpus", "running")
        survivors = self.survivors()
        by_id = self._mutants_by_id(survivors)
        programs = list(extra_programs) + K.corpus(seed, corpus_n, self.root,
                                                   include_examples=include_examples)
        original = K.load_whence(self._original_project_dir(), "orig_camp")
        cache = {}
        killers = []
        t0 = time.time()
        for d in survivors:
            m = by_id.get(d["id"])
            if m is None:
                continue
            k = K.find_killer(m, programs, original, self.root, cache)
            killers.append(k)
            self.log("%-9s %s tried=%d %.1fs" % ("KILLER" if k.found else "no_killer",
                                                 m.id, k.tried, k.seconds))
        found = [k for k in killers if k.found]
        if found:
            self._pin(found, test_file)
        data = {"seed": seed, "corpus_n": corpus_n, "include_examples": include_examples,
                "extra_programs": len(extra_programs),
                "programs": len(programs), "survivors": len(survivors), "found": len(found),
                "no_killer": len(killers) - len(found), "test_file": test_file,
                "seconds": round(time.time() - t0, 1), "killers": [k.as_dict() for k in killers]}
        _dump_json(art, data)
        self._mark("corpus", "done", survivors=len(survivors), found=len(found),
                   no_killer=len(killers) - len(found), test_file=test_file)
        return data

    def _pin(self, killers, test_file):
        path = os.path.join(self.root, test_file)
        existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        body = K.render_tests(killers, existing)
        compile(body, path, "exec")          # a broken generated file must never land
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def _verify(self, ids, test_file, timeout_s=300.0):
        """Re-run each mutant against only the pinned test file."""
        by_id = self._mutants_by_id([{"id": i, "path": self.files[0]} for i in ids]) if ids else {}
        # mutants may live in any of self.files; rebuild per file
        if len(self.files) > 1:
            by_id = {}
            for rel in self.files:
                by_id.update(self._mutants_by_id([{"id": i, "path": rel} for i in ids
                                                  if i.startswith(os.path.basename(rel) + ":")]))
        out = []
        for i in ids:
            m = by_id.get(i)
            if m is None:
                out.append({"id": i, "status": "missing"})
                continue
            run_mutant(m, self.root, pinned_test_cmd(test_file), timeout_s)
            out.append({"id": i, "status": m.status, "seconds": round(m.seconds or 0, 1),
                        "detail": (m.detail or "")[-200:]})
            self.log("verify %-8s %s" % (m.status, i))
        return out

    def stage_verify(self):
        art = self.path("verify-corpus.json")
        if self.done("verify"):
            return _load_json(art)
        self._mark("verify", "running")
        kdata = _load_json(self.path("killers.json"))
        ids = [k["mutant"] for k in kdata["killers"] if k["found"]]
        res = self._verify(ids, kdata["test_file"])
        ok = sum(1 for r in res if r["status"] in ("killed", "timeout"))
        data = {"test_file": kdata["test_file"], "pinned": len(ids), "verified": ok, "results": res}
        _dump_json(art, data)
        self._mark("verify", "done", pinned=len(ids), verified=ok)
        return data

    def no_killer_ids(self):
        kdata = _load_json(self.path("killers.json")) or {"killers": []}
        return [k["mutant"] for k in kdata["killers"] if not k["found"]]

    def stage_triage(self):
        """Static classification of the survivors (swe.triage): which
        instrument can see each one; the score over the behavioural set."""
        art = self.path("triage.json")
        if self.done("triage"):
            return _load_json(art)
        self._mark("triage", "running")
        data = _load_json(self.path("mutation-rechecked.json")) or _load_json(self.path("mutation.json"))
        self._snapshot_files()
        srcs = dict((rel, open(os.path.join(self._snapshot_dir(), rel), encoding="utf-8").read())
                   for rel in self.files)
        t = TR.triage(data["mutants"], srcs)
        _dump_json(art, t)
        self.log(TR.render(t))
        self._mark("triage", "done", counts=t["counts"], score_all=t["score_all"],
                   score_behavioural=t["score_behavioural"])
        return t

    def stage_oracle_kill(self, seed=0, corpus_n=60, test_file="tests/test_oracle_killers_r113.py",
                          timeout_s=5.0, limit=6000):
        """modes / frames / counters differential over the `no_killer`
        survivors (swe.oraclekill); kills pinned into `test_file` and
        verified against the pinned file alone."""
        art = self.path("oracle-killers.json")
        if self.done("oracle_kill"):
            return _load_json(art)
        self._mark("oracle_kill", "running")
        partial = self.path("oracle-killers.partial.jsonl")
        done = dict((d["mutant"], d) for d in _read_jsonl(partial))
        pool = self.no_killer_ids()
        survivors = [d for d in self.survivors() if d["id"] in set(pool)]
        by_id = self._mutants_by_id(survivors)
        programs = OK.corpus(seed, corpus_n, self.root)
        original = OK.load_whence(self._original_project_dir(), "orig_okill")
        cache = {}
        kills = []
        t0 = time.time()
        for d in survivors:
            m = by_id.get(d["id"])
            if m is None:
                continue
            if m.id in done:
                rec = done[m.id]
                if rec["found"]:
                    kills.append(OK.OracleKill(m, rec["kind"], rec["program"], rec["expected"],
                                               rec["got"], rec["tried"], rec["seconds"]))
                continue
            k = OK.find_oracle_killer(m, programs, original, self.root, cache, timeout_s=timeout_s, limit=limit)
            rec = k.as_dict()
            _append_jsonl(partial, rec)
            done[m.id] = rec
            if k.found:
                kills.append(k)
            self.log("%-9s %-8s %s tried=%d %.1fs" % ("OKILLER" if k.found else "no_killer",
                                                      k.kind or "-", m.id, k.tried, k.seconds))
        verified = []
        if kills:
            path = os.path.join(self.root, test_file)
            existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            body = OK.render_tests(kills, existing)
            compile(body, path, "exec")
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            verified = self._verify([k.mutant.id for k in kills], test_file)
        recs = [done[i] for i in pool if i in done]
        by_kind = dict((kind, sum(1 for r in recs if r["found"] and r["kind"] == kind))
                       for kind in ("modes", "frames", "counters"))
        data = {"seed": seed, "corpus_n": corpus_n, "programs": len(programs), "limit": limit,
                "pool": len(pool), "found": sum(1 for r in recs if r["found"]), "by_kind": by_kind,
                "no_killer": sum(1 for r in recs if not r["found"]), "test_file": test_file,
                "verified": sum(1 for v in verified if v["status"] in ("killed", "timeout")),
                "verify": verified, "seconds": round(time.time() - t0, 1), "killers": recs}
        _dump_json(art, data)
        self._mark("oracle_kill", "done", pool=len(pool), found=data["found"], by_kind=by_kind,
                   verified=data["verified"], test_file=test_file)
        return data

    def live_pool(self, exclude_classes=TR.NON_BEHAVIOURAL):
        """`no_killer` survivors minus the oracle kills minus the triage
        classes no program can observe: where a model's time can pay."""
        pool = self.no_killer_ids()
        ok = _load_json(self.path("oracle-killers.json")) or {"killers": []}
        killed = set(k["mutant"] for k in ok["killers"] if k["found"])
        tri = _load_json(self.path("triage.json")) or {"classes": {}}
        skip = set()
        for c in exclude_classes:
            skip.update(tri["classes"].get(c, []))
        return [i for i in pool if i not in killed and i not in skip]

    def stage_live_kill(self, make_llm, n=8, seed=0, max_steps=20,
                        test_file="tests/test_model_killers_r29.py", model=""):
        art = self.path("live-kill.json")
        if self.done("live_kill"):
            return _load_json(art)
        self._mark("live_kill", "running")
        partial = self.path("live-kill.partial.jsonl")
        done = dict((d["mutant"], d) for d in _read_jsonl(partial))
        pool = self.live_pool()
        rng = random.Random(seed)
        sample = sorted(rng.sample(pool, min(n, len(pool))))
        survivors = self.survivors()
        by_id = self._mutants_by_id([d for d in survivors if d["id"] in set(sample)])
        out_dir = self.path("live-kill")
        os.makedirs(out_dir, exist_ok=True)
        for mid in sample:
            if mid in done:
                self.log("live_kill resume: %s already %s" % (mid, done[mid]["outcome"]))
                continue
            m = by_id.get(mid)
            if m is None:
                continue
            recs = R.run_kill(make_llm, [m], self.root, out_dir, max_steps=max_steps)
            rec = recs[0]
            rec["model"] = model
            _append_jsonl(partial, rec)
            done[mid] = rec
            self.log("live_kill %-18s %s steps=%s $%.3f" % (
                rec["outcome"], mid, rec.get("steps"), rec.get("cost_usd") or 0.0))   # None when unpriced
        recs = [done[i] for i in sample if i in done]
        killed = [r for r in recs if r["killed"]]
        verified = []
        if killed:
            ks = []
            for r in killed:
                ks.append(K.Killer(by_id[r["mutant"]], r["minimized"], r["expected"],
                                   r.get("mutant_behaviour"), 0, r.get("seconds", 0)))
            self._pin(ks, test_file)
            verified = self._verify([r["mutant"] for r in killed], test_file)
        data = {"sample": sample, "pool": len(pool), "attempted": len(recs),
                "killed": len(killed),
                "equivalent_claimed": sum(1 for r in recs if r["outcome"] == "equivalent_claimed"),
                "failed": sum(1 for r in recs if r["outcome"] == "failed"),
                "verified": sum(1 for v in verified if v["status"] in ("killed", "timeout")),
                "cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in recs), 4),
                "steps": sum(r.get("steps", 0) or 0 for r in recs),
                "test_file": test_file, "model": model, "results": recs, "verify": verified}
        _dump_json(art, data)
        self._mark("live_kill", "done", attempted=len(recs), killed=len(killed),
                   verified=data["verified"], cost_usd=data["cost_usd"])
        return data

    def stage_review(self, make_llm, files=None, focus="", max_steps=30, model="", read_budget=None):
        art = self.path("review.json")
        if self.done("review"):
            return _load_json(art)
        self._mark("review", "running")
        out_dir = self.path("review")
        os.makedirs(out_dir, exist_ok=True)
        rec = R.run_review(make_llm, self.root, tuple(files or self.files), focus,
                           out_dir=out_dir, max_steps=max_steps, tag="review", read_budget=read_budget)
        rec["model"] = model
        rec["tool_histogram"] = tool_histogram(os.path.join(out_dir, "review.trace.jsonl"))
        _dump_json(art, rec)
        self._mark("review", "done", claimed=rec["claimed"], confirmed=rec["confirmed"],
                   oracle_calls=rec["tool_histogram"].get("oracle_check", 0),
                   cost_usd=rec.get("cost_usd", 0.0))
        return rec

    def stage_repair(self, make_llm, n=6, seed=0, max_steps=25, model="", ops=None,
                     test_args="-q tests", fail_args=("-q", "-x", "tests"), read_budget=None):
        art = self.path("repair.json")
        if self.done("repair"):
            return _load_json(art)
        self._mark("repair", "running")
        partial = self.path("repair.partial.jsonl")
        done = dict((d["mutant"], d) for d in _read_jsonl(partial))
        mj = self.path("mutation-rechecked.json") if os.path.exists(self.path("mutation-rechecked.json")) \
            else self.path("mutation.json")
        pool = RP.killed_pool(mj, ops=ops)
        sample = RP.stratified_sample(pool, n, seed)
        by_id = self._mutants_by_id(sample)
        out_dir = self.path("repair")
        os.makedirs(out_dir, exist_ok=True)
        for d in sample:
            mid = d["id"]
            if mid in done:
                self.log("repair resume: %s already %s" % (mid, done[mid]["outcome"]))
                continue
            m = by_id.get(mid)
            if m is None:
                continue
            recs = RP.run_repair(make_llm, [m], self.root, out_dir, max_steps=max_steps,
                                 test_args=test_args, fail_args=fail_args, read_budget=read_budget)
            rec = recs[0]
            rec["model"] = model
            _append_jsonl(partial, rec)
            done[mid] = rec
            self.log("repair %-20s %s steps=%s $%.3f" % (
                rec["outcome"], mid, rec.get("steps"), rec.get("cost_usd", 0.0) or 0.0))
        recs = [done[d["id"]] for d in sample if d["id"] in done]
        data = {"sample": [d["id"] for d in sample], "pool": len(pool), "model": model,
                "max_steps": max_steps, "test_args": test_args, "read_budget": read_budget,
                "summary": RP.summarize(recs), "results": recs}
        _dump_json(art, data)
        sm = data["summary"]
        self._mark("repair", "done", attempted=sm["attempted"], green=sm["green"],
                   exact=sm["exact"], ast_exact=sm["ast_exact"], localized=sm["localized"],
                   cost_usd=sm["cost_usd"])
        return data

    def stage_report(self):
        self._mark("report", "running")
        base = _load_json(self.path("mutation.json")) or {}
        rech = _load_json(self.path("mutation-rechecked.json"))
        corpus = _load_json(self.path("killers.json")) or {}
        verify = _load_json(self.path("verify-corpus.json")) or {}
        live = _load_json(self.path("live-kill.json")) or {}
        review = _load_json(self.path("review.json")) or {}
        covsum = _load_json(self.path("coverage-summary.json")) or {}
        repair = _load_json(self.path("repair.json")) or {}
        tri = _load_json(self.path("triage.json")) or {}
        okill = _load_json(self.path("oracle-killers.json")) or {}
        total = base.get("total", 0)
        killed = (rech or base).get("killed", 0)
        new_pins = verify.get("verified", 0) + live.get("verified", 0) + okill.get("verified", 0)
        rep = {
            "total": total,
            "baseline": {"killed": base.get("killed"), "survived": base.get("survived"),
                         "score": base.get("score"), "seconds": base.get("seconds")},
            "recheck": (rech or {}).get("recheck"),
            "corrected": {"killed": killed, "survived": (rech or base).get("survived"),
                          "score": (rech or base).get("score")},
            "corpus": {"survivors": corpus.get("survivors"), "found": corpus.get("found"),
                       "no_killer": corpus.get("no_killer"), "verified": verify.get("verified"),
                       "programs": corpus.get("programs")},
            "live_kill": dict((k, live.get(k)) for k in
                              ("attempted", "killed", "equivalent_claimed", "failed",
                               "verified", "cost_usd", "steps", "model")),
            "review": dict((k, review.get(k)) for k in
                           ("claimed", "confirmed", "steps", "tool_calls", "cost_usd",
                            "stop_reason", "model", "tool_histogram")),
            "coverage": self._coverage_block(covsum, corpus),
            "triage": dict((k, tri.get(k)) for k in ("counts", "score_all", "score_behavioural",
                                                     "behavioural_total", "behavioural_killed")) if tri else None,
            "oracle_kill": dict((k, okill.get(k)) for k in ("pool", "found", "by_kind", "verified",
                                                            "programs")) if okill else None,
            "subset": ((rech or {}).get("recheck") or {}).get("subset_survivors") and {
                "subset_survivors": rech["recheck"]["subset_survivors"],
                "subset_checked": rech["recheck"]["subset_checked"],
                "subset_flips": len(rech["recheck"]["subset_flips"])},
            "repair": dict((k, (repair.get("summary") or {}).get(k)) for k in
                           ("attempted", "green", "exact", "ast_exact", "localized", "cheated",
                            "green_not_exact", "cost_usd", "steps")),
            "tests_added": new_pins,
            "projected_score": round((killed + new_pins) / total, 4) if total else None,
            "cost_usd": round((live.get("cost_usd") or 0.0) + (review.get("cost_usd") or 0.0)
                              + ((repair.get("summary") or {}).get("cost_usd") or 0.0), 4),
        }
        rep["repair"]["model"] = repair.get("model")
        _dump_json(self.path("report.json"), rep)
        with open(self.path("report.md"), "w", encoding="utf-8") as f:
            f.write(render_report(rep))
        self._mark("report", "done", projected_score=rep["projected_score"],
                   tests_added=new_pins)
        return rep


    def _coverage_block(self, covsum, corpus):
        """Coverage pct per file, the survivor split, and the corpus kill rate
        on each side of the split (P5: uncovered survivors should be the
        killable ones)."""
        if not covsum:
            return None
        tri = covsum.get("triage") or {}
        block = {"pct": dict((f["file"], f["pct"]) for f in covsum.get("files", [])),
                 "targeted": (covsum.get("meta") or {}).get("targeted", False),
                 "never_executed_defs": sum(len(f["never_executed_defs"]) for f in covsum.get("files", [])),
                 "survived_covered": tri.get("survived_covered"),
                 "survived_uncovered": tri.get("survived_uncovered"),
                 "survived_unknown": tri.get("survived_unknown"),
                 "killed_traced": tri.get("killed_traced"),
                 "killed_on_uncovered": tri.get("killed_on_uncovered")}
        ks = corpus.get("killers") or []
        if ks:
            split = self.coverage_split([k["mutant"] for k in ks])
            found = set(k["mutant"] for k in ks if k["found"])
            for side in ("covered", "uncovered"):
                ids = split[side]
                block["corpus_found_" + side] = sum(1 for i in ids if i in found)
                block["corpus_tried_" + side] = len(ids)
        return block


def tool_histogram(trace_path):
    hist = {}
    for r in _read_jsonl(trace_path):
        if r.get("event") == "tool_call":
            hist[r["name"]] = hist.get(r["name"], 0) + 1
    return hist


def render_report(rep):
    b, c, co, lk, rv = rep["baseline"], rep["corrected"], rep["corpus"], rep["live_kill"], rep["review"]
    lines = ["# SWE campaign report", "",
             "| metric | value |", "|---|---|",
             "| mutants | %s |" % rep["total"],
             "| baseline score | %s (%s killed / %s survived, %s s) |"
             % (b["score"], b["killed"], b["survived"], b["seconds"]),
             "| timeout recheck flips | %s of %s timeouts |"
             % (len((rep["recheck"] or {}).get("flips", [])), (rep["recheck"] or {}).get("timeouts")),
             "| corrected score | %s (%s survived) |" % (c["score"], c["survived"]),
             "| corpus killers | %s of %s survivors (%s no_killer), %s verified |"
             % (co["found"], co["survivors"], co["no_killer"], co["verified"]),
             "| model kills | %s of %s attempted, %s equivalent claimed, %s verified, $%s, %s steps |"
             % (lk["killed"], lk["attempted"], lk["equivalent_claimed"], lk["verified"],
                lk["cost_usd"], lk["steps"]),
             "| review | %s claims, %s confirmed, tools %s, $%s, stop=%s |"
             % (rv["claimed"], rv["confirmed"], rv["tool_histogram"], rv["cost_usd"], rv["stop_reason"]),
             "| coverage | %s |" % _cov_row(rep.get("coverage")),
             "| subset verdicts | %s |" % _subset_row(rep.get("subset")),
             "| triage | %s |" % _triage_row(rep.get("triage")),
             "| oracle kills | %s |" % _okill_row(rep.get("oracle_kill")),
             "| repair | %s |" % _repair_row(rep.get("repair")),
             "| tests added | %s |" % rep["tests_added"],
             "| projected final score | %s |" % rep["projected_score"],
             "| live cost | $%s |" % rep["cost_usd"], ""]
    return "\n".join(lines)


def _cov_row(c):
    if not c:
        return "n/a"
    s = "%s%s; survivors %s covered / %s uncovered; killed-on-uncovered %s of %s traced" % (
        ", ".join("%s %.1f%%" % (f, p or 0.0) for f, p in c["pct"].items()),
        " (targeted, lower bound)" if c.get("targeted") else "",
        c["survived_covered"], c["survived_uncovered"], c["killed_on_uncovered"], c.get("killed_traced"))
    if "corpus_tried_covered" in c:
        s += "; corpus kills %s/%s covered vs %s/%s uncovered" % (
            c["corpus_found_covered"], c["corpus_tried_covered"],
            c["corpus_found_uncovered"], c["corpus_tried_uncovered"])
    return s


def _subset_row(s):
    if not s:
        return "n/a"
    return "%s survivors on a covering subset; %s re-run under the full suite, %s flipped" % (
        s["subset_survivors"], s["subset_checked"], s["subset_flips"])


def _triage_row(t):
    if not t:
        return "n/a"
    return "survivors %s; score all %s, behavioural %s (%s/%s)" % (
        ", ".join("%s %d" % (k, v) for k, v in (t.get("counts") or {}).items()),
        t["score_all"], t["score_behavioural"], t["behavioural_killed"], t["behavioural_total"])


def _okill_row(o):
    if not o:
        return "n/a"
    return "%s of %s no_killer survivors (%s), %s verified, %s programs" % (
        o["found"], o["pool"], ", ".join("%s %d" % (k, v) for k, v in (o.get("by_kind") or {}).items()),
        o["verified"], o["programs"])


def _repair_row(r):
    if not r or r.get("attempted") is None:
        return "n/a"
    # "exact" = the outcome CLASS (AST-exact fix AND green); "ast_exact" is
    # the weaker per-record signal alone -- a fix can be ast_exact without
    # being exact if something unrelated (e.g. an environment bug, see
    # harness/swe/repair.py::summarize's docstring) blocks the suite from
    # going green, and that gap is invisible unless both numbers are shown.
    return ("%s attempted: %s green, %s exact (%s ast-exact), %s localized, %s green-not-exact, "
            "%s cheated, $%s, %s steps (%s)"
            % (r["attempted"], r["green"], r["exact"], r.get("ast_exact", r["exact"]), r["localized"],
               r["green_not_exact"], r["cheated"], r["cost_usd"], r["steps"], r.get("model")))


def load_programs(path):
    """Extra corpus programs: a JSON list of strings, or a text file with
    programs separated by lines that are exactly `---`."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        data = json.loads(text)
        return [p for p in data if isinstance(p, str)]
    return [p.strip() + "\n" for p in text.split("\n---\n") if p.strip()]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--files", default="whence/interp.py", help="comma list relative to root")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--adopt-mutation", help="existing mutation JSON to take as the baseline")
    ap.add_argument("--prioritize-from", help="previous mutation JSON/partial.jsonl: run the test files "
                    "that killed the nearest mutants first (verdict-invariant under -x)")
    ap.add_argument("--coverage-map", help="by-file coverage JSON (swe.coverage --by-file): kill-first "
                    "order from real coverage, covering-subset verdicts, and the coverage stage derived from it")
    ap.add_argument("--no-subset", action="store_true", help="with --coverage-map: order only, run the full suite")
    ap.add_argument("--allow-stale-map", action="store_true",
                    help="with --coverage-map: keep subset restriction even if the on-disk file's "
                    "hash no longer matches the map's collection-time hash (DANGEROUS -- see "
                    "coverage.stale_files' docstring; rounds 113/137 both burned a full-suite "
                    "recheck for exactly this)")
    ap.add_argument("--subset-check", type=int, default=20,
                    help="recheck: subset-basis survivors re-run under the full suite (instrument self-check)")
    ap.add_argument("--recheck-timeout", type=float, default=600.0)
    ap.add_argument("--corpus-n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--extra-programs", help="JSON list or ---separated file of extra corpus programs")
    ap.add_argument("--no-examples", action="store_true", help="corpus: leave the checked-in examples out")
    ap.add_argument("--test-file-corpus", default="tests/test_generated_killers_r29.py")
    ap.add_argument("--test-file-model", default="tests/test_model_killers_r29.py")
    ap.add_argument("--no-oracle-kill", action="store_true", help="skip the triage + oracle-kill stages")
    ap.add_argument("--oracle-corpus-n", type=int, default=60)
    ap.add_argument("--oracle-limit", type=int, default=6000, help="host recursion limit for the frames probe")
    ap.add_argument("--test-file-oracle", default="tests/test_oracle_killers_r113.py")
    ap.add_argument("--live-kill", type=int, default=0, help="model kills on N sampled no_killer survivors")
    ap.add_argument("--live-review", action="store_true")
    ap.add_argument("--live-repair", type=int, default=0, help="model repairs on N sampled killed mutants")
    ap.add_argument("--repair-steps", type=int, default=25)
    ap.add_argument("--read-budget", type=int, default=0,
                    help="review/repair: hard cap on outline/read_file/search calls (0 = none)")
    ap.add_argument("--no-coverage", action="store_true", help="skip the coverage stage")
    ap.add_argument("--full-coverage", action="store_true", help="trace every line (slow) instead of survivor lines")
    ap.add_argument("--focus", default="")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--review-steps", type=int, default=30)
    ap.add_argument("--force", default="", help="comma list of stages to redo")
    ap.add_argument("--stop-after", default="", choices=("",) + STAGES)
    a = ap.parse_args(argv)

    files = tuple(p.strip() for p in a.files.split(",") if p.strip())
    pr = PR.Prioritizer.from_file(a.prioritize_from, a.root) if a.prioritize_from else None
    cov_map = None
    if a.coverage_map:
        cov_map = CV.load(a.coverage_map)
        pr = PR.MapPrioritizer(cov_map, PR.default_test_files(a.root), subset=not a.no_subset,
                               root=a.root, require_fresh=not a.allow_stale_map)
        if pr.stale:
            print("WARNING: --coverage-map %s is stale for %s (on-disk hash differs from "
                  "collection time) -- subset restriction DISABLED, falling back to "
                  "order-only (pass --allow-stale-map to force it back on)"
                  % (a.coverage_map, ", ".join(pr.stale)))
    c = Campaign(a.out, a.root, files, prioritizer=pr, coverage_map=cov_map)
    if a.force:
        c.force([s.strip() for s in a.force.split(",") if s.strip()])
    extra = load_programs(a.extra_programs) if a.extra_programs else ()

    def after(stage):
        return a.stop_after == stage

    c.stage_mutation(workers=a.workers, timeout_s=a.timeout, limit=a.limit or None,
                     adopt=a.adopt_mutation)
    if after("mutation"):
        return 0
    c.stage_recheck(timeout_s=a.recheck_timeout, subset_check=a.subset_check, seed=a.seed)
    if after("recheck"):
        return 0
    if not a.no_coverage:
        c.stage_coverage(targeted=not a.full_coverage, seed=a.seed)
        if after("coverage"):
            return 0
    c.stage_corpus(seed=a.seed, corpus_n=a.corpus_n, extra_programs=extra,
                   test_file=a.test_file_corpus, include_examples=not a.no_examples)
    if after("corpus"):
        return 0
    c.stage_verify()
    if after("verify"):
        return 0
    if not a.no_oracle_kill:
        c.stage_triage()
        if after("triage"):
            return 0
        c.stage_oracle_kill(seed=a.seed, corpus_n=a.oracle_corpus_n, test_file=a.test_file_oracle,
                            limit=a.oracle_limit)
        if after("oracle_kill"):
            return 0
    if a.live_kill or a.live_review or a.live_repair:
        from agentloop.adapters import ClaudeCLILLM
        make_llm = lambda: ClaudeCLILLM(model=a.model, timeout_s=600)   # noqa: E731
        if a.live_kill:
            c.stage_live_kill(make_llm, n=a.live_kill, seed=a.seed, max_steps=a.max_steps,
                              test_file=a.test_file_model, model=a.model)
            if after("live_kill"):
                return 0
        if a.live_review:
            c.stage_review(make_llm, files, a.focus, max_steps=a.review_steps, model=a.model,
                           read_budget=a.read_budget or None)
            if after("review"):
                return 0
        if a.live_repair:
            c.stage_repair(make_llm, n=a.live_repair, seed=a.seed, max_steps=a.repair_steps,
                           model=a.model, read_budget=a.read_budget or None)
            if after("repair"):
                return 0
    rep = c.stage_report()
    print(render_report(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
