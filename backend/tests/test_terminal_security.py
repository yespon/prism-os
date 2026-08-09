import pytest
from app.services.terminal.security import (
    CommandSecurityService,
    split_compound_command,
    extract_executable,
    matches_pattern,
    DEFAULT_SECURITY_CONFIG,
    DEFAULT_AUTO_APPROVAL,
)
from app.agent.terminal_tools import _build_web_fetch_command, _build_write_file_command
from app.gateway.routers.terminal import _build_web_fetch_argv


def test_write_file_command_uses_prismos_heredoc() -> None:
    command = _build_write_file_command("/tmp/report.txt", "hello")
    assert command.count("PRISMOS_EOF") == 2
    assert "OP" + "SINTECH_EOF" not in command


def test_web_fetch_commands_use_prismos_user_agents() -> None:
    command = _build_web_fetch_command("https://example.com")
    argv = _build_web_fetch_argv("https://example.com")
    assert "User-Agent: PrismOS/0.2" in command
    assert "User-Agent: Mozilla/5.0 (compatible; PrismOS/0.2)" in argv
    assert "OpsinTech" not in command
    assert all("OpsinTech" not in part for part in argv)

def test_split_compound_command():
    assert split_compound_command("ls -la && pwd") == ["ls -la", "pwd"]
    assert split_compound_command("echo 'a && b'; cat file") == ["echo 'a && b'", "cat file"]
    assert split_compound_command("command1 || command2; command3") == ["command1", "command2", "command3"]

def test_extract_executable():
    assert extract_executable("ls -la") == "ls"
    assert extract_executable("sudo systemctl restart nginx") == "systemctl"
    assert extract_executable("sudo nice df -h") == "df"
    assert extract_executable("cat file.txt | grep foo") == "cat"

def test_matches_pattern():
    assert matches_pattern("rm -rf /", "rm -rf /") is True
    assert matches_pattern("rm -rf /*", "rm -rf /*") is True
    assert matches_pattern("chmod 777 /path", "chmod 777 *") is True
    assert matches_pattern("ls -la", "ls") is True

def test_evaluate_command_allow_safe():
    res = CommandSecurityService.evaluate_command("ls -la", mode="agent")
    assert res.action == "allow"

def test_evaluate_command_block_critical():
    res = CommandSecurityService.evaluate_command("rm -rf /", mode="agent")
    assert res.action == "block"
    assert res.risk_level == "critical"

def test_evaluate_command_ask_dangerous():
    res = CommandSecurityService.evaluate_command("systemctl restart docker", mode="agent")
    assert res.action == "ask"
    assert res.risk_level == "high"

def test_evaluate_command_cmd_mode_ask():
    res = CommandSecurityService.evaluate_command("ls -la", mode="cmd")
    assert res.action == "ask"
    assert res.risk_level == "low"
