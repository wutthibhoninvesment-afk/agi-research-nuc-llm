import unittest

from agentloop import RetriesExhausted, RetryableLLMError, RetryPolicy, retry_call


class Boom(Exception):
    pass


class Fatal(Exception):
    pass


def flaky(fail_times, exc=Boom):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise exc("fail %d" % state["calls"])
        return "ok after %d" % state["calls"]

    fn.state = state
    return fn


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.sleep = self.sleeps.append
        self.rng = lambda: 0.5  # kills jitter: delay == raw delay exactly

    def test_success_first_try_no_sleep(self):
        out = retry_call(flaky(0), retry_on=(Boom,), sleep=self.sleep, rng=self.rng)
        self.assertEqual(out, "ok after 1")
        self.assertEqual(self.sleeps, [])

    def test_retries_then_succeeds_with_exponential_delays(self):
        policy = RetryPolicy(max_attempts=4, base_delay=1.0, multiplier=2.0,
                             max_delay=30.0, jitter=0.5)
        out = retry_call(flaky(2), retry_on=(Boom,), policy=policy,
                         sleep=self.sleep, rng=self.rng)
        self.assertEqual(out, "ok after 3")
        self.assertEqual(self.sleeps, [1.0, 2.0])  # rng=0.5 -> no jitter

    def test_delay_capped_at_max_delay(self):
        policy = RetryPolicy(max_attempts=6, base_delay=10.0, multiplier=10.0,
                             max_delay=25.0, jitter=0.5)
        retry_call(flaky(4), retry_on=(Boom,), policy=policy,
                   sleep=self.sleep, rng=self.rng)
        self.assertEqual(self.sleeps, [10.0, 25.0, 25.0, 25.0])

    def test_jitter_range(self):
        policy = RetryPolicy(base_delay=1.0, jitter=0.5)
        low = policy.delay_for(1, rng=lambda: 0.0)
        high = policy.delay_for(1, rng=lambda: 0.999999)
        self.assertAlmostEqual(low, 0.5)
        self.assertAlmostEqual(high, 1.5, places=4)

    def test_exhaustion_raises_with_last_error(self):
        policy = RetryPolicy(max_attempts=3, base_delay=1.0)
        with self.assertRaises(RetriesExhausted) as ctx:
            retry_call(flaky(99), retry_on=(Boom,), policy=policy,
                       sleep=self.sleep, rng=self.rng)
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIsInstance(ctx.exception.last_error, Boom)
        self.assertEqual(len(self.sleeps), 2)  # no sleep after final attempt

    def test_non_retryable_error_propagates_immediately(self):
        fn = flaky(99, exc=Fatal)
        with self.assertRaises(Fatal):
            retry_call(fn, retry_on=(Boom,), sleep=self.sleep, rng=self.rng)
        self.assertEqual(fn.state["calls"], 1)
        self.assertEqual(self.sleeps, [])

    def test_on_retry_hook_sees_attempt_error_delay(self):
        seen = []
        retry_call(flaky(1), retry_on=(Boom,),
                   policy=RetryPolicy(base_delay=1.0),
                   sleep=self.sleep, rng=self.rng,
                   on_retry=lambda a, e, d: seen.append((a, str(e), d)))
        self.assertEqual(seen, [(1, "fail 1", 1.0)])

    def test_invalid_max_attempts_rejected(self):
        with self.assertRaises(ValueError):
            retry_call(flaky(0), retry_on=(Boom,),
                       policy=RetryPolicy(max_attempts=0),
                       sleep=self.sleep, rng=self.rng)

    # ---------------------------------------------------- retry_after hint --
    # Round 13: a RetryableLLMError can carry a server-stated `retry_after`
    # (parsed from a `retry-after` response header). retry_call() must honor
    # it over the policy's own exponential guess.

    def flaky_with_hint(self, fail_times, hints):
        state = {"calls": 0}

        def fn():
            state["calls"] += 1
            if state["calls"] <= fail_times:
                raise RetryableLLMError("rate limited", retry_after=hints[state["calls"] - 1])
            return "ok after %d" % state["calls"]
        return fn

    def test_retry_after_hint_overrides_exponential_delay(self):
        policy = RetryPolicy(max_attempts=3, base_delay=1.0, multiplier=2.0, jitter=0.5)
        fn = self.flaky_with_hint(2, hints=[7.0, 3.0])
        out = retry_call(fn, retry_on=(RetryableLLMError,), policy=policy,
                         sleep=self.sleep, rng=self.rng)
        self.assertEqual(out, "ok after 3")
        # NOT [1.0, 2.0] (the policy's own schedule) -- the server's numbers win.
        self.assertEqual(self.sleeps, [7.0, 3.0])

    def test_retry_after_none_falls_back_to_policy_delay(self):
        policy = RetryPolicy(max_attempts=3, base_delay=1.0, multiplier=2.0, jitter=0.5)
        fn = self.flaky_with_hint(2, hints=[None, None])
        retry_call(fn, retry_on=(RetryableLLMError,), policy=policy,
                   sleep=self.sleep, rng=self.rng)
        self.assertEqual(self.sleeps, [1.0, 2.0])

    def test_retry_after_hint_still_consumes_rng_deterministically(self):
        # A caller asserting exact rng-consumption counts (e.g. a seeded
        # replay test) must see the same number of rng() calls whether or
        # not a hint won -- delay_for() is still evaluated every attempt.
        calls = {"n": 0}

        def counting_rng():
            calls["n"] += 1
            return 0.5

        fn = self.flaky_with_hint(2, hints=[9.0, None])
        retry_call(fn, retry_on=(RetryableLLMError,),
                   policy=RetryPolicy(max_attempts=3, base_delay=1.0),
                   sleep=self.sleep, rng=counting_rng)
        self.assertEqual(calls["n"], 2)
        # attempt 2's policy delay is base_delay * multiplier**1 = 2.0 (default multiplier 2.0)
        self.assertEqual(self.sleeps, [9.0, 2.0])   # hint wins attempt 1, policy wins attempt 2

    def test_negative_retry_after_clamped_to_zero(self):
        fn = self.flaky_with_hint(1, hints=[-5.0])
        retry_call(fn, retry_on=(RetryableLLMError,),
                   policy=RetryPolicy(max_attempts=2, base_delay=1.0),
                   sleep=self.sleep, rng=self.rng)
        self.assertEqual(self.sleeps, [0.0])


if __name__ == "__main__":
    unittest.main()
