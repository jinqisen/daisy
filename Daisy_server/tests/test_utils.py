import pytest
from app.core.utils import split_response_into_parts

def test_split_response_into_parts_basic():
    text = "Hello.\n\nWorld."
    parts = split_response_into_parts(text)
    assert parts == ["Hello.", "World."]

def test_split_response_into_parts_long_sentence():
    # Long sentence that should be split
    text = "This is a very long sentence that needs to be split because it is longer than thirty characters. Yes it is."
    parts = split_response_into_parts(text)
    # The split logic is: split by delimiters if > 30 chars.
    # "This is a very long sentence that needs to be split because it is longer than thirty characters." is > 30.
    # It ends with '.', so it might be kept as one if no internal delimiters.
    # Wait, the logic splits by `(?<=[。！？.!?；;……])`.
    # So "This is... characters." is one part. "Yes it is." is another.
    # If the first part is > 30, it stays as one part if no other delimiters inside.
    
    # Let's try with internal delimiters
    text = "This is part one. This is part two. This is part three."
    # Length of "This is part one." is 17.
    # "This is part one. This is part two. This is part three." is > 30.
    # It should be split.
    parts = split_response_into_parts(text)
    assert len(parts) >= 2
    assert "This is part one." in parts[0]

def test_split_response_into_parts_action_protection():
    text = "Hello (smiles). How are you?"
    parts = split_response_into_parts(text)
    # "(smiles)" should be protected and not split even if it contains delimiters (though ) is not a delimiter.
    # Let's try a delimiter inside action
    text = "Hello (smiles. happily). How are you?"
    parts = split_response_into_parts(text)
    # The split logic shouldn't split inside (smiles. happily)
    # "Hello (smiles. happily)." might be one part.
    assert "Hello (smiles. happily)." in parts or "Hello (smiles. happily)" in parts[0]

def test_split_response_into_parts_empty():
    assert split_response_into_parts("") == []
    assert split_response_into_parts(None) == []

def test_split_response_into_parts_chinese():
    text = "你好！这是一个测试。\n\n再见。"
    parts = split_response_into_parts(text)
    assert "你好！这是一个测试。" in parts or "你好！" in parts
    assert "再见。" in parts
