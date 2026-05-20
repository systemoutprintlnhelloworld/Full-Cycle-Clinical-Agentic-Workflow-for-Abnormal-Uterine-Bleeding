from __future__ import annotations

import re
from typing import Any


_CASE_UNDERSCORE_RE = re.compile(r"^(.*)_([0-9]+)$")
_TRAILING_DIGITS_RE = re.compile(r"^(.*?)([0-9]+)$")


def case_id_sort_key(case_id: Any) -> tuple[str, int, str]:
    """
    Natural sort key for case IDs like:
      foshan_2 < foshan_10
      wuhan_7 < wuhan_11
    """
    s = "" if case_id is None else str(case_id).strip()
    if not s:
        return ("", 10**9, "")
    m = _CASE_UNDERSCORE_RE.match(s)
    if m:
        return (m.group(1), int(m.group(2)), s)
    m = _TRAILING_DIGITS_RE.match(s)
    if m:
        return (m.group(1), int(m.group(2)), s)
    return (s, 10**9, s)

