# Errand — a task-script language for agent ops on a slow box (spec v0.1, round 112)

**One idea:** every request is *priced before it is sent*. On pgain-nuc a wrong
prompt costs minutes (E1: 23 s at 134 tokens, 143 s at 904, 87 min for a stock
Hermes turn), so the script's static shape — lane, prompt, reply cap — is enough
to project the cost from the banked curves and refuse, reroute or shrink the
work *before* the network is touched. The second idea is Whence's: a result is
a value that carries its own trail (lane, attempts, tokens, seconds, refusals),
and a failure is a `miss` value that explains itself instead of an exception.

## Design decisions
1. **Preflight is mandatory.** A task's projected seconds
   (`fixed + prompt/prefill + reply/decode`, or the measured E1 curve for the
   qwen36 lane) are compared with the *remaining* budget — the task's own
   `within` budget and the enclosing flow's — and a task that does not fit is a
   `miss` with no request sent. Prompt tokens come from an injectable tokenizer
   (default: chars/4 + 5 per message, stated as an estimate).
2. **Budgets are consumed, not just declared.** A flow `within` a budget spends
   measured seconds (projected seconds under `--dry-run`); the next task sees
   what is left. Retries draw on the same budget: a retry whose projection no
   longer fits is refused. The transport timeout *is* the remaining budget.
3. **Retries are policy, not code.** `retry N backoff D` = up to N extra
   attempts, delay `D·2^(n−1)` with ±50 % jitter; sleep and rng are injected so
   tests run instantly. Only *retryable* failures retry: transport errors,
   HTTP 408/429/5xx, timeouts, and an `expect` clause the reply fails. Other
   4xx and preflight refusals are final.
4. **Errors are values.** `ok(text)` / `miss(reasons)`; `miss` propagates
   through `==`, `!=`, interpolation, `if` (a miss condition ends the flow with
   that miss). `a rescue b` recovers. `why(x)` renders the trail; `missed(x)`
   tests it. The interpreter never raises for a script-level failure.
5. **Telemetry is the trace, not a printout.** Every preflight, attempt,
   retry and result is one JSON line (`--trace`); a `flow_end` line totals
   seconds and tokens per lane. The same events feed `why`.
6. **Static discipline at link time.** Duplicate names, unknown lane/budget,
   wrong call arity, undefined names in a flow, `{name}` interpolating an
   undeclared name, and a lane URL on port 8001 (the frontier lane — hard rule)
   are errors before anything runs (exit 2).
7. **No tools in v0.1.** Tool calls are the tool-proxy's job (:8080); Errand
   scripts compose tool-free turns and route between lanes. Lanes still carry
   `tools yes|no` and `ctx` as facts the preflight enforces (`ctx` overflow is a
   refusal).

## Grammar (newline-separated; `#` comments; `( )` suppress newlines)
```
program  := (lane | budget | task | flow)*
lane     := 'lane' NAME '{' (key value)* '}'      keys: url model prefill decode fixed ctx tools
                                                     prefill := NUMBER | 'e1'; tools := 'yes'|'no'
budget   := 'budget' NAME '{' ('time' DURATION | 'tokens' NUMBER)* '}'
task     := 'task' NAME '(' params ')' 'on' NAME ['within' NAME] ['retry' NUMBER]
            ['backoff' DURATION] '{' ('system' STRING | 'user' STRING | 'reply' NUMBER | expect)* '}'
expect   := 'expect' ('one_of' STRING+ | 'contains' STRING | 'nonempty' | 'json')
flow     := 'flow' NAME '(' params ')' ['within' NAME] block
block    := '{' stmt* '}'
stmt     := 'let' NAME '=' expr | 'if' expr block ['else' (block | if)] | 'emit' expr
expr     := rescue ; rescue := cmp ('rescue' cmp)* ; cmp := unary (('=='|'!=') unary)?
unary    := STRING | NUMBER | 'true' | 'false' | NAME | NAME '(' args ')' | '(' expr ')'
DURATION := NUMBER ('ms'|'s'|'m'|'h') ; STRING interpolates '{name}' ('{{' escapes)
```
Builtins: `why(x)`, `missed(x)`, `len(x)`, `lower(x)`, `trim(x)`.

## Exit codes (`run.py script.errand FLOW k=v ...`)
0 flow completed, every emitted value ok · 1 a miss was emitted or ended the
flow · 2 lex/parse/link error · 3 usage/transport setup error.
`--dry-run` prices every task without a request (works with the box down);
`--transport mock:FILE` replays scripted replies; `--transport http` is live.
