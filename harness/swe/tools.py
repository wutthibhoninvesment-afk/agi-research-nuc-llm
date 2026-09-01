"""The SWE engines as agentloop Tools.

Every tool is sandboxed to one Whence checkout (`root`) and writes its
artifacts under `outdir` so the trace, the crashers, the mutation JSON and
the generated tests are all inspectable after the run. Tool output is what
the model sees, so summaries are short and the JSON is on disk.
"""

import json
import os
import subprocess
import sys

from .proc import run_capped

from agentloop.tools import Tool, ToolResult
from . import fuzz as F
from . import mutation as M
from . import killers as K
from . import oracles as O


class FuzzTool(Tool):
    name = "fuzz"
    description = ("Fuzz the Whence interpreter with random programs. Reports "
                   "unique crash signatures (Python exceptions escaping the "
                   "interpreter = totality bugs) and writes minimized "
                   "reproducers to <outdir>/crashers/.")
    params = {
        "seed": {"type": "integer", "description": "campaign seed"},
        "n": {"type": "integer", "description": "number of programs (default 300)"},
    }
    required = ["seed"]

    def __init__(self, root, outdir):
        self.root = root
        self.outdir = outdir
        self.last = None

    def run(self, seed, n=300):
        camp = F.fuzz(seed=int(seed), n=int(n), root=self.root)
        self.last = camp
        cdir = os.path.join(self.outdir, "crashers")
        os.makedirs(cdir, exist_ok=True)
        for i, (sig, cr) in enumerate(sorted(camp.crashers.items())):
            with open(os.path.join(cdir, "crash-%02d.lang" % i), "w") as f:
                f.write("# %s\n" % " | ".join(sig))
                f.write(cr.minimized or cr.src)
        with open(os.path.join(self.outdir, "fuzz-%d.json" % seed), "w") as f:
            json.dump(camp.as_dict(), f, indent=1)
        text = camp.summary()
        for i, (sig, cr) in enumerate(sorted(camp.crashers.items())):
            text += "\n\n[crash-%02d] %s\n%s" % (i, " | ".join(sig), (cr.minimized or cr.src).strip())
        return ToolResult(True, text)


class OracleFuzzTool(Tool):
    name = "oracle_fuzz"
    description = ("Fuzz the Whence interpreter against its differential/metamorphic "
                   "oracles (totality, fast_slow, direct, determinism, render): random programs "
                   "plus the checked-in examples; reports unique finding signatures "
                   "(crashes AND semantic mismatches) with minimized reproducers, "
                   "written to <outdir>/oracle-findings/.")
    params = {
        "seed": {"type": "integer", "description": "campaign seed"},
        "n": {"type": "integer", "description": "number of generated programs (default 200)"},
        "oracles": {"type": "string", "description": "comma list (default: all)"},
    }
    required = ["seed"]

    def __init__(self, root, outdir):
        self.root = root
        self.outdir = outdir
        self.last = None

    def run(self, seed, n=200, oracles=None):
        names = tuple(x.strip() for x in (oracles or "").split(",") if x.strip()) or O.ORACLE_NAMES
        camp = O.fuzz_oracles(seed=int(seed), n=int(n), oracles=names, root=self.root,
                              extra_programs=O.example_programs(self.root))
        self.last = camp
        fdir = os.path.join(self.outdir, "oracle-findings")
        os.makedirs(fdir, exist_ok=True)
        for i, (sig, f) in enumerate(sorted(camp.findings.items())):
            with open(os.path.join(fdir, "finding-%02d.lang" % i), "w") as fh:
                fh.write("# %s\n# %s\n" % (" | ".join(sig), f.outcome.detail.replace("\n", " ")[:200]))
                fh.write(f.minimized or f.src)
            with open(os.path.join(fdir, "finding-%02d.json" % i), "w") as fh:
                json.dump({"program": f.minimized or f.src, "oracle": f.outcome.oracle,
                           "detail": f.outcome.detail, "signature": list(sig)}, fh, indent=1)
        with open(os.path.join(self.outdir, "oracle-fuzz-%d.json" % int(seed)), "w") as fh:
            json.dump(camp.as_dict(), fh, indent=1)
        text = camp.summary()
        for i, (sig, f) in enumerate(sorted(camp.findings.items())):
            text += "\n\n[finding-%02d] %s\n%s\n--- %s" % (
                i, " | ".join(sig), (f.minimized or f.src).strip(), f.outcome.detail[:300])
        return ToolResult(True, text)


class MutationTool(Tool):
    name = "mutate"
    description = ("Mutation-test Python files of the Whence checkout against "
                   "its pytest suite. Returns score and the SURVIVED mutants "
                   "(test gaps). Writes <outdir>/mutation.json.")
    params = {
        "files": {"type": "string", "description": "comma-separated paths relative to checkout"},
        "limit": {"type": "integer", "description": "cap on mutant count (0 = all)"},
        "workers": {"type": "integer", "description": "parallel test runs (default 4)"},
    }
    required = ["files"]

    def __init__(self, root, outdir, json_name="mutation.json", test_cmd=None):
        self.root = root
        self.outdir = outdir
        self.json_name = json_name
        #: Round 419: the suite each mutant is scored against. Was
        #: `M.DEFAULT_TEST_CMD` unconditionally, which is the entire whence
        #: suite per mutant — correct for a real campaign and unaffordable
        #: for any test of the loop that composes this tool.
        self.test_cmd = list(test_cmd) if test_cmd else list(M.DEFAULT_TEST_CMD)
        self.last = None

    def run(self, files, limit=0, workers=4):
        rels = [p.strip() for p in files.split(",") if p.strip()]
        rep = M.mutation_test(self.root, rels, self.test_cmd, workers=int(workers),
                              limit=int(limit) or None)
        self.last = rep
        os.makedirs(self.outdir, exist_ok=True)
        with open(os.path.join(self.outdir, self.json_name), "w") as f:
            json.dump(rep.as_dict(), f, indent=1)
        return ToolResult(True, rep.summary())


class KillTool(Tool):
    name = "kill_survivors"
    description = ("For each surviving mutant in <outdir>/mutation.json, search "
                   "a corpus of generated programs for one whose behaviour "
                   "differs under the mutant, shrink it, and append a pytest "
                   "pinning the original behaviour to the given test file.")
    params = {
        "test_file": {"type": "string", "description": "test file path relative to checkout"},
        "corpus_n": {"type": "integer", "description": "generated programs to try (default 300)"},
        "seed": {"type": "integer", "description": "corpus seed (default 0)"},
    }
    required = ["test_file"]

    def __init__(self, root, outdir, json_name="mutation.json"):
        self.root = root
        self.outdir = outdir
        self.json_name = json_name
        self.last = None

    def run(self, test_file, corpus_n=300, seed=0):
        mj = os.path.join(self.outdir, self.json_name)
        if not os.path.exists(mj):
            return ToolResult(False, "no mutation results at %s; run 'mutate' first" % mj)
        survivors = K.load_survivors(mj)
        if not survivors:
            return ToolResult(True, "no survivors to kill")
        ms = K.rebuild_mutants(self.root, survivors)
        ks = K.generate_killers(ms, self.root, int(seed), int(corpus_n))
        self.last = ks
        path = os.path.join(self.root, test_file)
        existing = open(path).read() if os.path.exists(path) else ""
        with open(path, "w") as f:
            f.write(K.render_tests(ks, existing))
        with open(os.path.join(self.outdir, "killers.json"), "w") as f:
            json.dump([k.as_dict() for k in ks], f, indent=1)
        found = [k for k in ks if k.found]
        lines = ["killers: %d/%d survivors got a killing test -> %s"
                 % (len(found), len(ks), test_file)]
        for k in ks:
            lines.append("  %-9s %-34s %s" % ("KILLER" if k.found else "no_killer",
                                              k.mutant.id, k.mutant.description))
        return ToolResult(True, "\n".join(lines))


class PytestTool(Tool):
    name = "pytest"
    description = "Run the checkout's pytest suite; returns the tail of the output and exit code."
    params = {"args": {"type": "string", "description": "extra pytest args (default '-q tests')"}}
    required = []

    def __init__(self, root, timeout_s=600):
        self.root = root
        self.timeout_s = timeout_s

    def run(self, args="-q tests"):
        cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + args.split()
        r = run_capped(cmd, self.root, self.timeout_s)
        if r.timed_out:
            return ToolResult(False, "pytest timed out after %ds (process group killed)" % self.timeout_s)
        tail = "\n".join(r.output.strip().splitlines()[-15:])
        return ToolResult(r.returncode == 0, tail + "\n[exit %d]" % r.returncode)


class WhenceRunTool(Tool):
    name = "whence_run"
    description = ("Run Whence source in-process and report behaviour as data "
                   "(kind, printed lines, checks, bindings) — crashes are "
                   "reported as kind=crash with the exception type.")
    params = {"source": {"type": "string", "description": "Whence program text"}}
    required = ["source"]

    def __init__(self, root, tag="tool"):
        self.root = root
        self.tag = tag          # package tag: distinct per checkout copy
        self._pkg = None

    def run(self, source):
        if self._pkg is None:
            self._pkg = K.load_whence(self.root, self.tag)
        b = K.behaviour(self._pkg, source, timeout_s=5.0, max_depth=2000)
        return ToolResult(b.get("kind") != "crash", json.dumps(b, ensure_ascii=False, indent=1))
