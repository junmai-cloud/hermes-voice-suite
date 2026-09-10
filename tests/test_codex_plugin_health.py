from voice_suite.codex_plugin_health import parse_plugin_list


def test_installed_plugin_is_not_reported_ready_without_auth_and_live_read():
    health = parse_plugin_list(
        "google-calendar@openai-curated  installed, enabled  d416fd5a  /tmp/plugin\n",
        "google-calendar",
    )
    assert health.installation == "INSTALLED"
    assert health.enabled is True
    assert health.version == "d416fd5a"
    assert health.authentication == "UNVERIFIED"
    assert health.live_api == "UNVERIFIED"
    assert health.ready is False


def test_available_plugin_is_not_mistaken_for_installed():
    health = parse_plugin_list(
        "google-calendar@openai-curated  not installed  /tmp/plugin\n",
        "google-calendar",
    )
    assert health.installation == "NOT_INSTALLED"
    assert health.enabled is False
    assert health.next_action == "install_and_enable_plugin"


def test_missing_plugin_reports_marketplace_action():
    health = parse_plugin_list("notion@openai-curated installed, enabled abc /tmp/notion\n", "google-calendar")
    assert health.installation == "NOT_FOUND"
    assert health.ready is False
