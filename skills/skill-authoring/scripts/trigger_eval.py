#!/usr/bin/env python3
"""trigger_eval.py — measure whether SKILL.md descriptions actually trigger.

Gives a *fresh* Claude Code instance (``claude -p``) a task phrased without
the skill's name and records which skills it invoked. Aggregates per-skill
precision/recall over a labelled case file, so description edits can be
evaluated instead of guessed.

Usage:
    python3 trigger_eval.py CASES.json --skills DIR [--skills DIR ...]
        [--mode native|catalog|body] [--model sonnet[,haiku,...]] [--repeats 1]
        [--concurrency 4] [--timeout 150] [--json OUT.json] [--only ID,ID]
        [--distractors DIR] [--n-distractors N] [--distractor-seed S]
        [--body-tools "Skill,Read"] [--paired] [--transcripts DIR]
        [--canary CANARY.json]

Modes:
    native   (default) Stage the skills in a temp project's ``.claude/skills/``
             and run ``claude -p`` there with only the Skill tool enabled; a
             skill counts as *fired* when the model emits a ``Skill`` tool_use
             for it. This exercises the real skill index + selection path.
             The host's user-level skills are present too and act as natural
             distractors (they are listed in the report).
    catalog  Put the catalog (name + description of every skill) in the
             prompt and ask for a JSON list of the skills the model would
             invoke. No tools, cheaper, but tests the description text in
             isolation rather than the real selection path.
    body     Body-following: the probe is told to DO the task (tools from
             ``--body-tools``, default Skill+Read; deliverable goes in the
             reply). Besides which skills fired, records which *staged
             bundled files* were read (Read paths / Bash commands touching
             ``.claude/skills/…``) and which case-supplied ``body.evidence``
             regexes match the transcript — i.e. did the agent follow the
             loaded instructions, not just load them. A Read whose
             tool_result errored does NOT count as a file read; denied /
             failed reads are reported separately (``files_failed``).
             ``body.evidence_min: N`` makes a case count as followed when
             ≥N of its evidence regexes match (default: all — but
             all-or-nothing penalizes tasks where a marker can be
             legitimately out of scope).

Multi-model: ``--model sonnet,haiku`` runs every case per model and prints
one report per model plus a per-skill recall comparison table.

Fire rates: with ``--repeats N`` the report adds a per-case rate table
splitting *all-expected-fired* (every expected skill fired; for negatives:
nothing fired) from *exact* (fired set == expected set) — a case can fire
reliably yet rarely be exact because a sibling co-fires. Small probe
models are unreadable at n=1; decide from rates, not single runs.

``--paired`` (requires ``--distractors``): every probe runs twice — once
with only your skills staged ("plain") and once with the distractors
staged too ("staged") — and the report adds a per-case paired table with
a suppression verdict: a case whose fire count drops when siblings are
staged *without* the sibling firing is SUPPRESSED (the selector fired
neither contender); if the sibling fired while yours went missing it is
DISPLACED. This automates the round-21 paired diagnostic.

``--transcripts DIR`` writes every probe's full transcript (all assistant
text blocks + tool touches) to ``DIR/<model>[-<arm>]-<case>-<k>.txt`` —
the JSON keeps only a 4000-char tail, which is too little to diagnose a
long body-mode run.

``--canary CANARY.json`` runs frozen sentinel case(s) against stored
acceptance bands and exits 0 (in band) / 1 (drift) / 2 (inconclusive):
an instrument-drift tripwire to run at session start BEFORE trusting any
cross-round comparison (the host skill population shifts under the
benchmark). File: ``[{"case": "fmk-near", "model": "sonnet",
"repeats": 4, "min_rate": 0.75, "max_rate": 1.0, "mode": "native"}]``
(rate = all-expected-fired over non-errored runs).

Controlled distractors: ``--distractors DIR`` (repeatable, recursive,
lenient about broken frontmatter) stages foreign skills alongside yours —
``--n-distractors N --distractor-seed S`` picks a deterministic sample.
Fires on staged distractors are reported separately from host "foreign"
fires, and *displacement* (an expected skill missing while a staged
distractor fired) is counted.

Case file (JSON):
    [{"id": "gte-1", "prompt": "…indirect task…", "expect": ["skill-name"],
      "note": "optional"}, {"id": "neg-1", "prompt": "…", "expect": []},
     {"id": "body-1", "prompt": "…real task…", "expect": ["skill-name"],
      "body": {"files": ["skill-name/references/x.md"],
               "evidence": ["regex matched against transcript", "…"]}}]
    ``expect`` is the set of *our* skills that should fire; skills outside
    the staged set are reported as "foreign" fires but never counted as
    false positives (the host's own skills are out of our control).
    ``body`` is only used by ``--mode body``; ``files`` are staged-relative
    paths (``<skill>/<relpath>``), ``evidence`` are case-insensitive regexes.

Exit codes: 0 = ran and every case matched; 1 = ran with mismatches;
2 = usage / IO / runner problem.
"""

import argparse
import concurrent.futures
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_lint import parse_frontmatter  # noqa: E402

PROBE_SYSTEM = (
    "Skill-selection probe: if any available skill applies to the user's task, "
    "invoke it via the Skill tool FIRST (invoke every skill that applies, one "
    "at a time). As soon as the skill content has loaded, or if no skill "
    "applies, reply with exactly one line: SKILLS=<comma-separated skill "
    "names you invoked, or NONE> and stop. Do not perform the task itself."
)

CATALOG_PROMPT = (
    "You are an agent with the following skills available. Each entry is a "
    "skill name followed by its description; a skill's full instructions are "
    "loaded only if you choose to invoke it.\n\n{catalog}\n\n"
    "A user sends this task:\n\n<task>\n{task}\n</task>\n\n"
    "Which skills would you invoke before starting the task? Reply with ONLY a "
    "JSON object of the form {{\"skills\": [\"name\", ...]}} — an empty list if "
    "none applies. No prose."
)

BODY_SYSTEM = (
    "Skill-following probe: if any available skill applies to the user's "
    "task, invoke it via the Skill tool FIRST, then FOLLOW the loaded "
    "instructions — including reading any bundled reference files they "
    "point to — while you carry out the task. You have no write access: "
    "deliver all work product (code, analysis, rewritten text) directly in "
    "your reply. Be concrete; show real code where the task needs it."
)

SKILLS_LINE_RE = re.compile(r"SKILLS\s*=\s*(.+)", re.I)
SKILL_PATH_RE = re.compile(r"\.claude/skills/([^\s'\"`)\]]+)")
DENIED_RE = re.compile(r"permission|denied|haven'?t granted|not.{0,20}allowed", re.I)


def _result_text(content):
    """Flatten a tool_result ``content`` (string, or list of text blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict))
    return ""


# ----------------------------------------------------------------- catalog --
def load_catalog(skill_dirs, lenient=False, recursive=False):
    """Return [(name, description, path)] for every SKILL.md under the given
    skill directories (each may be a skill dir or a directory of them).
    ``recursive`` also finds skills nested deeper (category/skill/SKILL.md);
    ``lenient`` skips (with a stderr note) skills whose frontmatter does not
    parse instead of raising — for wild corpora used as distractors."""
    out = []
    skipped = []
    for root in skill_dirs:
        root = os.path.expanduser(root)
        candidates = []
        if os.path.isfile(os.path.join(root, "SKILL.md")):
            candidates.append(root)
        elif os.path.isdir(root):
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                    if "SKILL.md" in filenames:
                        candidates.append(dirpath)
                        dirnames[:] = []  # a skill dir's subdirs are bundled files
            else:
                for e in sorted(os.listdir(root)):
                    d = os.path.join(root, e)
                    if os.path.isfile(os.path.join(d, "SKILL.md")):
                        candidates.append(d)
        for d in candidates:
            with open(os.path.join(d, "SKILL.md"), encoding="utf-8") as f:
                fields, _, err = parse_frontmatter(f.read())
            if err:
                if lenient:
                    skipped.append(d)
                    continue
                raise ValueError("%s: %s" % (d, err))
            name = fields.get("name") or os.path.basename(os.path.abspath(d))
            out.append((name, fields.get("description", ""), os.path.abspath(d)))
    if skipped:
        print("trigger-eval: skipped %d unparseable skill(s): %s"
              % (len(skipped), ", ".join(os.path.basename(s) for s in skipped)),
              file=sys.stderr)
    return out


def pick_distractors(pool, ours_names, n, seed):
    """Deterministically sample ``n`` distractor skills from ``pool``
    (name-deduped, ours excluded, sorted by name first so the sample depends
    only on names + seed). ``n < 0`` keeps the whole pool."""
    seen = set(ours_names)
    uniq = []
    for c in sorted(pool, key=lambda c: c[0]):
        if c[0] not in seen:
            seen.add(c[0])
            uniq.append(c)
    if 0 <= n < len(uniq):
        uniq = sorted(random.Random(seed).sample(uniq, n), key=lambda c: c[0])
    return uniq


def load_cases(path):
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    if not isinstance(cases, list):
        raise ValueError("case file must be a JSON list")
    seen = set()
    for i, c in enumerate(cases):
        for k in ("id", "prompt", "expect"):
            if k not in c:
                raise ValueError("case %d missing %r" % (i, k))
        if c["id"] in seen:
            raise ValueError("duplicate case id %r" % c["id"])
        seen.add(c["id"])
        if not isinstance(c["expect"], list):
            raise ValueError("case %r: expect must be a list" % c["id"])
        b = c.get("body")
        if b is not None:
            if not isinstance(b, dict):
                raise ValueError("case %r: body must be an object" % c["id"])
            for k in ("files", "evidence"):
                if not isinstance(b.get(k, []), list):
                    raise ValueError("case %r: body.%s must be a list" % (c["id"], k))
            for e in b.get("evidence", []):
                try:
                    re.compile(e)
                except re.error as ex:
                    raise ValueError("case %r: bad evidence regex %r: %s"
                                     % (c["id"], e, ex))
            em = b.get("evidence_min")
            if em is not None:
                if not isinstance(em, int) or isinstance(em, bool) \
                        or not 0 <= em <= len(b.get("evidence", [])):
                    raise ValueError(
                        "case %r: evidence_min must be an int in "
                        "[0, len(evidence)]" % c["id"])
    return cases


# ------------------------------------------------------------------ runner --
def default_runner(argv, cwd, timeout_s):
    """Run argv; return (rc, stdout, stderr). CLAUDE* env vars are stripped so
    a nested Claude Code session does not inherit the parent's context."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, cwd=cwd,
                           timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ds" % timeout_s
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


# ----------------------------------------------------------------- parsing --
def parse_stream(text):
    """Parse ``--output-format stream-json`` output into a probe record:
    {"invoked": [names in order], "declared": [names from SKILLS= line],
     "available": [slash commands the session listed], "reads": [Read paths
     attempted], "reads_failed": [{"path", "reason", "denied"} for Reads
     whose tool_result errored — permission denials flagged], "bash":
     [Bash commands], "texts": [every assistant text block],
     "cost_usd", "turns", "error"}."""
    rec = {"invoked": [], "declared": None, "available": [], "cost_usd": 0.0,
           "turns": 0, "error": None, "final_text": "", "reads": [],
           "reads_failed": [], "bash": [], "texts": []}
    pending_reads = {}  # tool_use id -> Read file_path, for result matching
    saw_result = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            rec["available"] = list(ev.get("slash_commands") or [])
        elif t == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use" and b.get("name") == "Skill":
                    name = (b.get("input") or {}).get("skill")
                    if name:
                        # plugin skills arrive as "plugin:skill" — keep the tail
                        rec["invoked"].append(name.split(":")[-1])
                elif b.get("type") == "tool_use" and b.get("name") == "Read":
                    p = (b.get("input") or {}).get("file_path")
                    if p:
                        rec["reads"].append(p)
                        if b.get("id"):
                            pending_reads[b["id"]] = p
                elif b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = (b.get("input") or {}).get("command")
                    if cmd:
                        rec["bash"].append(cmd)
                elif b.get("type") == "text":
                    rec["final_text"] = b.get("text", "")
                    rec["texts"].append(b.get("text", ""))
        elif t == "user":
            for b in (ev.get("message") or {}).get("content") or []:
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                p = pending_reads.get(b.get("tool_use_id"))
                if p is not None and b.get("is_error"):
                    txt = _result_text(b.get("content"))
                    rec["reads_failed"].append(
                        {"path": p, "reason": txt[:160],
                         "denied": bool(DENIED_RE.search(txt))})
        elif t == "result":
            saw_result = True
            rec["cost_usd"] = float(ev.get("total_cost_usd") or 0.0)
            rec["turns"] = int(ev.get("num_turns") or 0)
            if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                rec["error"] = "result subtype=%s: %s" % (
                    ev.get("subtype"), str(ev.get("result"))[:200])
            if not rec["final_text"] and isinstance(ev.get("result"), str):
                rec["final_text"] = ev["result"]
    if not saw_result and rec["error"] is None:
        rec["error"] = "no result event in stream output"
    rec["declared"] = parse_declared(rec["final_text"])
    return rec


def parse_declared(text):
    """Extract the SKILLS=… line into a list (NONE → [])."""
    m = SKILLS_LINE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).strip().strip("`").strip()
    if raw.upper().startswith("NONE"):
        return []
    return [s.strip().strip("`'\"") for s in raw.split(",") if s.strip()]


def parse_catalog_answer(text):
    """Extract {"skills": [...]} from a catalog-mode reply; tolerant of fences."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return None
    return [str(s).strip() for s in skills]


# ------------------------------------------------------------------ probes --
def stage_skills(catalog, project_dir):
    """Copy every catalog skill into project_dir/.claude/skills/<name>/."""
    dest_root = os.path.join(project_dir, ".claude", "skills")
    os.makedirs(dest_root, exist_ok=True)
    for name, _, path in catalog:
        dest = os.path.join(dest_root, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(path, dest)
    return dest_root


def native_argv(executable, model, prompt, budget_usd):
    return [executable, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--tools", "Skill", "--permission-mode", "dontAsk",
            "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd),
            "--append-system-prompt", PROBE_SYSTEM, prompt]


def body_argv(executable, model, prompt, budget_usd, tools):
    return [executable, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--tools", tools, "--permission-mode", "dontAsk",
            "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd),
            "--append-system-prompt", BODY_SYSTEM, prompt]


def staged_files_touched(rec):
    """Staged-skill-relative paths (``<skill>/<relpath>``) the probe READ,
    via Read file_paths or Bash command text; deduped, order kept. A Read
    whose tool_result errored (permission denial, missing file) is NOT a
    read — v3 counted attempts, so a denied reference registered as
    consulted. Bash touches stay attempt-level (no per-path result to
    match). Failed staged reads are listed by staged_files_failed()."""
    fail_n = {}
    for f in rec.get("reads_failed", []):
        fail_n[f["path"]] = fail_n.get(f["path"], 0) + 1
    reads = rec.get("reads", [])
    hits = []
    for p in reads:
        if reads.count(p) <= fail_n.get(p, 0):   # every attempt errored
            continue
        m = SKILL_PATH_RE.search(p)
        if m:
            hits.append(m.group(1).rstrip("/."))
    for cmd in rec.get("bash", []):
        for m in SKILL_PATH_RE.finditer(cmd):
            hits.append(m.group(1).rstrip("/."))
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def staged_files_failed(rec):
    """Failed Reads of staged files, as [{"file": <skill-relative>,
    "reason", "denied"}] — denied=True means the error text looks like a
    permission denial rather than e.g. a missing file."""
    out = []
    for f in rec.get("reads_failed", []):
        m = SKILL_PATH_RE.search(f["path"])
        if m:
            out.append({"file": m.group(1).rstrip("/."),
                        "reason": f["reason"], "denied": f["denied"]})
    return out


def catalog_argv(executable, model, prompt, budget_usd):
    return [executable, "-p", "--output-format", "json", "--model", model,
            "--tools", "", "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd), prompt]


def render_catalog(catalog):
    return "\n".join("- %s: %s" % (n, d) for n, d, _ in catalog)


def run_probe(case, mode, catalog, project_dir, runner, executable, model,
              timeout_s, budget_usd, distractor_names=frozenset(),
              body_tools="Skill,Read", arm=None, transcript_path=None):
    """Run one probe; return a record with fired skills and diagnostics.
    ``arm`` tags the result ("plain"/"staged") for --paired runs;
    ``transcript_path`` writes the full transcript there."""
    if mode in ("native", "body"):
        if mode == "native":
            argv = native_argv(executable, model, case["prompt"], budget_usd)
        else:
            argv = body_argv(executable, model, case["prompt"], budget_usd,
                             body_tools)
        rc, out, err = runner(argv, project_dir, timeout_s)
        rec = parse_stream(out)
        if rc != 0:
            rec["error"] = "rc=%d: %s" % (rc, (err or out)[-300:])
        fired = rec["invoked"]
    else:
        prompt = CATALOG_PROMPT.format(catalog=render_catalog(catalog),
                                       task=case["prompt"])
        argv = catalog_argv(executable, model, prompt, budget_usd)
        rc, out, err = runner(argv, project_dir, timeout_s)
        rec = {"invoked": [], "declared": None, "available": [], "cost_usd": 0.0,
               "turns": 0, "error": None, "final_text": ""}
        if rc != 0:
            rec["error"] = "rc=%d: %s" % (rc, (err or out)[-300:])
        else:
            try:
                data = json.loads(out)
                rec["cost_usd"] = float(data.get("total_cost_usd") or 0.0)
                rec["turns"] = int(data.get("num_turns") or 0)
                rec["final_text"] = data.get("result") or ""
                if data.get("is_error"):
                    rec["error"] = "cli error: %s" % str(data.get("result"))[:200]
            except ValueError:
                rec["error"] = "non-JSON output: %r" % out[:200]
        ans = parse_catalog_answer(rec["final_text"])
        if ans is None and rec["error"] is None:
            rec["error"] = "unparseable answer: %r" % rec["final_text"][:200]
        fired = ans or []
    ours = {n for n, _, _ in catalog}
    # dedupe, keep order
    seen, fired_u = set(), []
    for f in fired:
        if f not in seen:
            seen.add(f)
            fired_u.append(f)
    res = {"id": case["id"], "prompt": case["prompt"], "expect": list(case["expect"]),
           "fired": [f for f in fired_u if f in ours],
           "distractors": [f for f in fired_u if f in distractor_names],
           "foreign": [f for f in fired_u
                       if f not in ours and f not in distractor_names],
           "declared": rec.get("declared"), "error": rec.get("error"),
           "cost_usd": rec.get("cost_usd", 0.0), "turns": rec.get("turns", 0),
           "available": rec.get("available", []), "model": model, "arm": arm}
    if mode == "body":
        spec = case.get("body") or {}
        exp_files = list(spec.get("files") or [])
        exp_ev = list(spec.get("evidence") or [])
        transcript = "\n".join(t for t in rec.get("texts", []) if t) \
            or rec.get("final_text", "")
        files_read = staged_files_touched(rec)
        res["body"] = {
            "files_read": files_read,
            "files_failed": staged_files_failed(rec),
            "files_expected": exp_files,
            "files_hit": [f for f in exp_files if f in files_read],
            "evidence_expected": exp_ev,
            "evidence_min": spec.get("evidence_min", len(exp_ev)),
            "evidence_hit": [e for e in exp_ev
                             if re.search(e, transcript, re.I | re.S)],
            "transcript_chars": len(transcript),
            # kept so a missed evidence marker can be diagnosed from the JSON
            "transcript_tail": transcript[-4000:],
        }
    if transcript_path:
        try:
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write("case: %s\nmodel: %s\narm: %s\nfired: %s\n"
                        "distractors: %s\nforeign: %s\nerror: %s\n"
                        "reads: %s\nreads_failed: %s\nbash: %s\n"
                        % (case["id"], model, arm, res["fired"],
                           res["distractors"], res["foreign"], res["error"],
                           rec.get("reads", []), rec.get("reads_failed", []),
                           rec.get("bash", [])))
                f.write("\n--- transcript ---\n")
                f.write("\n\n".join(t for t in rec.get("texts", []) if t)
                        or rec.get("final_text", ""))
            res["transcript_path"] = transcript_path
        except OSError as e:
            res["transcript_path"] = "unwritable: %s" % e
    return res


# ----------------------------------------------------------------- metrics --
def score(results, catalog_names):
    """Aggregate probe results into per-skill and overall metrics.

    A result is *exact* when set(fired) == set(expect); it is a *hit*
    (all-expected-fired) when expect ⊆ fired for positives / nothing fired
    for negatives. Foreign fires are reported but never penalised. Errored
    probes are excluded from the metrics and counted separately.
    ``per_case`` aggregates repeats into rates — the readable unit when a
    probe model is noisy at n=1."""
    per = {n: {"tp": 0, "fp": 0, "fn": 0} for n in catalog_names}
    per_case = {}
    exact = 0
    n_ok = 0
    n_err = 0
    neg_total = neg_false_fire = 0
    cost = 0.0
    distractor_fires = displaced = 0
    body_n = body_followed = 0
    bf_hit = bf_tot = be_hit = be_tot = 0
    for r in results:
        cost += r.get("cost_usd") or 0.0
        pc = per_case.setdefault(r["id"], {"expect": list(r["expect"]), "n": 0,
                                           "err": 0, "exact": 0, "hit": 0,
                                           "displaced": 0,
                                           "distractor_fired": 0})
        if r.get("error"):
            n_err += 1
            pc["err"] += 1
            continue
        n_ok += 1
        pc["n"] += 1
        fired, expect = set(r["fired"]), set(r["expect"])
        if fired == expect:
            exact += 1
            pc["exact"] += 1
        if (expect <= fired) if expect else (not fired):
            pc["hit"] += 1
        if not expect:
            neg_total += 1
            if fired:
                neg_false_fire += 1
        d_fired = r.get("distractors") or []
        distractor_fires += len(d_fired)
        if d_fired:
            pc["distractor_fired"] += 1
        if d_fired and expect - fired:
            displaced += 1
            pc["displaced"] += 1
        b = r.get("body")
        if b is not None:
            body_n += 1
            bf_hit += len(b["files_hit"])
            bf_tot += len(b["files_expected"])
            be_hit += len(b["evidence_hit"])
            be_tot += len(b["evidence_expected"])
            if (fired == expect
                    and len(b["files_hit"]) == len(b["files_expected"])
                    and len(b["evidence_hit"]) >=
                    b.get("evidence_min", len(b["evidence_expected"]))):
                body_followed += 1
        for n in catalog_names:
            if n in fired and n in expect:
                per[n]["tp"] += 1
            elif n in fired:
                per[n]["fp"] += 1
            elif n in expect:
                per[n]["fn"] += 1
    for pc in per_case.values():
        pc["exact_rate"] = pc["exact"] / pc["n"] if pc["n"] else None
        pc["hit_rate"] = pc["hit"] / pc["n"] if pc["n"] else None
    for n, d in per.items():
        tp, fp, fn = d["tp"], d["fp"], d["fn"]
        d["precision"] = tp / (tp + fp) if tp + fp else None
        d["recall"] = tp / (tp + fn) if tp + fn else None
    return {"per_skill": per, "per_case": per_case,
            "exact": exact, "n_ok": n_ok, "n_err": n_err,
            "exact_rate": exact / n_ok if n_ok else None,
            "neg_total": neg_total, "neg_false_fire": neg_false_fire,
            "cost_usd": cost,
            "distractor_fires": distractor_fires, "displaced": displaced,
            "body": None if not body_n else {
                "n": body_n, "followed": body_followed,
                "files_hit": bf_hit, "files_expected": bf_tot,
                "evidence_hit": be_hit, "evidence_expected": be_tot}}


def fmt_rate(x):
    return "  n/a" if x is None else "%4.0f%%" % (100 * x)


def render_report(results, metrics, catalog_names, mode, model,
                  distractor_names=()):
    lines = ["# skill trigger eval — mode=%s model=%s" % (mode, model), ""]
    lines.append("probes: %d ok, %d errored, exact-match %s, negatives false-fire %d/%d, cost $%.3f"
                 % (metrics["n_ok"], metrics["n_err"], fmt_rate(metrics["exact_rate"]).strip(),
                    metrics["neg_false_fire"], metrics["neg_total"], metrics["cost_usd"]))
    lines += ["", "| skill | recall | precision | tp | fp | fn |", "|---|---|---|---|---|---|"]
    for n in catalog_names:
        d = metrics["per_skill"][n]
        lines.append("| %s | %s | %s | %d | %d | %d |" % (
            n, fmt_rate(d["recall"]).strip(), fmt_rate(d["precision"]).strip(),
            d["tp"], d["fp"], d["fn"]))
    pc = metrics.get("per_case") or {}
    if any(d["n"] + d["err"] > 1 for d in pc.values()):
        lines += ["", "per-case fire rates (all-expected-fired vs exact; "
                  "negatives: hit = nothing fired):",
                  "| case | runs | fired | exact | err |", "|---|---|---|---|---|"]
        for cid, d in pc.items():   # insertion order == case order
            lines.append("| %s | %d | %d (%s) | %d (%s) | %d |" % (
                cid, d["n"], d["hit"], fmt_rate(d["hit_rate"]).strip(),
                d["exact"], fmt_rate(d["exact_rate"]).strip(), d["err"]))
    dcol = bool(distractor_names)
    head = "| case | expect | fired |" + (" staged-distractor |" if dcol else "") \
        + " foreign | ok |"
    lines += ["", head, "|---|---|---|" + ("---|" if dcol else "") + "---|---|"]
    for r in results:
        if r.get("error"):
            status = "ERR: " + r["error"][:80]
        else:
            status = "yes" if set(r["fired"]) == set(r["expect"]) else "NO"
        cells = [r["id"], ",".join(r["expect"]) or "—", ",".join(r["fired"]) or "—"]
        if dcol:
            cells.append(",".join(r.get("distractors") or []) or "—")
        cells += [",".join(r["foreign"]) or "—", status]
        lines.append("| " + " | ".join(cells) + " |")
    if mode == "body":
        b = metrics.get("body")
        if b:
            lines += ["", "body-following: %d/%d cases fully followed; "
                      "bundled files read %d/%d; evidence matched %d/%d"
                      % (b["followed"], b["n"], b["files_hit"], b["files_expected"],
                         b["evidence_hit"], b["evidence_expected"])]
        lines += ["", "| case | fired | staged files read | failed reads | files | evidence | chars |",
                  "|---|---|---|---|---|---|---|"]
        for r in results:
            bb = r.get("body") or {}
            fails = ", ".join("%s%s" % (f["file"], " (denied)" if f["denied"] else "")
                              for f in bb.get("files_failed") or [])
            ev_min = bb.get("evidence_min", len(bb.get("evidence_expected") or []))
            ev_cell = "%d/%d" % (len(bb.get("evidence_hit") or []),
                                 len(bb.get("evidence_expected") or []))
            if ev_min != len(bb.get("evidence_expected") or []):
                ev_cell += " (min %d)" % ev_min
            lines.append("| %s | %s | %s | %s | %d/%d | %s | %d |" % (
                r["id"], ",".join(r["fired"]) or "—",
                ", ".join(bb.get("files_read") or []) or "—", fails or "—",
                len(bb.get("files_hit") or []), len(bb.get("files_expected") or []),
                ev_cell, bb.get("transcript_chars", 0)))
    if distractor_names:
        fired_d = {}
        for r in results:
            for d in r.get("distractors") or []:
                fired_d[d] = fired_d.get(d, 0) + 1
        lines += ["", "staged distractors (%d): %s"
                  % (len(distractor_names), ", ".join(sorted(distractor_names)))]
        if fired_d:
            lines.append("staged-distractor fires: " + ", ".join(
                "%s×%d" % (k, v) for k, v in sorted(fired_d.items())))
        lines.append("displacement (expected skill missing while a staged "
                     "distractor fired): %d probe(s)" % metrics.get("displaced", 0))
    avail = set()
    for r in results:
        avail.update(r.get("available") or [])
    host = sorted(a for a in avail
                  if a not in catalog_names and a not in set(distractor_names))
    if host:
        lines += ["", "host distractor skills present: " + ", ".join(host)]
    return "\n".join(lines)


def render_model_comparison(metrics_by_model, catalog_names, models):
    lines = ["# per-model comparison", "",
             "| skill | " + " | ".join("%s recall" % m for m in models) + " |",
             "|---|" + "---|" * len(models)]
    for n in catalog_names:
        row = [fmt_rate(metrics_by_model[m]["per_skill"][n]["recall"]).strip()
               for m in models]
        lines.append("| %s | %s |" % (n, " | ".join(row)))
    lines += ["", "| metric | " + " | ".join(models) + " |",
              "|---|" + "---|" * len(models)]
    rows = [
        ("exact-match", lambda mm: fmt_rate(mm["exact_rate"]).strip()),
        ("neg false-fire", lambda mm: "%d/%d" % (mm["neg_false_fire"], mm["neg_total"])),
        ("errored", lambda mm: str(mm["n_err"])),
        ("displaced", lambda mm: str(mm.get("displaced", 0))),
        ("cost", lambda mm: "$%.3f" % mm["cost_usd"]),
    ]
    for label, f in rows:
        lines.append("| %s | %s |" % (label, " | ".join(f(metrics_by_model[m])
                                                        for m in models)))
    return "\n".join(lines)


def paired_verdicts(plain_metrics, staged_metrics):
    """Per positive case, compare plain vs staged fire counts and name the
    failure mode. Returns [{"id", "expect", "plain": "h/n", "staged": "h/n",
    "gap", "verdict"}]. Verdicts: ok (no drop), noise? (drop of 1 — re-run
    before acting), SUPPRESSED (drop ≥2, staged distractor never fired on
    the case: the selector fired neither contender), DISPLACED (drop ≥2
    with the distractor firing while yours went missing)."""
    out = []
    pp, sp = plain_metrics["per_case"], staged_metrics["per_case"]
    for cid, p in pp.items():
        if not p["expect"] or cid not in sp:
            continue
        s = sp[cid]
        gap = p["hit"] - s["hit"]
        if gap >= 2:
            verdict = "DISPLACED" if s["displaced"] else "SUPPRESSED"
        elif gap == 1:
            verdict = "noise?"
        else:
            verdict = "ok"
        out.append({"id": cid, "expect": p["expect"],
                    "plain": "%d/%d" % (p["hit"], p["n"]),
                    "staged": "%d/%d" % (s["hit"], s["n"]),
                    "staged_distractor_fires": s["distractor_fired"],
                    "gap": gap, "verdict": verdict})
    return out


def render_paired(verdicts, model):
    lines = ["# paired suppression diagnostic — model=%s" % model,
             "(fired = all expected skills fired; drop ≥2 with no distractor "
             "fire on the case = suppression)", "",
             "| case | plain fired | staged fired | gap | distractor fired | verdict |",
             "|---|---|---|---|---|---|"]
    for v in verdicts:
        lines.append("| %s | %s | %s | %+d | %d run(s) | %s |" % (
            v["id"], v["plain"], v["staged"], -v["gap"],
            v["staged_distractor_fires"], v["verdict"]))
    return "\n".join(lines)


# ------------------------------------------------------------------ canary --
def load_canary(path):
    """Load and validate a canary file: a sentinel dict or list of them.
    Required: case, min_rate. Defaults: model=sonnet, repeats=4,
    max_rate=1.0, mode=native."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("canary file must be a sentinel object or list")
    out = []
    for i, s in enumerate(data):
        if not isinstance(s, dict) or "case" not in s or "min_rate" not in s:
            raise ValueError("canary sentinel %d needs 'case' and 'min_rate'" % i)
        rep = s.get("repeats", 4)
        lo, hi = s["min_rate"], s.get("max_rate", 1.0)
        if not isinstance(rep, int) or rep < 1:
            raise ValueError("canary sentinel %d: repeats must be int ≥1" % i)
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))
                and 0 <= lo <= hi <= 1):
            raise ValueError("canary sentinel %d: need 0 ≤ min_rate ≤ "
                             "max_rate ≤ 1" % i)
        mode = s.get("mode", "native")
        if mode not in ("native", "catalog", "body"):
            raise ValueError("canary sentinel %d: bad mode %r" % (i, mode))
        out.append({"case": s["case"], "model": s.get("model", "sonnet"),
                    "repeats": rep, "min_rate": float(lo),
                    "max_rate": float(hi), "mode": mode})
    return out


def run_canary(sentinels, cases, catalog, project_dir, runner, executable,
               timeout_s, budget_usd, body_tools, concurrency, quiet):
    """Run each sentinel case ×repeats; band-check the all-expected-fired
    rate. Returns (exit_code, records): 0 all in band, 1 drift, 2
    inconclusive (a sentinel had zero non-errored runs or an unknown
    case id)."""
    by_id = {c["id"]: c for c in cases}
    records = []
    code = 0
    for s in sentinels:
        case = by_id.get(s["case"])
        if case is None:
            print("canary: unknown case id %r" % s["case"], file=sys.stderr)
            return 2, records
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, concurrency)) as ex:
            futs = [ex.submit(run_probe, case, s["mode"], catalog, project_dir,
                              runner, executable, s["model"], timeout_s,
                              budget_usd, body_tools=body_tools)
                    for _ in range(s["repeats"])]
            results = [f.result() for f in futs]
        m = score(results, [n for n, _, _ in catalog])
        pc = m["per_case"][s["case"]]
        rec = dict(s, n_ok=pc["n"], n_err=pc["err"], hit=pc["hit"],
                   rate=pc["hit_rate"], cost_usd=m["cost_usd"],
                   results=results)
        if pc["n"] == 0:
            rec["status"] = "INCONCLUSIVE"
            code = 2
        elif s["min_rate"] <= pc["hit_rate"] <= s["max_rate"]:
            rec["status"] = "OK"
        else:
            rec["status"] = "DRIFT"
            if code == 0:
                code = 1
        records.append(rec)
        if not quiet:
            print("CANARY %-12s %-8s %s: fired %d/%d (errs %d) band "
                  "[%.2f, %.2f] -> %s" % (
                      s["case"], s["model"], s["mode"], pc["hit"], pc["n"],
                      pc["err"], s["min_rate"], s["max_rate"], rec["status"]),
                  file=sys.stderr)
    return code, records


# -------------------------------------------------------------------- main --
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cases")
    ap.add_argument("--skills", action="append", required=True,
                    help="skill dir or directory of skill dirs (repeatable)")
    ap.add_argument("--mode", choices=("native", "catalog", "body"), default="native")
    ap.add_argument("--model", default="sonnet",
                    help="probe model, or comma-separated list for a per-model comparison")
    ap.add_argument("--executable", default="claude")
    ap.add_argument("--distractors", action="append", default=[],
                    help="directory tree of foreign skills staged as controlled "
                         "distractors (repeatable, recursive, lenient)")
    ap.add_argument("--n-distractors", type=int, default=-1,
                    help="deterministic sample size from the distractor pool (-1 = all)")
    ap.add_argument("--distractor-seed", type=int, default=0)
    ap.add_argument("--body-tools", default="Skill,Read",
                    help="--tools value for body-mode probes")
    ap.add_argument("--paired", action="store_true",
                    help="run every probe with AND without the staged "
                         "distractors and print a per-case suppression table "
                         "(requires --distractors)")
    ap.add_argument("--transcripts",
                    help="directory to write full per-probe transcripts into")
    ap.add_argument("--canary",
                    help="canary sentinel file: run frozen case(s) against "
                         "stored acceptance bands; exit 0 in-band / 1 drift "
                         "/ 2 inconclusive")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=150.0)
    ap.add_argument("--budget-usd", type=float, default=0.5, help="per-probe cap")
    ap.add_argument("--only", help="comma-separated case ids to run")
    ap.add_argument("--json", help="write raw results + metrics here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        catalog = load_catalog(args.skills)
        cases = load_cases(args.cases)
    except (OSError, ValueError) as e:
        print("trigger-eval: %s" % e, file=sys.stderr)
        return 2
    if not catalog:
        print("trigger-eval: no SKILL.md found under %s" % args.skills, file=sys.stderr)
        return 2
    names = [n for n, _, _ in catalog]
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    unknown = sorted({e for c in cases for e in c["expect"]} - set(names))
    if unknown:
        print("trigger-eval: cases expect unknown skills %s" % unknown, file=sys.stderr)
        return 2
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    if not models:
        print("trigger-eval: --model is empty", file=sys.stderr)
        return 2

    if args.canary:
        try:
            sentinels = load_canary(args.canary)
        except (OSError, ValueError) as e:
            print("trigger-eval: canary: %s" % e, file=sys.stderr)
            return 2
        tmp = tempfile.mkdtemp(prefix="trigger-eval-")
        try:
            stage_skills(catalog, tmp)
            code, records = run_canary(
                sentinels, cases, catalog, tmp, default_runner,
                args.executable, args.timeout, args.budget_usd,
                args.body_tools, args.concurrency, args.quiet)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"canary": records, "exit": code}, f, indent=1)
        return code

    distractors = []
    if args.distractors:
        try:
            pool = load_catalog(args.distractors, lenient=True, recursive=True)
        except OSError as e:
            print("trigger-eval: %s" % e, file=sys.stderr)
            return 2
        distractors = pick_distractors(pool, names, args.n_distractors,
                                       args.distractor_seed)
    dnames = frozenset(n for n, _, _ in distractors)
    if args.paired and not distractors:
        print("trigger-eval: --paired requires --distractors", file=sys.stderr)
        return 2
    if args.transcripts:
        os.makedirs(args.transcripts, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="trigger-eval-")
    tmp_plain = tempfile.mkdtemp(prefix="trigger-eval-plain-") if args.paired else None
    try:
        stage_skills(catalog + distractors, tmp)
        if args.paired:
            stage_skills(catalog, tmp_plain)
            arms = [("plain", tmp_plain, frozenset()), ("staged", tmp, dnames)]
        else:
            arms = [(None, tmp, dnames)]
        jobs = []
        for m in models:
            for c in cases:
                for k in range(args.repeats):
                    for arm, proj, dn in arms:
                        tp = None
                        if args.transcripts:
                            base = "-".join(x for x in (m, arm, c["id"], str(k)) if x)
                            tp = os.path.join(args.transcripts, base + ".txt")
                        jobs.append((c, m, arm, proj, dn, tp))
        results = [None] * len(jobs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futs = {ex.submit(run_probe, c, args.mode, catalog, proj, default_runner,
                              args.executable, m, args.timeout, args.budget_usd,
                              distractor_names=dn, body_tools=args.body_tools,
                              arm=arm, transcript_path=tp): i
                    for i, (c, m, arm, proj, dn, tp) in enumerate(jobs)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                results[i] = fut.result()
                if not args.quiet:
                    r = results[i]
                    mark = "ERR" if r["error"] else ("ok " if set(r["fired"]) == set(r["expect"]) else "NO ")
                    print("[%s] %-8s %-6s %-12s expect=%s fired=%s distractor=%s foreign=%s $%.3f" % (
                        mark, r["model"], r.get("arm") or "-", r["id"], r["expect"],
                        r["fired"], r["distractors"], r["foreign"], r["cost_usd"]),
                        file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if tmp_plain:
            shutil.rmtree(tmp_plain, ignore_errors=True)

    metrics_by_model = {}
    metrics_by_model_arm = {}
    paired_by_model = {}
    for m in models:
        rs = [r for r in results if r["model"] == m]
        metrics_by_model[m] = score(rs, names)
        if args.paired:
            arm_metrics = {}
            for arm in ("plain", "staged"):
                ars = [r for r in rs if r.get("arm") == arm]
                arm_metrics[arm] = score(ars, names)
                print(render_report(ars, arm_metrics[arm], names, args.mode,
                                    "%s arm=%s" % (m, arm),
                                    dnames if arm == "staged" else frozenset()))
                print()
            metrics_by_model_arm[m] = arm_metrics
            paired_by_model[m] = paired_verdicts(arm_metrics["plain"],
                                                 arm_metrics["staged"])
            print(render_paired(paired_by_model[m], m))
        else:
            print(render_report(rs, metrics_by_model[m], names, args.mode, m, dnames))
        if len(models) > 1:
            print()
    if len(models) > 1:
        print(render_model_comparison(metrics_by_model, names, models))
    metrics = score(results, names)
    if args.json:
        out = {"mode": args.mode, "model": args.model, "models": models,
               "distractors": sorted(dnames), "paired": args.paired,
               "results": results,
               "metrics": metrics, "metrics_by_model": metrics_by_model}
        if args.paired:
            out["metrics_by_model_arm"] = metrics_by_model_arm
            out["paired_by_model"] = paired_by_model
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    if metrics["n_err"] == len(results):
        return 2
    return 0 if metrics["exact"] == metrics["n_ok"] and metrics["n_err"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
