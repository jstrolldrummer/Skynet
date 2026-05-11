from bid_watcher.classify.classifier import _extract_json


def test_extract_plain_json():
    data = _extract_json('{"is_bid_request": true, "confidence": 0.9, "scope_summary": "x"}')
    assert data["is_bid_request"] is True


def test_extract_fenced_json():
    text = """```json
{"is_bid_request": false, "confidence": 0.1, "scope_summary": ""}
```"""
    data = _extract_json(text)
    assert data["confidence"] == 0.1


def test_extract_with_preamble():
    text = "Sure! Here is the analysis:\n{\"is_bid_request\": true, \"confidence\": 0.8, \"scope_summary\": \"hvac retrofit\"}"
    data = _extract_json(text)
    assert data["scope_summary"] == "hvac retrofit"
