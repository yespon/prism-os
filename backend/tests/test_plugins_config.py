"""Integration tests for plugin configuration system."""


def test_load_plugin_config_defaults_all_enabled():
    """When no plugins config provided, all plugins default to enabled."""
    from app.plugins.registry import PLUGIN_DEFINITIONS, load_plugin_config

    states = load_plugin_config(None)
    assert len(states) == len(PLUGIN_DEFINITIONS)
    for key, enabled in states.items():
        assert enabled is True, f"Plugin '{key}' should default to enabled"


def test_load_plugin_config_disabled():
    """When a plugin is explicitly disabled, it should be false."""
    from app.plugins.registry import load_plugin_config

    states = load_plugin_config({"ops-alerting": {"enabled": False}})
    assert states["ops-alerting"] is False
    assert states["ops-terminal"] is True  # not mentioned, defaults to True


def test_load_plugin_config_partial():
    """Only listed plugins are affected; unlisted ones default to True."""
    from app.plugins.registry import load_plugin_config

    states = load_plugin_config({"ops-terminal": {"enabled": False}})
    assert states["ops-alerting"] is True
    assert states["ops-terminal"] is False
    assert states["ops-assets"] is True


def test_plugin_definitions_have_valid_imports():
    """Every plugin definition with a router should have a valid import path."""
    from app.plugins.registry import PLUGIN_DEFINITIONS

    for key, defn in PLUGIN_DEFINITIONS.items():
        if defn.router_import:
            mod = __import__(defn.router_import, fromlist=[defn.router_attr])
            assert hasattr(mod, defn.router_attr), (
                f"Plugin '{key}': {defn.router_import} has no attribute '{defn.router_attr}'"
            )