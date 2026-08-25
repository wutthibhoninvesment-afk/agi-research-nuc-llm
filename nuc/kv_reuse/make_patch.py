#!/usr/bin/env python3
"""Generate the qwen36 prefix-reuse patch from the pristine colibri v1.7.0
qwen36.c (upstream/qwen36.c, md5 56fe53a65aa6412036a1941b111505e3).

Every edit is an asserted-unique string replacement (process rule 8), so the
patch is reproducible and a drifted upstream fails loudly instead of silently
interleaving. Output: patched/qwen36.c + qwen36-prefix-reuse.patch (diff -u).
"""
import hashlib, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "upstream", "qwen36.c")
DST_DIR = os.path.join(HERE, "patched")
DST = os.path.join(DST_DIR, "qwen36.c")
PATCH = os.path.join(HERE, "qwen36-prefix-reuse.patch")
UPSTREAM_MD5 = "56fe53a65aa6412036a1941b111505e3"


def rep(s, old, new, count=1):
    assert len(old) > 0, "empty old"
    n = s.count(old)
    assert n == count, f"expected {count} occurrence(s), found {n}: {old[:80]!r}"
    return s.replace(old, new)


def build(src_text):
    s = src_text

    # 1. include the shared record after json.h
    s = rep(s,
            '#include "json.h"   /* tokenizer.json parsing (reuse minimal parser) */\n',
            '#include "json.h"   /* tokenizer.json parsing (reuse minimal parser) */\n'
            '#include "kv_prefix.h"   /* KV/state prefix reuse (shared with kimi_k3/inkling) */\n')

    # 2. snapshot type + Model fields
    s = rep(s,
            "typedef struct { Slot *slots; int n, cap; } LCache;\n",
            "typedef struct { Slot *slots; int n, cap; } LCache;\n"
            "\n"
            "/* A snapshot of the DeltaNet state (recurrent S[h] + conv ring of every\n"
            " * linear-attention layer) as it stood after feeding fed[0..pos). Fixed\n"
            " * size (~63 MB for the shipping geometry), independent of the context.\n"
            " * Slot 0 = the system-prefix boundary (gateway hint, or the LCP of two\n"
            " * successive fresh prompts); slot 1 = the end of the last prompt. */\n"
            "#define Q36_SNAP_SYS 0\n"
            "#define Q36_SNAP_PROMPT_END 1\n"
            "#define Q36_SNAP_N 2\n"
            "typedef struct { int pos; float **rec; float **conv; } Q36Snap;\n")
    s = rep(s,
            "    float **K, **V; int kv_len, max_t, kv_cap;\n",
            "    float **K, **V; int kv_len, max_t, kv_cap;\n"
            "    /* PREFIX REUSE (kv_prefix.h). kvp.fed[0..len) are the token ids the\n"
            "     * current state was built from. The 10 attention layers keep K/V rows\n"
            "     * per position, which stay valid for every position whose id still\n"
            "     * matches the next prompt; the 30 DeltaNet layers keep a recurrent\n"
            "     * state that cannot be rewound, so partial reuse restores one of the\n"
            "     * snapshots below instead. See prepare_request_state(). */\n"
            "    kv_prefix kvp;\n"
            "    Q36Snap snap[Q36_SNAP_N];\n")

    # 3. attention rows are laid out with the ALLOCATED stride, not the request's
    #    max_t: a later request with a smaller max_t must find the rows a
    #    previous one wrote (the two agreed before only because every request
    #    started from position 0).
    s = rep(s,
            "        memcpy(m->K[layer] + ((int64_t)kvh*m->max_t + t)*kvd, k + (int64_t)s*KV*kvd + kvh*kvd, kvd*sizeof(float));\n"
            "        memcpy(m->V[layer] + ((int64_t)kvh*m->max_t + t)*kvd, vv + (int64_t)s*KV*kvd + kvh*kvd, kvd*sizeof(float));\n",
            "        /* stride = kv_cap (the allocation), not max_t: reused rows were\n"
            "         * written by an earlier request that may have had a different max_t */\n"
            "        memcpy(m->K[layer] + ((int64_t)kvh*m->kv_cap + t)*kvd, k + (int64_t)s*KV*kvd + kvh*kvd, kvd*sizeof(float));\n"
            "        memcpy(m->V[layer] + ((int64_t)kvh*m->kv_cap + t)*kvd, vv + (int64_t)s*KV*kvd + kvh*kvd, kvd*sizeof(float));\n")
    s = rep(s,
            "                const float *kv = m->K[layer] + ((int64_t)kvh*m->max_t + t)*kvd;\n",
            "                const float *kv = m->K[layer] + ((int64_t)kvh*m->kv_cap + t)*kvd;\n")
    s = rep(s,
            "                const float *vrow = m->V[layer] + ((int64_t)kvh*m->max_t + t)*kvd;\n",
            "                const float *vrow = m->V[layer] + ((int64_t)kvh*m->kv_cap + t)*kvd;\n")

    # 4. record what was fed, where it was fed (kv_prefix.h's invariant)
    s = rep(s,
            "    m->kv_len = pos_base + S;\n"
            "    float *last = falloc(D);\n",
            "    m->kv_len = pos_base + S;\n"
            "    /* record what was just fed, at the positions it went to (kv_prefix.h) */\n"
            "    kv_prefix_record(&m->kvp, ids, pos_base, S);\n"
            "    float *last = falloc(D);\n")

    # 5. ensure_kv grows by copying the reusable prefix
    old_ensure = (
        "/* Allocate (once) or reuse the KV cache across requests. Grows only when a\n"
        " * longer context is needed; never shrinks. Frees the previous buffers on\n"
        " * growth so the server doesn't leak KV memory across requests. */\n"
        "static void ensure_kv(Model *m){\n"
        "    Cfg *c = &m->c;\n"
        "    if (m->kv_cap >= m->max_t && m->K) return;\n"
        "    if (m->K){\n"
        "        for (int i = 0; i < c->n_layers; i++){ if (m->K[i]) free(m->K[i]); if (m->V[i]) free(m->V[i]); }\n"
        "        free(m->K); free(m->V); m->K = NULL; m->V = NULL;\n"
        "    }\n"
        "    m->K = calloc(c->n_layers, sizeof(float*)); m->V = calloc(c->n_layers, sizeof(float*));\n"
        "    for (int i = 0; i < c->n_layers; i++){\n"
        "        if (c->is_attn[i]){\n"
        "            m->K[i] = falloc((int64_t)c->kv_heads * m->max_t * c->k_head_dim);\n"
        "            m->V[i] = falloc((int64_t)c->kv_heads * m->max_t * c->k_head_dim);\n"
        "        } else { m->K[i] = NULL; m->V[i] = NULL; }\n"
        "    }\n")
    new_ensure = (
        "/* Allocate (once) or reuse the KV cache across requests. Grows only when a\n"
        " * longer context is needed; never shrinks. GROW, DO NOT RESTART: a\n"
        " * conversation asks for a larger max_t every turn (np grows), so freeing\n"
        " * on growth would discard the very positions prefix reuse exists for\n"
        " * (same shape of bug kimi_k3.c/inkling.c had). Rows are head-major\n"
        " * [kv_heads][kv_cap][kvd], so the copy is one strided memcpy per head. */\n"
        "static void ensure_kv(Model *m){\n"
        "    Cfg *c = &m->c;\n"
        "    if (m->kv_cap >= m->max_t && m->K) return;\n"
        "    float **oldK = m->K, **oldV = m->V; int old_cap = m->kv_cap;\n"
        "    int keep = (oldK && m->kvp.len > 0 && m->kvp.len <= old_cap) ? m->kvp.len : 0;\n"
        "    int kvd = c->k_head_dim;\n"
        "    m->K = calloc(c->n_layers, sizeof(float*)); m->V = calloc(c->n_layers, sizeof(float*));\n"
        "    for (int i = 0; i < c->n_layers; i++){\n"
        "        if (c->is_attn[i]){\n"
        "            m->K[i] = falloc((int64_t)c->kv_heads * m->max_t * kvd);\n"
        "            m->V[i] = falloc((int64_t)c->kv_heads * m->max_t * kvd);\n"
        "            if (keep && oldK[i] && oldV[i]) for (int kvh = 0; kvh < c->kv_heads; kvh++){\n"
        "                memcpy(m->K[i] + (int64_t)kvh*m->max_t*kvd, oldK[i] + (int64_t)kvh*old_cap*kvd, (size_t)keep*kvd*sizeof(float));\n"
        "                memcpy(m->V[i] + (int64_t)kvh*m->max_t*kvd, oldV[i] + (int64_t)kvh*old_cap*kvd, (size_t)keep*kvd*sizeof(float));\n"
        "            }\n"
        "        } else { m->K[i] = NULL; m->V[i] = NULL; }\n"
        "    }\n"
        "    if (oldK){\n"
        "        for (int i = 0; i < c->n_layers; i++){ if (oldK[i]) free(oldK[i]); if (oldV[i]) free(oldV[i]); }\n"
        "        free(oldK); free(oldV);\n"
        "    }\n")
    s = rep(s, old_ensure, new_ensure)
    s = rep(s,
            "    m->attn_sc = falloc((int64_t)m->attn_sc_thr * m->max_t);\n"
            "    m->kv_cap = m->max_t;\n"
            "}\n",
            "    m->attn_sc = falloc((int64_t)m->attn_sc_thr * m->max_t);\n"
            "    m->kv_cap = m->max_t;\n"
            "    /* the record describes those same positions, so it survives with them */\n"
            "    if (!kv_prefix_grow(&m->kvp, m->max_t, keep)) kv_prefix_clear(&m->kvp);\n"
            "}\n"
            "\n"
            "/* ---- prefix reuse: snapshots + the decision ------------------------------ */\n"
            "static size_t q36_dn_rec_n(const Cfg *c){ return (size_t)c->dn_vheads * c->dn_kdim * c->dn_vdim; }\n"
            "static size_t q36_dn_conv_n(const Cfg *c){ return (size_t)c->dn_conv_dim * (c->dn_convk - 1); }\n"
            "\n"
            "static int q36_prefix_enabled(void){\n"
            "    const char *e = getenv(\"Q36_PREFIX\");\n"
            "    return !(e && *e && atoi(e) == 0);\n"
            "}\n"
            "\n"
            "/* Snapshot the DeltaNet state as it stands now. Only valid when the state\n"
            " * IS at `pos` (kv_len == pos) and the record covers it; anything else would\n"
            " * label a state with tokens that did not produce it. Buffers are kept for\n"
            " * the process lifetime (one allocation per slot). Returns 1 on success. */\n"
            "static int q36_snap_take(Model *m, Q36Snap *s, int pos){\n"
            "    Cfg *c = &m->c;\n"
            "    s->pos = 0;\n"
            "    if (pos <= 0 || m->kv_len != pos || m->kvp.len < pos || m->kvp.tainted) return 0;\n"
            "    if (!s->rec){\n"
            "        s->rec = calloc(c->n_layers, sizeof(float*)); s->conv = calloc(c->n_layers, sizeof(float*));\n"
            "        if (!s->rec || !s->conv){ free(s->rec); free(s->conv); s->rec = NULL; s->conv = NULL; return 0; }\n"
            "        for (int i = 0; i < c->n_layers; i++){\n"
            "            if (c->is_attn[i]) continue;\n"
            "            s->rec[i] = malloc(q36_dn_rec_n(c) * sizeof(float));\n"
            "            s->conv[i] = malloc(q36_dn_conv_n(c) * sizeof(float));\n"
            "            if (!s->rec[i] || !s->conv[i]){\n"
            "                for (int j = 0; j <= i; j++){ free(s->rec[j]); free(s->conv[j]); }\n"
            "                free(s->rec); free(s->conv); s->rec = NULL; s->conv = NULL; return 0;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    for (int i = 0; i < c->n_layers; i++){\n"
            "        if (c->is_attn[i]) continue;\n"
            "        memcpy(s->rec[i], m->DN_rec[i], q36_dn_rec_n(c) * sizeof(float));\n"
            "        memcpy(s->conv[i], m->DN_conv[i], q36_dn_conv_n(c) * sizeof(float));\n"
            "    }\n"
            "    s->pos = pos;\n"
            "    return 1;\n"
            "}\n"
            "\n"
            "static void q36_snap_restore(Model *m, const Q36Snap *s){\n"
            "    Cfg *c = &m->c;\n"
            "    for (int i = 0; i < c->n_layers; i++){\n"
            "        if (c->is_attn[i]) continue;\n"
            "        memcpy(m->DN_rec[i], s->rec[i], q36_dn_rec_n(c) * sizeof(float));\n"
            "        memcpy(m->DN_conv[i], s->conv[i], q36_dn_conv_n(c) * sizeof(float));\n"
            "    }\n"
            "}\n"
            "\n"
            "/* Longest common prefix of the record and this prompt, capped at np-1: at\n"
            " * least one token must be fed so there is a final hidden state to sample. */\n"
            "static int q36_lcp(const kv_prefix *p, const int *ids, int np){\n"
            "    if (!p->fed || p->tainted || p->len <= 0) return 0;\n"
            "    int n = p->len < np - 1 ? p->len : np - 1;\n"
            "    int i = 0;\n"
            "    while (i < n && p->fed[i] == ids[i]) i++;\n"
            "    return i;\n"
            "}\n"
            "\n"
            "/* Forget the conversation: the record, the recurrent state, the snapshots.\n"
            " * Pairs the three so they can never disagree (kv_prefix.h). */\n"
            "static void model_state_reset(Model *m){\n"
            "    kv_prefix_clear(&m->kvp);\n"
            "    reset_recurrent(m);\n"
            "    m->kv_len = 0;\n"
            "    for (int k = 0; k < Q36_SNAP_N; k++) m->snap[k].pos = 0;\n"
            "}\n"
            "\n"
            "/* Decide how much of the state to keep BEFORE touching it, then size the\n"
            " * KV cache. Returns the position prefill starts at (0 = cold).\n"
            " *\n"
            " *  1. strict continuation (kv_prefix_reuse): the prompt begins with every\n"
            " *     id the state was built from, prompt and reply alike -> the state\n"
            " *     already IS the state at that position; nothing to restore.\n"
            " *  2. otherwise the deepest snapshot at or before the longest common\n"
            " *     prefix: the attention rows below the LCP are still the rows a cold\n"
            " *     run would compute (a row depends only on its prefix), and the\n"
            " *     snapshot supplies the recurrent state at exactly that position.\n"
            " *     This is what an agent turn needs: the client re-renders the reply\n"
            " *     (tool calls, stripped reasoning) so 1 fails at the reply boundary,\n"
            " *     but the prompt-end snapshot restores everything up to it.\n"
            " *  3. nothing usable -> cold: reset, prefill from 0.\n"
            " * The logits are the ones a cold run would have produced in every case. */\n"
            "static int prepare_request_state(Model *m, const int *ids, int np, int max_t, int *lcp_out){\n"
            "    int reuse = 0;\n"
            "    *lcp_out = 0;\n"
            "    if (q36_prefix_enabled()){\n"
            "        reuse = kv_prefix_reuse(&m->kvp, ids, np);\n"
            "        if (!reuse){\n"
            "            int lcp = q36_lcp(&m->kvp, ids, np), best = -1;\n"
            "            *lcp_out = lcp;\n"
            "            for (int k = 0; k < Q36_SNAP_N; k++)\n"
            "                if (m->snap[k].pos > 0 && m->snap[k].pos <= lcp &&\n"
            "                    (best < 0 || m->snap[k].pos > m->snap[best].pos)) best = k;\n"
            "            if (best >= 0){\n"
            "                q36_snap_restore(m, &m->snap[best]);\n"
            "                reuse = m->snap[best].pos;\n"
            "                m->kvp.len = reuse;      /* the record now ends where the state does */\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    if (!reuse) model_state_reset(m);\n"
            "    m->max_t = max_t;\n"
            "    ensure_kv(m);\n"
            "    if (reuse && m->kvp.len != reuse){ model_state_reset(m); reuse = 0; }   /* growth lost the rows */\n"
            "    m->kv_len = reuse;\n"
            "    /* snapshots above the kept prefix describe positions about to be overwritten */\n"
            "    for (int k = 0; k < Q36_SNAP_N; k++) if (m->snap[k].pos > reuse) m->snap[k].pos = 0;\n"
            "    return reuse;\n"
            "}\n")

    # 6. generate()/tf_nll(): the CLI paths go through the same reset
    s = rep(s,
            "    reset_recurrent(m);\n"
            "    ensure_kv(m);\n"
            "    m->kv_len = 0;\n",
            "    model_state_reset(m);\n"
            "    ensure_kv(m);\n", count=2)

    # 7. wire protocol: optional 7th/8th header fields (xlen, prefix_bytes)
    s = rep(s,
            " *   gateway: SUBMIT <id> <slot> <plen> <max_tok> <temp> <top_p>\\n <payload bytes>\\n\n",
            " *   gateway: SUBMIT <id> <slot> <plen> <max_tok> <temp> <top_p> [<xlen> <prefix_bytes>]\\n <payload bytes>\\n\n"
            " *            (prefix_bytes: the gateway's system-prefix hint, byte length of the\n"
            " *             rendered prompt up to the first user turn -- same 8th field the\n"
            " *             DeepSeek V4 engine takes; xlen bytes of extension payload, if any,\n"
            " *             follow the prompt and are read and ignored here)\n")
    s = rep(s,
            "typedef struct { char id[64]; int max_tok; float temp, top_p; char *payload; int plen; } ServeReq;\n",
            "typedef struct { char id[64]; int max_tok; float temp, top_p; char *payload; int plen; int prefix_bytes, stable_bytes; } ServeReq;\n"
            "\n"
            "/* Parse a SUBMIT header line. Returns the number of numeric fields read\n"
            " * (5 = classic, 6 = +xlen, 7 = +system-prefix hint, 8 = +stable-prefix\n"
            " * hint) or 0 on a malformed line. Hints outside the payload are dropped. */\n"
            "static int serve_parse_header(const char *line, int *slot, int *plen, int *max_tok,\n"
            "                              float *temp, float *top_p, int *xlen, int *prefix_bytes, int *stable_bytes){\n"
            "    *xlen = 0; *prefix_bytes = 0; *stable_bytes = 0;\n"
            "    int n = sscanf(line,\"%*s %*s %d %d %d %f %f %d %d %d\",slot,plen,max_tok,temp,top_p,xlen,prefix_bytes,stable_bytes);\n"
            "    if (n < 5) return 0;\n"
            "    if (n < 6 || *xlen < 0) *xlen = 0;\n"
            "    if (n < 7 || *prefix_bytes < 0 || *prefix_bytes >= *plen) *prefix_bytes = 0;\n"
            "    if (n < 8 || *stable_bytes < 0 || *stable_bytes >= *plen) *stable_bytes = 0;\n"
            "    return n;\n"
            "}\n"
            "\n"
            "/* Tokenize the first `nbytes` of the payload. The count is a usable boundary\n"
            " * only when those ids are an exact token prefix of the whole prompt (template\n"
            " * markers make that the normal case) and strictly inside it. */\n"
            "static int serve_hint_tokens(ServeReq *q, int nbytes, const int *ids, int np){\n"
            "    if (nbytes <= 0 || nbytes >= q->plen) return 0;\n"
            "    char save = q->payload[nbytes]; q->payload[nbytes] = 0;\n"
            "    int *pids = NULL, pn = 0; encode_text(q->payload, &pids, &pn);\n"
            "    q->payload[nbytes] = save;\n"
            "    int ok = pn > 0 && pn < np && !memcmp(pids, ids, (size_t)pn*sizeof(int));\n"
            "    free(pids);\n"
            "    return ok ? pn : 0;\n"
            "}\n")
    s = rep(s,
            "    int slot, plen, max_tok; float temp, top_p;\n"
            "    if(sscanf(line,\"%*s %*s %d %d %d %f %f\",&slot,&plen,&max_tok,&temp,&top_p)!=5 ||\n"
            "       plen<0||plen>(1<<24)||max_tok<1){\n"
            "        printf(\"ERROR %s bad submit header\\n\",id); fflush(stdout); return 0;\n"
            "    }\n"
            "    (void)slot;\n"
            "    char *payload=malloc((size_t)plen+1);\n"
            "    if(!payload){ printf(\"ERROR %s out of memory\\n\",id); fflush(stdout); return 0; }\n"
            "    if(fread(payload,1,(size_t)plen,stdin)!=(size_t)plen){ free(payload); return -1; }\n"
            "    (void)fgetc(stdin); payload[plen]=0;\n",
            "    int slot, plen, max_tok, xlen, prefix_bytes, stable_bytes; float temp, top_p;\n"
            "    if(!serve_parse_header(line,&slot,&plen,&max_tok,&temp,&top_p,&xlen,&prefix_bytes,&stable_bytes) ||\n"
            "       plen<0||plen>(1<<24)||max_tok<1||xlen>(1<<24)){\n"
            "        printf(\"ERROR %s bad submit header\\n\",id); fflush(stdout); return 0;\n"
            "    }\n"
            "    (void)slot;   /* KV_SLOTS is 1 for this engine: one conversation state, reused by prefix */\n"
            "    char *payload=malloc((size_t)plen+1);\n"
            "    if(!payload){ printf(\"ERROR %s out of memory\\n\",id); fflush(stdout); return 0; }\n"
            "    if(fread(payload,1,(size_t)plen,stdin)!=(size_t)plen){ free(payload); return -1; }\n"
            "    /* extension payload (grammar/audio on other engines): not ours, drain it */\n"
            "    for(int k=0;k<xlen;k++) if(fgetc(stdin)==EOF){ free(payload); return -1; }\n"
            "    (void)fgetc(stdin); payload[plen]=0;\n"
            "    q->prefix_bytes=prefix_bytes; q->stable_bytes=stable_bytes;\n")

    # 8. serve_one: decide, restore, prefill only the tail, snapshot
    s = rep(s,
            "    printf(\"ACCEPT %s %d\\n\",q->id,np); fflush(stdout);\n"
            "    m->max_t = np + q->max_tok;\n"
            "    reset_recurrent(m); ensure_kv(m); m->kv_len = 0;\n"
            "    /* Per-REQUEST state, not per-process: without this the server keeps the\n"
            "     * first request's prefill flag and expert-collection set forever, so\n"
            "     * COLIBRI_RESIDENT=1 collects on request #1 and never again, and the\n"
            "     * router EMA carries one conversation's history into the next. */\n"
            "    m->first_step = 1;\n"
            "    if (m->seen) memset(m->seen, 0, (size_t)m->c.n_layers * m->c.n_experts);\n"
            "    if (m->momentum_logits)\n"
            "        memset(m->momentum_logits, 0,\n"
            "               (size_t)m->c.n_layers * m->c.n_experts * sizeof(float));\n"
            "    float *lo = step(m, ids, np, 0);\n",
            "    printf(\"ACCEPT %s %d\\n\",q->id,np); fflush(stdout);\n"
            "    /* KV PREFIX REUSE: decide before the state it describes is touched. */\n"
            "    int lcp = 0;\n"
            "    int reuse = prepare_request_state(m, ids, np, np + q->max_tok, &lcp);\n"
            "    /* Per-REQUEST state, not per-process: without this the server keeps the\n"
            "     * first request's prefill flag and expert-collection set forever, so\n"
            "     * COLIBRI_RESIDENT=1 collects on request #1 and never again, and the\n"
            "     * router EMA carries one conversation's history into the next. The EMA\n"
            "     * only steers the pilot prefetch (routing uses the raw logits), so a\n"
            "     * kept prefix keeps its history: that is the same conversation. */\n"
            "    m->first_step = 1;\n"
            "    if (m->seen) memset(m->seen, 0, (size_t)m->c.n_layers * m->c.n_experts);\n"
            "    if (!reuse && m->momentum_logits)\n"
            "        memset(m->momentum_logits, 0,\n"
            "               (size_t)m->c.n_layers * m->c.n_experts * sizeof(float));\n"
            "    /* Where to snapshot mid-prefill. Two boundaries, both byte hints from the\n"
            "     * gateway (tokenized, accepted only as exact token prefixes):\n"
            "     *  - prefix_bytes: end of the system turn, so the NEXT fresh conversation\n"
            "     *    starts from the shared system prefix. Without a hint, a cold miss\n"
            "     *    plans it at the LCP with the previous prompt (two fresh prompts\n"
            "     *    reveal the boundary -- DeepSeek V4's rule).\n"
            "     *  - stable_bytes: where the next turn of THIS conversation will diverge:\n"
            "     *    right after the assistant header, before the renderer's generation\n"
            "     *    suffix (Qwen's empty <think> block) that the history rendering omits\n"
            "     *    and the re-rendered reply that follows it. A snapshot at the prompt\n"
            "     *    END would sit past that divergence and every turn would fall back to\n"
            "     *    the system boundary (measured on the nuc-mini profile: 317 of 415\n"
            "     *    instead of 334). Without the hint the prompt end is used. */\n"
            "    int cut = 0, pe_cut = 0;\n"
            "    if (q36_prefix_enabled()){\n"
            "        int min_cut = getenv(\"Q36_PREFIX_MIN\") ? atoi(getenv(\"Q36_PREFIX_MIN\")) : 64;\n"
            "        if (min_cut < 8) min_cut = 8;\n"
            "        cut = serve_hint_tokens(q, q->prefix_bytes, ids, np);\n"
            "        if (cut < min_cut || cut <= reuse) cut = 0;\n"
            "        if (!cut && !reuse && lcp >= min_cut && lcp < np) cut = lcp;\n"
            "        if (m->snap[Q36_SNAP_SYS].pos > 0 && m->snap[Q36_SNAP_SYS].pos == cut) cut = 0;   /* already held */\n"
            "        pe_cut = serve_hint_tokens(q, q->stable_bytes, ids, np);\n"
            "        if (pe_cut <= reuse || pe_cut <= cut) pe_cut = 0;\n"
            "    }\n"
            "    if (getenv(\"Q36_PREFIX_LOG\")){\n"
            "        if (reuse) fprintf(stderr,\"[PREFIX] reusing %d of %d prompt tokens (%.0f%%) sys_cut=%d stable_cut=%d\\n\",\n"
            "                           reuse,np,100.0*reuse/np,cut,pe_cut);\n"
            "        else fprintf(stderr,\"[PREFIX] no reuse: held=%d cap=%d prompt=%d sys_cut=%d stable_cut=%d\\n\",\n"
            "                     m->kvp.len,m->kvp.cap,np,cut,pe_cut);\n"
            "        fflush(stderr);\n"
            "    }\n"
            "    /* chunked prefill is exact: attention is position-indexed and the\n"
            "     * DeltaNet state is carried, the same way decode extends it */\n"
            "    float *lo = NULL; int at = reuse;\n"
            "    if (cut > at){\n"
            "        lo = step(m, ids + at, cut - at, at); free(lo); at = cut;\n"
            "        q36_snap_take(m, &m->snap[Q36_SNAP_SYS], at);\n"
            "    }\n"
            "    if (pe_cut > at){\n"
            "        lo = step(m, ids + at, pe_cut - at, at); free(lo); at = pe_cut;\n"
            "        q36_snap_take(m, &m->snap[Q36_SNAP_PROMPT_END], at);\n"
            "    }\n"
            "    lo = step(m, ids + at, np - at, at);\n"
            "    if (!pe_cut && q36_prefix_enabled()) q36_snap_take(m, &m->snap[Q36_SNAP_PROMPT_END], np);\n")
    return s


def main():
    src = open(SRC).read()
    md5 = hashlib.md5(src.encode()).hexdigest()
    assert md5 == UPSTREAM_MD5, f"upstream drifted: {md5}"
    out = build(src)
    os.makedirs(DST_DIR, exist_ok=True)
    open(DST, "w").write(out)
    r = subprocess.run(["diff", "-u", "--label", "a/c/qwen36.c", "--label", "b/c/qwen36.c", SRC, DST],
                       capture_output=True, text=True)
    open(PATCH, "w").write(r.stdout)
    added = sum(1 for l in r.stdout.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in r.stdout.splitlines() if l.startswith("-") and not l.startswith("---"))
    print(f"patched {DST}: +{added} -{removed} lines -> {PATCH}")


if __name__ == "__main__":
    main()
