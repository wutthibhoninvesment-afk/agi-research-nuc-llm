"""swe — the harness turned on our own code (round 5, track D).

    fuzz.py       random Whence programs + totality oracle + shrinker
    mutation.py   AST mutation testing of a Python module against a pytest suite
    killers.py    differential test generation: find programs that kill survivors
    tools.py      the above as agentloop Tools (sandboxed to the Whence checkout)
    policy.py     PolicyLLM: a scripted, deterministic "model" that drives the loop
    loop.py       CLI entry point: run the whole SWE loop, write metrics
"""
