"""Observation truncation.

Tool output goes back into the model's context, so unbounded output (a huge
file, a chatty build) can evict everything else. Strategy: keep the head and
the tail, elide the middle with an explicit marker that states how much was
cut — the model should always be able to tell it saw a partial view.

Head is weighted 2:1 over tail because leading content (error messages, file
headers) is usually more informative than trailing content, while the tail
still catches "exit status"-style summaries.
"""

TRUNCATION_MARKER = "\n... [TRUNCATED: {cut} of {total} chars elided] ...\n"


def truncate_observation(text: str, max_chars: int = 8000) -> str:
    """Return text unchanged if it fits, else head + marker + tail.

    Guarantees the result is never longer than the input, and that for any
    reasonable max_chars (>= ~80) the result fits within max_chars plus the
    marker's own length.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return text

    head_len = (max_chars * 2) // 3
    tail_len = max_chars - head_len
    cut = len(text) - head_len - tail_len
    marker = TRUNCATION_MARKER.format(cut=cut, total=len(text))
    return text[:head_len] + marker + text[len(text) - tail_len:]
