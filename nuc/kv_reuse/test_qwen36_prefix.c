/* test_qwen36_prefix — prefix reuse for the qwen36 hybrid engine: the
 * decision, the DeltaNet snapshots, and a KV growth that keeps the rows.
 *
 * The piece that must not be wrong is the decision (see test_kv_prefix.c): a
 * bad reuse length does not crash, it answers from a state built out of a
 * different conversation. Every rejection rule gets a case.
 *
 * No model file: everything under test reads only geometry fields, the same
 * way test_qwen36_ctx.c drives ensure_kv(). The prefill/decode calls are
 * simulated by feed(): record the ids where step() would have recorded them
 * and move kv_len, which is all prepare_request_state() ever looks at.
 */
#define main qwen36_main_unused
#include "../qwen36.c"
#undef main

static int fails = 0;

static void ck(int cond, const char *what) {
    if (cond) { printf("  ok   %s\n", what); return; }
    printf("  FAIL %s\n", what);
    fails++;
}

static void env_set(const char *name, const char *value) { setenv(name, value, 1); }
static void env_unset(const char *name) { unsetenv(name); }

#define NL 8                    /* 8 layers, 2 of them attention (i % 4 == 3) */
#define KVH 2
#define KVD 4

static void shape_model(Model *m) {
    memset(m, 0, sizeof(*m));
    m->c.n_layers = NL; m->c.kv_heads = KVH; m->c.k_head_dim = KVD;
    m->c.dn_vheads = 2; m->c.dn_kdim = 3; m->c.dn_vdim = 3;
    m->c.dn_conv_dim = 6; m->c.dn_convk = 4;
    m->c.is_attn = calloc(NL, 1);
    for (int i = 0; i < NL; i++) m->c.is_attn[i] = (i % 4 == 3);
    m->DN_rec = calloc(NL, sizeof(float *));
    m->DN_conv = calloc(NL, sizeof(float *));
    for (int i = 0; i < NL; i++) {
        if (m->c.is_attn[i]) continue;
        m->DN_rec[i] = calloc(q36_dn_rec_n(&m->c), sizeof(float));
        m->DN_conv[i] = calloc(q36_dn_conv_n(&m->c), sizeof(float));
    }
}

static void dn_fill(Model *m, float v) {
    for (int i = 0; i < NL; i++) {
        if (m->c.is_attn[i]) continue;
        for (size_t j = 0; j < q36_dn_rec_n(&m->c); j++) m->DN_rec[i][j] = v;
        for (size_t j = 0; j < q36_dn_conv_n(&m->c); j++) m->DN_conv[i][j] = v;
    }
}

static int dn_all(Model *m, float v) {
    for (int i = 0; i < NL; i++) {
        if (m->c.is_attn[i]) continue;
        for (size_t j = 0; j < q36_dn_rec_n(&m->c); j++) if (m->DN_rec[i][j] != v) return 0;
        for (size_t j = 0; j < q36_dn_conv_n(&m->c); j++) if (m->DN_conv[i][j] != v) return 0;
    }
    return 1;
}

/* what step() does to the bookkeeping when it feeds n ids at pos0 */
static void feed(Model *m, const int *ids, int pos0, int n) {
    kv_prefix_record(&m->kvp, ids, pos0, n);
    m->kv_len = pos0 + n;
}

static float row_val(int layer, int kvh, int t, int d) { return 100.f * layer + 10.f * kvh + t + d / 10.f; }

/* --- growth keeps the reusable rows, at the new stride ------------------- */
static void case_growth_keeps_rows(void) {
    Model m; shape_model(&m);
    printf("growth keeps rows\n");
    const int ids[6] = {1, 2, 3, 4, 5, 6};
    m.max_t = 16; ensure_kv(&m);
    ck(m.kvp.cap == 16 && m.kvp.fed != NULL, "first allocation sizes the record to the cache");
    feed(&m, ids, 0, 6);
    for (int layer = 3; layer < NL; layer += 4)
        for (int kvh = 0; kvh < KVH; kvh++)
            for (int t = 0; t < 6; t++)
                for (int d = 0; d < KVD; d++) {
                    m.K[layer][((int64_t)kvh * m.kv_cap + t) * KVD + d] = row_val(layer, kvh, t, d);
                    m.V[layer][((int64_t)kvh * m.kv_cap + t) * KVD + d] = -row_val(layer, kvh, t, d);
                }
    m.max_t = 64; ensure_kv(&m);
    ck(m.kv_cap == 64, "cache grew to the new max_t");
    ck(m.kvp.len == 6 && m.kvp.cap == 64, "the record survived the growth with its positions");
    int intact = 1;
    for (int layer = 3; layer < NL; layer += 4)
        for (int kvh = 0; kvh < KVH; kvh++)
            for (int t = 0; t < 6; t++)
                for (int d = 0; d < KVD; d++) {
                    if (m.K[layer][((int64_t)kvh * 64 + t) * KVD + d] != row_val(layer, kvh, t, d)) intact = 0;
                    if (m.V[layer][((int64_t)kvh * 64 + t) * KVD + d] != -row_val(layer, kvh, t, d)) intact = 0;
                }
    ck(intact, "every kept row of every head sits at the kv_cap stride");
    m.max_t = 32; ensure_kv(&m);
    ck(m.kv_cap == 64 && m.kvp.len == 6, "a smaller request neither shrinks nor forgets");
}

/* --- the decision --------------------------------------------------------- */
static void case_strict_continuation(void) {
    Model m; shape_model(&m);
    printf("strict continuation\n");
    const int p1[6] = {1, 2, 3, 4, 5, 6};
    int lcp = -1;
    int r = prepare_request_state(&m, p1, 6, 6 + 4, &lcp);
    ck(r == 0 && lcp == 0, "first request is cold");
    feed(&m, p1, 0, 6);
    dn_fill(&m, 7.f);
    const int p2[8] = {1, 2, 3, 4, 5, 6, 9, 10};
    r = prepare_request_state(&m, p2, 8, 8 + 4, &lcp);
    ck(r == 6, "a prompt that extends the record reuses all of it");
    ck(dn_all(&m, 7.f), "the recurrent state is kept as it stands");
    ck(m.kv_len == 6 && m.kvp.len == 6, "prefill resumes at the record's end");
    ck(m.kv_cap >= 12, "the cache was grown for the new request");
}

static void case_prompt_end_snapshot(void) {
    Model m; shape_model(&m);
    printf("prompt-end snapshot survives a re-rendered reply\n");
    const int p1[6] = {1, 2, 3, 4, 5, 6};
    int lcp;
    prepare_request_state(&m, p1, 6, 6 + 8, &lcp);
    feed(&m, p1, 0, 6);
    dn_fill(&m, 7.f);
    ck(q36_snap_take(&m, &m.snap[Q36_SNAP_PROMPT_END], 6) == 1 && m.snap[Q36_SNAP_PROMPT_END].pos == 6,
       "snapshot taken at the prompt end");
    /* decode two tokens: the state moves on, the record follows */
    const int gen[2] = {20, 21};
    dn_fill(&m, 8.f);
    feed(&m, gen, 6, 2);
    ck(m.kvp.len == 8, "decoded tokens are recorded");
    /* the client re-renders the reply: 30 31 32 instead of 20 21 */
    const int p2[9] = {1, 2, 3, 4, 5, 6, 30, 31, 32};
    int r = prepare_request_state(&m, p2, 9, 9 + 8, &lcp);
    ck(lcp == 6, "LCP stops at the reply boundary");
    ck(r == 6, "reuse falls back to the prompt-end snapshot");
    ck(dn_all(&m, 7.f), "the recurrent state was restored from the snapshot");
    ck(m.kvp.len == 6 && m.kv_len == 6, "record and state agree on the restored position");
    ck(m.snap[Q36_SNAP_PROMPT_END].pos == 6, "a snapshot at the kept prefix stays valid");
}

static void case_deepest_snapshot_wins(void) {
    Model m; shape_model(&m);
    printf("deepest usable snapshot wins, deeper ones are dropped\n");
    const int p1[6] = {1, 2, 3, 4, 5, 6};
    int lcp;
    prepare_request_state(&m, p1, 6, 6 + 8, &lcp);
    feed(&m, p1, 0, 3); dn_fill(&m, 5.f);
    ck(q36_snap_take(&m, &m.snap[Q36_SNAP_SYS], 3) == 1, "system-boundary snapshot at 3");
    feed(&m, p1 + 3, 3, 3); dn_fill(&m, 7.f);
    ck(q36_snap_take(&m, &m.snap[Q36_SNAP_PROMPT_END], 6) == 1, "prompt-end snapshot at 6");

    const int same_conv[9] = {1, 2, 3, 4, 5, 6, 30, 31, 32};
    int r = prepare_request_state(&m, same_conv, 9, 9 + 8, &lcp);
    ck(r == 6 && dn_all(&m, 7.f), "same conversation: the prompt-end snapshot (deeper) is used");
    ck(m.snap[Q36_SNAP_SYS].pos == 3, "the shallower system snapshot is kept");
    feed(&m, same_conv + 6, 6, 3);

    const int new_conv[7] = {1, 2, 3, 40, 41, 42, 43};
    r = prepare_request_state(&m, new_conv, 7, 7 + 8, &lcp);
    ck(lcp == 3, "new conversation shares only the system prefix");
    ck(r == 3 && dn_all(&m, 5.f), "the system snapshot restores the shared prefix");
    ck(m.snap[Q36_SNAP_PROMPT_END].pos == 0, "the deeper snapshot is dropped: its positions get overwritten");
    ck(m.snap[Q36_SNAP_SYS].pos == 3, "the system snapshot survives for the next conversation");
}

static void case_rejections(void) {
    Model m; shape_model(&m);
    printf("rejections\n");
    const int p1[6] = {1, 2, 3, 4, 5, 6};
    int lcp;
    prepare_request_state(&m, p1, 6, 6 + 8, &lcp);
    feed(&m, p1, 0, 6); dn_fill(&m, 7.f);
    q36_snap_take(&m, &m.snap[Q36_SNAP_PROMPT_END], 6);

    ck(q36_snap_take(&m, &m.snap[Q36_SNAP_SYS], 4) == 0 && m.snap[Q36_SNAP_SYS].pos == 0,
       "a snapshot is refused when the state is not at that position");

    int r = prepare_request_state(&m, p1, 6, 6 + 8, &lcp);
    ck(r == 0 && lcp == 5, "an equal prompt cannot reuse everything (nothing left to feed) nor a snapshot past np-1");
    ck(dn_all(&m, 0.f) && m.kvp.len == 0 && m.snap[Q36_SNAP_PROMPT_END].pos == 0,
       "a cold miss resets state, record and snapshots together");

    feed(&m, p1, 0, 6); dn_fill(&m, 7.f);
    q36_snap_take(&m, &m.snap[Q36_SNAP_PROMPT_END], 6);
    const int shorter[4] = {1, 2, 3, 4};
    r = prepare_request_state(&m, shorter, 4, 4 + 8, &lcp);
    ck(r == 0, "a shorter prompt with no snapshot inside it starts cold (state cannot rewind)");

    feed(&m, p1, 0, 6); dn_fill(&m, 7.f);
    const int other[7] = {9, 9, 9, 9, 9, 9, 9};
    r = prepare_request_state(&m, other, 7, 7 + 8, &lcp);
    ck(r == 0 && lcp == 0 && dn_all(&m, 0.f), "a diverging prompt reuses nothing");

    feed(&m, p1, 0, 6); dn_fill(&m, 7.f);
    env_set("Q36_PREFIX", "0");
    const int p2[8] = {1, 2, 3, 4, 5, 6, 9, 10};
    r = prepare_request_state(&m, p2, 8, 8 + 8, &lcp);
    ck(r == 0 && dn_all(&m, 0.f), "Q36_PREFIX=0 disables reuse entirely");
    env_unset("Q36_PREFIX");
}

/* --- the wire header ------------------------------------------------------ */
static void case_header(void) {
    printf("SUBMIT header\n");
    int slot, plen, max_tok, xlen, pb, sb; float temp, top_p;
    ck(serve_parse_header("SUBMIT 7 0 120 64 0.7 0.9\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 5
       && plen == 120 && max_tok == 64 && xlen == 0 && pb == 0 && sb == 0, "classic six-field header");
    ck(serve_parse_header("SUBMIT 7 0 120 64 0.7 0.9 0 80\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 7
       && xlen == 0 && pb == 80 && sb == 0, "eighth field carries the system-prefix hint");
    ck(serve_parse_header("SUBMIT 7 0 120 64 0.7 0.9 0 80 110\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 8
       && pb == 80 && sb == 110, "ninth field carries the stable-prefix hint");
    ck(serve_parse_header("SUBMIT 7 0 120 64 0.7 0.9 5\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 6
       && xlen == 5 && pb == 0, "seventh field alone is an extension length");
    ck(serve_parse_header("SUBMIT 7 0 120 64 0.7 0.9 0 120 120\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 8
       && pb == 0 && sb == 0, "hints at or past the payload end are ignored");
    ck(serve_parse_header("SUBMIT 7 0 120\n", &slot, &plen, &max_tok, &temp, &top_p, &xlen, &pb, &sb) == 0,
       "a short header is malformed");
}

int main(void) {
    env_unset("Q36_PREFIX");
    case_growth_keeps_rows();
    case_strict_continuation();
    case_prompt_end_snapshot();
    case_deepest_snapshot_wins();
    case_rejections();
    case_header();
    if (fails) { printf("%d FAILED\n", fails); return 1; }
    printf("OK test_qwen36_prefix\n");
    return 0;
}
