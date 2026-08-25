#!/usr/bin/env python3
"""kv_reuse_model — reference model of qwen36 prefix/KV reuse (round 28, E3).

Three things, all offline:

1. Geometry: what a position costs and what a DeltaNet snapshot costs for the
   shipping Qwen3.6-35B-A3B (numbers read from config.json on the NUC).
2. StateModel: the reuse DECISION of nuc/kv_reuse/qwen36-prefix-reuse.patch,
   line for line (strict continuation -> deepest snapshot at/below the LCP ->
   cold), so scenarios can be checked here and pinned in the C unit test with
   the same expectations.
3. Projection: per-turn prefill time for real prompt sequences (nuc-mini,
   Hermes) under no reuse / strict-only / snapshot policies, on the E1 curve.

Tokenization for scenarios comes from prompt_budget (the model's own
tokenizer.json + the byte-identical adapter copy); this module stays importable
without it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# --- geometry -----------------------------------------------------------------
QWEN36 = {
    "n_layers": 40, "attn_layers": 10, "kv_heads": 2, "head_dim": 256,
    "dn_layers": 30, "dn_vheads": 32, "dn_kheads": 16, "dn_kdim": 128, "dn_vdim": 128,
    "dn_convk": 4,
}


def kv_bytes_per_token(g=QWEN36):
    """fp32 K and V rows of every attention layer for one position."""
    return 2 * g["attn_layers"] * g["kv_heads"] * g["head_dim"] * 4


def dn_snapshot_bytes(g=QWEN36):
    """One DeltaNet snapshot: recurrent S[h]=[kdim,vdim] per value head plus the
    conv ring [conv_dim, convk-1], for every linear-attention layer. Fixed size:
    it does not grow with the context, which is what makes a snapshot at an
    arbitrary position affordable."""
    rec = g["dn_vheads"] * g["dn_kdim"] * g["dn_vdim"]
    conv_dim = 2 * g["dn_kheads"] * g["dn_kdim"] + g["dn_vheads"] * g["dn_vdim"]
    conv = conv_dim * (g["dn_convk"] - 1)
    return g["dn_layers"] * (rec + conv) * 4


# --- the decision -------------------------------------------------------------
class StateModel:
    """Mirror of prepare_request_state()/q36_snap_take() in the patch.

    fed: token ids the state was built from. snaps: {slot: pos}. Snapshot slot
    0 is the system boundary, 1 the prompt end. `enabled=False` models
    Q36_PREFIX=0."""

    SYS, PROMPT_END = 0, 1

    def __init__(self, enabled=True):
        self.fed = []
        self.snaps = {}
        self.enabled = enabled
        self.log = []

    def lcp(self, ids):
        n = min(len(self.fed), len(ids) - 1)
        i = 0
        while i < n and self.fed[i] == ids[i]:
            i += 1
        return i

    def prepare(self, ids):
        """Return (reuse, lcp) and mutate state the way the engine would."""
        reuse, lcp = 0, 0
        if self.enabled:
            if 0 < len(self.fed) < len(ids) and ids[:len(self.fed)] == self.fed:
                reuse = len(self.fed)               # strict continuation
            else:
                lcp = self.lcp(ids)
                usable = [p for p in self.snaps.values() if 0 < p <= lcp]
                if usable:
                    reuse = max(usable)             # deepest snapshot at/below the LCP
                    self.fed = self.fed[:reuse]
        if not reuse:
            self.fed, self.snaps = [], {}
        self.snaps = {k: p for k, p in self.snaps.items() if p <= reuse}
        return reuse, lcp

    def feed(self, ids, pos0):
        assert pos0 == len(self.fed), (pos0, len(self.fed))
        self.fed = self.fed[:pos0] + list(ids)

    def snap(self, slot, pos):
        if pos <= 0 or pos != len(self.fed):
            self.snaps.pop(slot, None)
            return False
        self.snaps[slot] = pos
        return True

    def serve(self, prompt_ids, reply_ids, prefix_hint_pos=0, stable_hint_pos=0, min_cut=64):
        """One serve_one(): decide, split the prefill at the system boundary
        (hint or LCP plan) and at the stable boundary (hint; else the prompt
        end) for the two snapshots, prefill, then feed the reply (decode).
        Returns tokens prefilled."""
        np_ = len(prompt_ids)
        reuse, lcp = self.prepare(prompt_ids)
        cut = pe_cut = 0
        if self.enabled:
            if prefix_hint_pos and min_cut <= prefix_hint_pos < np_ and prefix_hint_pos > reuse:
                cut = prefix_hint_pos
            if not cut and not reuse and min_cut <= lcp < np_:
                cut = lcp
            if self.snaps.get(self.SYS) == cut:
                cut = 0
            if reuse < stable_hint_pos < np_ and stable_hint_pos > cut:
                pe_cut = stable_hint_pos
        start = reuse
        at = reuse
        if cut > at:
            self.feed(prompt_ids[at:cut], at); at = cut
            self.snap(self.SYS, at)
        if pe_cut > at:
            self.feed(prompt_ids[at:pe_cut], at); at = pe_cut
            self.snap(self.PROMPT_END, at)
        self.feed(prompt_ids[at:], at)
        if self.enabled and not pe_cut:
            self.snap(self.PROMPT_END, np_)
        self.feed(reply_ids, np_)
        self.log.append({"np": np_, "reuse": start, "prefilled": np_ - start,
                         "sys_cut": cut, "stable_cut": pe_cut})
        return np_ - start


# --- E1 timing ----------------------------------------------------------------
def prefill_seconds(np_, start):
    """Cost of prefilling positions [start, np) on the E1 curve: the convex
    TTFT difference plus the fixed request overhead."""
    from prompt_budget import ttft_projected
    overhead = 2.4
    if start <= 0:
        return ttft_projected(np_)
    return overhead + max(0.0, ttft_projected(np_) - ttft_projected(start))


def decode_tok_s(kv_positions):
    """E1 decode series 5.3 @300, 4.78 @1k, 3.32 @4k, linear extrapolation,
    floored at 1.0 tok/s."""
    pts = [(300, 5.3), (1000, 4.78), (4000, 3.32)]
    if kv_positions <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if kv_positions <= x1:
            return y0 + (y1 - y0) * (kv_positions - x0) / (x1 - x0)
    x1, y1 = pts[-1]
    slope = (pts[-1][1] - pts[-2][1]) / (pts[-1][0] - pts[-2][0])
    return max(1.0, y1 + slope * (kv_positions - x1))


# --- scenarios ----------------------------------------------------------------
def tokenizer():
    from tokenizers import Tokenizer
    return Tokenizer.from_file(os.path.join(HERE, "tokenizer-qwen36.json"))


def system_boundary(text):
    """Byte offset of the first user turn: the server-side prefix hint."""
    i = text.find("<|im_start|>user")
    return i if i > 0 else 0


ASSISTANT_HEAD = "<|im_start|>assistant\n"


def stable_boundary(text):
    """Byte offset just after the last assistant header: the point up to which
    the next turn's re-rendered history still matches this prompt (the
    generation suffix after it is omitted from history)."""
    i = text.rfind(ASSISTANT_HEAD)
    return i + len(ASSISTANT_HEAD) if i > 0 else 0


def token_prefix_stable(tok, whole, part):
    """Does tokenizing `part` give a token prefix of tokenizing `whole`?
    (`whole` must start with `part`.) The hint is accepted by the engine only
    when this holds."""
    assert whole.startswith(part)
    a, b = tok.encode(part).ids, tok.encode(whole).ids
    return b[:len(a)] == a, len(a), len(b)


def agent_session(prompts, replies, hint=True, policy="snapshot", min_cut=64):
    """Run a sequence of (prompt_text, raw_reply_text) turns through the model.
    policy: 'none' | 'strict' | 'snapshot'. Returns per-turn records with
    prefilled tokens and projected seconds."""
    tok = tokenizer()
    sm = StateModel(enabled=(policy != "none"))
    out = []
    for p, r in zip(prompts, replies):
        pids = tok.encode(p).ids
        rids = tok.encode(r).ids
        hp = sp = 0
        if hint and policy == "snapshot":
            cut = system_boundary(p)
            ok, n_part, _ = token_prefix_stable(tok, p, p[:cut]) if cut else (False, 0, 0)
            hp = n_part if ok else 0
            st = stable_boundary(p)
            ok, n_part, _ = token_prefix_stable(tok, p, p[:st]) if st else (False, 0, 0)
            sp = n_part if ok else 0
        if policy == "strict":
            # strict-only: no snapshots ever taken (kimi_k3-style engine)
            reuse, _ = sm.prepare(pids)
            sm.snaps = {}
            sm.feed(pids[reuse:], reuse)
            sm.snaps = {}
            sm.feed(rids, len(pids))
            prefilled = len(pids) - reuse
        else:
            prefilled = sm.serve(pids, rids, prefix_hint_pos=hp, stable_hint_pos=sp, min_cut=min_cut)
            reuse = len(pids) - prefilled
        secs = prefill_seconds(len(pids), reuse)
        out.append({"np": len(pids), "reuse": reuse, "prefilled": prefilled,
                    "prefill_s": round(secs, 1),
                    "decode_tok_s": round(decode_tok_s(len(pids)), 2)})
    return out


def main(argv):
    print(f"KV bytes/token: {kv_bytes_per_token():,}  (40 KB)")
    print(f"DeltaNet snapshot: {dn_snapshot_bytes() / 1e6:.1f} MB")
    for n in (546, 1000, 4000, 26483):
        print(f"  prefix {n:>6} tok: KV {n * kv_bytes_per_token() / 1e6:8.1f} MB"
              f"  + snapshot {dn_snapshot_bytes() / 1e6:.1f} MB")
    if len(argv) > 1:
        sc = json.load(open(argv[1]))
        for policy in ("none", "strict", "snapshot"):
            rows = agent_session(sc["prompts"], sc["replies"], policy=policy)
            tot = sum(r["prefill_s"] for r in rows)
            print(f"{policy:>9}: " + "  ".join(f"t{i + 1} {r['reuse']}/{r['np']} {r['prefill_s']}s"
                                              for i, r in enumerate(rows)) + f"  | total prefill {tot:.0f}s")


if __name__ == "__main__":
    main(sys.argv)
