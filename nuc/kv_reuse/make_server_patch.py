#!/usr/bin/env python3
"""Generate the gateway side of the qwen36 prefix-reuse proposal: send the
system-prefix hint (8th SUBMIT field) for qwen36 as for deepseek_v4, plus a
byte-exact transcript test next to the existing v4 one. Asserted-unique
replacements against the pristine colibri v1.7.0 files (upstream/)."""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(HERE, "upstream")
OUT = os.path.join(HERE, "patched")


def rep(s, old, new, count=1):
    assert len(old) > 0
    n = s.count(old)
    assert n == count, f"expected {count}, found {n}: {old[:70]!r}"
    return s.replace(old, new)


def server(s):
    s = rep(s,
            '        prefix_field = ""\n'
            '        if ARCH == "deepseek_v4":\n',
            '        prefix_field = ""\n'
            '        cut = 0\n'
            '        if ARCH == "deepseek_v4":\n')
    s = rep(s,
            "                      default=0)\n"
            "            if cut > 0:\n"
            "                prefix_field = f\" {len(xpayload)} {len(prompt[:cut].encode('utf-8'))}\"\n",
            "                      default=0)\n"
            "        elif ARCH == \"qwen36\":\n"
            "            # The qwen36 hybrid takes the same hint: it snapshots its DeltaNet\n"
            "            # state at that boundary so a fresh conversation restores the shared\n"
            "            # system prefix instead of re-prefilling it. In the Qwen template the\n"
            "            # system turn ends where the first user turn begins.\n"
            "            cut = max(prompt.find(\"<|im_start|>user\"), 0)\n"
            "            # Second hint (9th field): where the NEXT turn of this conversation\n"
            "            # diverges from this prompt -- right after the assistant header. The\n"
            "            # history rendering omits the generation suffix (the empty <think>\n"
            "            # block) and re-renders the reply, so a snapshot at the prompt end\n"
            "            # would never be reusable; one at the header is.\n"
            "            head = \"<|im_start|>assistant\\n\"\n"
            "            last = prompt.rfind(head)\n"
            "            stable = last + len(head) if last > 0 else 0\n"
            "        if cut > 0:\n"
            "            prefix_field = f\" {len(xpayload)} {len(prompt[:cut].encode('utf-8'))}\"\n"
            "            if ARCH == \"qwen36\" and stable > cut:\n"
            "                prefix_field += f\" {len(prompt[:stable].encode('utf-8'))}\"\n")
    return s


def tests(s):
    return rep(s,
               "    def test_kimi_request_and_response_transcript_is_byte_exact(self):\n",
               "    def test_qwen36_request_carries_the_system_prefix_hint(self):\n"
               "        prompt = (\"<|im_start|>system\\nS<|im_end|>\\n<|im_start|>user\\nHello<|im_end|>\\n\"\n"
               "                  \"<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n\")\n"
               "        payload = prompt.encode(\"utf-8\")\n"
               "        prefix = len(\"<|im_start|>system\\nS<|im_end|>\\n\".encode(\"utf-8\"))\n"
               "        stable = len(payload) - len(\"<think>\\n\\n</think>\\n\\n\".encode(\"utf-8\"))\n"
               "        expected = (f\"SUBMIT 1 0 {len(payload)} 4 0.25 0.9 0 {prefix} {stable}\\n\".encode() +\n"
               "                    payload + b\"\\n\")\n"
               "\n"
               "        def respond(process, frame):\n"
               "            self.assertEqual(frame, expected)\n"
               "            process.stdout.feed(\n"
               "                b\"ACCEPT 1 21\\n\"\n"
               "                b\"DATA 1 4\\nA\\n\\xc3\\xa9\\n\"\n"
               "                b\"DONE 1 STAT 1 2.500 0.0 1.25 21 0\\n\"\n"
               "            )\n"
               "\n"
               "        process = FakeProcess(respond)\n"
               "        with patch(\"openai_server.ARCH\", \"qwen36\"), \\\n"
               "             patch(\"openai_server.subprocess.Popen\", return_value=process):\n"
               "            engine = Engine(\"qwen36\", \"model\")\n"
               "            chunks = []\n"
               "            stats = engine.generate(prompt, 4, 0.25, 0.9, chunks.append)\n"
               "        engine.close()\n"
               "\n"
               "        self.assertEqual(process.writes, [expected])\n"
               "        self.assertEqual(chunks, [\"A\\n\\u00e9\"])\n"
               "        self.assertEqual(stats[\"prompt_tokens\"], 21)\n"
               "\n"
               "    def test_kimi_request_and_response_transcript_is_byte_exact(self):\n")


def main():
    os.makedirs(os.path.join(OUT, "tests"), exist_ok=True)
    pairs = [("openai_server.py", server, "openai_server.py"),
             ("test_openai_server.py", tests, "tests/test_openai_server.py")]
    patch = ""
    for name, fn, rel in pairs:
        src = open(os.path.join(UP, name)).read()
        dst = os.path.join(OUT, rel)
        open(dst, "w").write(fn(src))
        r = subprocess.run(["diff", "-u", "--label", f"a/c/{rel}", "--label", f"b/c/{rel}",
                            os.path.join(UP, name), dst], capture_output=True, text=True)
        patch += r.stdout
    open(os.path.join(HERE, "openai_server-prefix-hint.patch"), "w").write(patch)
    print("ok", len(patch.splitlines()), "patch lines")


if __name__ == "__main__":
    main()
