from bid_watcher.sinks.dropbox_sink import build_project_folder_name, sanitize_segment


def test_sanitize_strips_invalid_chars():
    assert sanitize_segment('Acme / Bob? <test>') == "Acme Bob test"


def test_folder_name_falls_back_when_missing():
    name = build_project_folder_name(None, None, "2026-05-11T12:40:00+00:00")
    assert name.endswith("Bid 2026-05-11")
    assert name.startswith("Unknown Client")


def test_folder_name_uses_client_and_project():
    name = build_project_folder_name("McBrien Builders", "Riverdale HVAC", "2026-05-11T12:40:00")
    assert name == "McBrien Builders - Riverdale HVAC"
