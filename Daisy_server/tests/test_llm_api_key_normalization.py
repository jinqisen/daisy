import os
import sys

import pytest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.llm import LLMService


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", ""),
        ("   ", ""),
        ("abc", "abc"),
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("Authorization: Bearer abc", "abc"),
        ("authorization:bearer abc", "abc"),
        ("  'Bearer abc'  ", "abc"),
        ('  "Bearer abc"  ', "abc"),
        ("Authorization: abc", "abc"),
    ],
)
def test_normalize_api_key(raw, expected):
    assert LLMService._normalize_api_key(raw) == expected
