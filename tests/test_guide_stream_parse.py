from __future__ import annotations

from src.ai.guide_cli import partial_json_string_value


def test_partial_content_grows():
    assert partial_json_string_value('{"content": "Hel') == "Hel"
    assert partial_json_string_value('{"content": "Hello"}') == "Hello"
    assert (
        partial_json_string_value('{"content": "line1\\nline2"}') == "line1\nline2"
    )


def test_partial_empty_until_value():
    assert partial_json_string_value("{") == ""
    assert partial_json_string_value('{"content"') == ""
    assert partial_json_string_value('{"content":') == ""
