import unittest

from agentloop import truncate_observation


class TruncateTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(truncate_observation("hello", 100), "hello")

    def test_exact_fit_unchanged(self):
        text = "x" * 100
        self.assertEqual(truncate_observation(text, 100), text)

    def test_long_text_keeps_head_and_tail(self):
        text = "HEAD" + "m" * 10000 + "TAIL"
        out = truncate_observation(text, 300)
        self.assertTrue(out.startswith("HEAD"))
        self.assertTrue(out.endswith("TAIL"))
        self.assertIn("TRUNCATED", out)
        self.assertLess(len(out), len(text))

    def test_marker_reports_elided_char_count(self):
        text = "a" * 1000
        out = truncate_observation(text, 100)
        # head 66 + tail 34 = 100 kept, 900 cut
        self.assertIn("[TRUNCATED: 900 of 1000 chars elided]", out)

    def test_head_weighted_over_tail(self):
        text = "".join(str(i % 10) for i in range(1000))
        out = truncate_observation(text, 90)
        marker_start = out.index("\n...")
        head = out[:marker_start]
        tail = out[out.rindex("...\n") + 4:]
        self.assertGreater(len(head), len(tail))
        self.assertEqual(len(head) + len(tail), 90)

    def test_rejects_nonpositive_max(self):
        with self.assertRaises(ValueError):
            truncate_observation("abc", 0)


if __name__ == "__main__":
    unittest.main()
