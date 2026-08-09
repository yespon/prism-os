
from app.agent.terminal_graph import _resolve_tool_targets
from app.services.terminal.session import _new_command_marker, _strip_command_markers, session_manager


def test_terminal_marker_uses_prismos_identity() -> None:
    marker = _new_command_marker()
    assert marker.startswith("__PRISMOS_MARKER_")
    assert "OPSINTECH" not in marker


def test_terminal_output_strips_prismos_marker() -> None:
    marker = "__PRISMOS_MARKER_abc__"
    assert _strip_command_markers(f"hello\n{marker}\n") == "hello\n"


def test_terminal_output_preserves_lines_around_marker() -> None:
    marker = "__PRISMOS_MARKER_abc__"
    assert _strip_command_markers(f"before\n{marker}\nafter\n") == "before\nafter\n"

def test_session_manager_composite_key():
    # Clear existing sessions for clean test state
    session_manager.sessions.clear()
    
    # Create session for task_1 on host_A
    s1 = session_manager.get_or_create_session("task_1", "host_A")
    assert s1.session_id == "task_1"
    assert s1.asset_id == "host_A"
    
    # Retrieve it
    assert session_manager.get_session("task_1", "host_A") == s1
    
    # Create session for task_1 on host_B
    s2 = session_manager.get_or_create_session("task_1", "host_B")
    assert s2.session_id == "task_1"
    assert s2.asset_id == "host_B"
    assert s1 != s2
    
    # Fallback retrieve should return first matching session
    assert session_manager.get_session("task_1") in (s1, s2)
    
    # Close specific session
    session_manager.close_session("task_1", "host_A")
    assert session_manager.get_session("task_1", "host_A") is None
    assert session_manager.get_session("task_1", "host_B") == s2
    
    # Close all for task_1
    session_manager.close_session("task_1")
    assert len(session_manager.sessions) == 0

def test_resolve_tool_targets():
    selected_assets = [
        {"id": "h1", "name": "host-1", "ip": "10.0.0.1"},
        {"id": "h2", "name": "host-2", "ip": "10.0.0.2"},
        {"id": "h3", "name": "host-3", "ip": "10.0.0.3"},
    ]
    
    # Case 1: No host_index, no asset_id -> defaults to all selected_assets
    targets = _resolve_tool_targets({}, "h1", selected_assets)
    assert len(targets) == 3
    assert [t["id"] for t in targets] == ["h1", "h2", "h3"]
    
    # Case 2: host_index is -1 -> targets all selected_assets
    targets = _resolve_tool_targets({"host_index": -1}, "h1", selected_assets)
    assert len(targets) == 3
    assert [t["id"] for t in targets] == ["h1", "h2", "h3"]
    
    # Case 3: host_index is 1 -> targets host at index 1
    targets = _resolve_tool_targets({"host_index": 1}, "h1", selected_assets)
    assert len(targets) == 1
    assert targets[0]["id"] == "h2"
    assert targets[0]["name"] == "host-2"
    
    # Case 4: host_index out of bounds -> falls back to default
    targets = _resolve_tool_targets({"host_index": 99}, "h1", selected_assets)
    assert len(targets) == 3
    
    # Case 5: asset_id matches in selected_assets
    targets = _resolve_tool_targets({"asset_id": "h3"}, "h1", selected_assets)
    assert len(targets) == 1
    assert targets[0]["id"] == "h3"
    
    # Case 6: asset_id doesn't match selected_assets -> returns asset_id as fallback target
    targets = _resolve_tool_targets({"asset_id": "h_other"}, "h1", selected_assets)
    assert len(targets) == 1
    assert targets[0]["id"] == "h_other"
    
    # Case 7: no selected_assets -> fallback to primary asset_id
    targets = _resolve_tool_targets({}, "h_primary", [])
    assert len(targets) == 1
    assert targets[0]["id"] == "h_primary"
