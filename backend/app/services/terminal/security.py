import re
from typing import Literal

SecurityResult = Literal["allow", "ask", "block"]

class CommandSecurityResult:
    def __init__(
        self,
        action: SecurityResult,
        reason: str = "",
        risk_level: str = "low",
        is_state_changing: bool = False,
    ):
        self.action = action
        self.reason = reason
        self.risk_level = risk_level
        self.is_state_changing = is_state_changing


DEFAULT_SECURITY_CONFIG = {
    "enableCommandSecurity": True,
    "enableStrictMode": False,
    "maxCommandLength": 10000,
    "blacklistPatterns": [
        'rm -rf /',
        'rm -rf /*',
        'rm -fr /',
        'rm -fr /*',
        'chmod 777 /',
        'chmod -R 777 /',
        'chown -R /',
        'dd if=/dev/zero',
        'mkfs.* /dev/sda',
        'mkfs.* /dev/nvme',
        ':(){ :|:& };:',
        'wget * -O - | sh',
        'curl * | sh',
    ],
    "whitelistPatterns": [
        'ls', 'pwd', 'whoami', 'date', 'uptime', 'uname',
        'df', 'du', 'free', 'ps aux', 'top -n 1 -b',
        'netstat', 'ss', 'ping', 'curl -I', 'wget --spider',
        'cat', 'head', 'tail', 'grep', 'find', 'which', 'type', 'file',
        'echo', 'printf', 'printenv', 'env',
        'id', 'groups', 'hostname',
        'awk', 'sed', 'cut', 'tr',
        'git status', 'git log', 'git diff', 'git branch',
        'docker ps', 'docker images', 'kubectl get',
        'journalctl', 'dmesg',
    ],
    "dangerousCommands": [
        'rm', 'del', 'format', 'shutdown', 'reboot', 'halt', 'poweroff',
        'dd', 'mkfs', 'fdisk', 'parted',
        'killall', 'pkill',
        'systemctl', 'service',
        'chmod', 'chown',
        'mount', 'umount',
        'iptables', 'ufw', 'firewall-cmd',
        'sudo', 'su',
        'init',
    ],
    "securityPolicy": {
        "blockCritical": True,
        "askForHigh": True,
        "askForMedium": True,
        "askForBlacklist": False,
    },
}

DEFAULT_AUTO_APPROVAL = {
    "enabled": False,
    "actions": {
        "readFiles": True,
        "editFiles": False,
        "executeSafeCommands": True,
        "executeAllCommands": False,
        "autoExecuteReadOnlyCommands": False,
    },
    "maxRequests": 3,
    "enableNotifications": True,
}

DANGEROUS_COMMANDS_SEVERITY = {
    # Critical
    "rm": {"severity": "critical", "reason": "删除文件/目录，可能导致数据丢失"},
    "del": {"severity": "critical", "reason": "删除文件，可能导致数据丢失"},
    "format": {"severity": "critical", "reason": "格式化磁盘，会导致数据永久丢失"},
    "shutdown": {"severity": "critical", "reason": "关闭系统，会导致服务中断"},
    "reboot": {"severity": "critical", "reason": "重启系统，会导致服务中断"},
    "halt": {"severity": "critical", "reason": "停止系统，会导致服务中断"},
    "poweroff": {"severity": "critical", "reason": "关闭电源，会导致服务中断"},
    "dd": {"severity": "critical", "reason": "磁盘操作，误用会导致数据丢失"},
    "mkfs": {"severity": "critical", "reason": "创建文件系统，会清空磁盘数据"},
    "fdisk": {"severity": "critical", "reason": "磁盘分区操作，误用会导致数据丢失"},
    "parted": {"severity": "critical", "reason": "磁盘分区工具，误操作会导致数据丢失"},
    "init": {"severity": "critical", "reason": "改变系统运行级别，可能导致服务中断"},
    # High
    "killall": {"severity": "high", "reason": "批量终止进程，可能影响系统稳定性"},
    "pkill": {"severity": "high", "reason": "模式匹配终止进程，可能误杀关键进程"},
    "systemctl": {"severity": "high", "reason": "管理系统服务，可能影响服务运行"},
    "service": {"severity": "high", "reason": "管理系统服务，可能影响服务运行"},
    "chmod": {"severity": "high", "reason": "修改文件权限，可能导致安全漏洞"},
    "chown": {"severity": "high", "reason": "修改文件所有者，可能影响系统安全"},
    "mount": {"severity": "high", "reason": "挂载文件系统，不当操作可能影响系统"},
    "umount": {"severity": "high", "reason": "卸载文件系统，可能导致数据不一致"},
    # Medium
    "iptables": {"severity": "medium", "reason": "修改防火墙规则，可能影响网络访问"},
    "ufw": {"severity": "medium", "reason": "修改防火墙设置，可能影响网络访问"},
    "firewall-cmd": {"severity": "medium", "reason": "修改防火墙配置，可能影响网络访问"},
    "sudo": {"severity": "medium", "reason": "以超级用户权限执行命令，请确认必要性"},
    "su": {"severity": "medium", "reason": "切换用户身份，请确认必要性"},
}

READONLY_COMMANDS = [
    'ls', 'pwd', 'whoami', 'date', 'uptime', 'uname',
    'df', 'du', 'free', 'ps', 'top', 'htop',
    'netstat', 'ss', 'ping', 'traceroute',
    'curl', 'wget',
    'cat', 'head', 'tail', 'grep', 'find', 'wc', 'sort',
    'which', 'whereis', 'type', 'file',
    'echo', 'printf', 'printenv', 'env',
    'history', 'alias', 'help', 'man', 'info',
    'id', 'groups', 'hostname', 'hostnamectl',
    'awk', 'sed', 'cut', 'tr',
    'git status', 'git log', 'git diff', 'git branch', 'git show',
    'docker ps', 'docker images', 'docker logs', 'docker inspect',
    'kubectl get', 'kubectl describe', 'kubectl logs',
    'journalctl', 'dmesg',
    'systemctl status', 'systemctl list-units',
]

def split_compound_command(command: str) -> list[str]:
    parts = []
    current = []
    in_single = False
    in_double = False
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
        elif not in_single and not in_double:
            if ch == '&' and i + 1 < n and command[i+1] == '&':
                parts.append("".join(current).strip())
                current = []
                i += 1
            elif ch == '|' and i + 1 < n and command[i+1] == '|':
                parts.append("".join(current).strip())
                current = []
                i += 1
            elif ch == ';':
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]

def extract_executable(command: str) -> str:
    prefixes = ["sudo", "timeout", "nice", "ionice", "nohup", "setsid", "chroot", "flock", "stdbuf"]
    stripped = command.strip()
    while True:
        words = stripped.split()
        if not words:
            break
        if words[0] in prefixes:
            stripped = stripped[len(words[0]):].strip()
        else:
            break

    pipe_idx = -1
    in_single = False
    in_double = False
    for idx, ch in enumerate(stripped):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '|' and not in_single and not in_double:
            pipe_idx = idx
            break

    first_cmd = stripped[:pipe_idx].strip() if pipe_idx >= 0 else stripped
    match = re.match(r"^([a-zA-Z0-9_][a-zA-Z0-9_.-]*)", first_cmd)
    return match.group(1) if match else ""

def matches_pattern(command: str, pattern: str) -> bool:
    command_lower = command.lower().strip()
    pattern_lower = pattern.lower().strip()

    if "*" in pattern_lower:
        escaped = re.escape(pattern_lower).replace(r"\*", ".*")
        return bool(re.match(f"^{escaped}$", command_lower))

    escaped_pattern = re.escape(pattern_lower)
    if pattern_lower.endswith(" /") or pattern_lower.endswith(" / "):
        return bool(re.search(f"^{escaped_pattern}(\\s|$)", command_lower))

    return bool(re.search(f"(^|\\s){escaped_pattern}(\\s|$)", command_lower))

def is_read_only_command(command: str) -> bool:
    lower = command.lower().strip()
    return any(lower.startswith(c) for c in READONLY_COMMANDS)


class CommandSecurityService:
    @classmethod
    def evaluate_command(
        cls,
        command: str,
        mode: str = "agent",
        security_config: dict = None,
        auto_approval: dict = None,
    ) -> CommandSecurityResult:
        """
        Evaluate a shell command dynamically and return action/reason.
        """
        if security_config is None:
            security_config = DEFAULT_SECURITY_CONFIG
        if auto_approval is None:
            auto_approval = DEFAULT_AUTO_APPROVAL

        command = command.strip()
        if not command:
            return CommandSecurityResult("allow", "空命令")

        enable_command_security = security_config.get("enableCommandSecurity", True)
        if not enable_command_security:
            return CommandSecurityResult("allow", "安全检查已关闭")

        # Length check
        max_length = security_config.get("maxCommandLength", 10000)
        if len(command) > max_length:
            return CommandSecurityResult(
                "block",
                f"命令长度超过限制 ({max_length} 字符)",
                risk_level="medium",
                is_state_changing=False,
            )

        compounds = split_compound_command(command)

        # 1. Blacklist check
        blacklist_patterns = security_config.get("blacklistPatterns", [])
        for cmd in compounds:
            for pattern in blacklist_patterns:
                if matches_pattern(cmd, pattern):
                    ask_for_blacklist = security_config.get("securityPolicy", {}).get("askForBlacklist", False)
                    if ask_for_blacklist:
                        return CommandSecurityResult(
                            "ask",
                            f"命令命中了黑名单模式 '{pattern}'，策略已配置为人工确认。",
                            risk_level="critical",
                            is_state_changing=True,
                        )
                    else:
                        return CommandSecurityResult(
                            "block",
                            f"命令命中了阻断规则 '{pattern}'，已拦截该操作。",
                            risk_level="critical",
                            is_state_changing=True,
                        )

        # 2. Strict Mode Whitelist check
        enable_strict_mode = security_config.get("enableStrictMode", False)
        if enable_strict_mode:
            whitelist_patterns = security_config.get("whitelistPatterns", [])
            for cmd in compounds:
                exec_name = extract_executable(cmd)
                if not exec_name:
                    continue
                is_whitelisted = False
                for p in whitelist_patterns:
                    if matches_pattern(cmd, p) or exec_name.lower() == p.lower().split()[0]:
                        is_whitelisted = True
                        break
                if not is_whitelisted:
                    return CommandSecurityResult(
                        "block",
                        f"严格模式下禁止执行非白名单命令 '{exec_name}'。",
                        risk_level="medium",
                        is_state_changing=True,
                    )

        # 3. Dangerous command list check
        dangerous_commands = security_config.get("dangerousCommands", [])
        policy = security_config.get("securityPolicy", {})
        for cmd in compounds:
            exec_name = extract_executable(cmd).lower()
            if not exec_name:
                continue
            if exec_name in dangerous_commands or exec_name in DANGEROUS_COMMANDS_SEVERITY:
                info = DANGEROUS_COMMANDS_SEVERITY.get(exec_name, {"severity": "medium", "reason": "高风险命令"})
                severity = info["severity"]
                reason = info["reason"]

                # Check policy
                should_ask = True
                if severity == "critical":
                    should_ask = not policy.get("blockCritical", True)
                elif severity == "high":
                    should_ask = policy.get("askForHigh", True)
                elif severity == "medium":
                    should_ask = policy.get("askForMedium", True)

                if not should_ask:
                    return CommandSecurityResult(
                        "block",
                        f"命令 '{exec_name}' 属于高风险操作（{reason}），安全策略已配置为禁止执行。",
                        risk_level=severity,
                        is_state_changing=True,
                    )
                else:
                    # Check if auto-approval override applies
                    if mode == "agent" and auto_approval.get("enabled", False):
                        if auto_approval.get("actions", {}).get("executeAllCommands", False):
                            continue

                    return CommandSecurityResult(
                        "ask",
                        f"检测到高风险命令 '{exec_name}'（{reason}），需要人工确认。",
                        risk_level=severity,
                        is_state_changing=True,
                    )

        # 4. Standard auto-approval for safe commands
        if mode == "agent" and auto_approval.get("enabled", False):
            all_readonly = True
            for cmd in compounds:
                if not is_read_only_command(cmd):
                    all_readonly = False
                    break

            if all_readonly:
                if auto_approval.get("actions", {}).get("executeSafeCommands", True):
                    return CommandSecurityResult("allow", "命令属于安全只读操作，已自动批准执行。")
            else:
                if auto_approval.get("actions", {}).get("editFiles", False):
                    return CommandSecurityResult("allow", "自动执行写操作命令。")
                else:
                    return CommandSecurityResult(
                        "ask",
                        "命令包含写操作或修改状态，需用户授权。",
                        risk_level="medium",
                        is_state_changing=True,
                    )

        # In cmd mode, everything not blocked requires confirmation
        if mode == "cmd":
            # Determine risk level based on executable
            has_state_changing = False
            for cmd in compounds:
                exec_name = extract_executable(cmd).lower()
                if exec_name in DANGEROUS_COMMANDS_SEVERITY:
                    has_state_changing = True
                    break

            return CommandSecurityResult(
                "ask",
                "Command 模式下所有命令均需手动确认。",
                risk_level="medium" if has_state_changing else "low",
                is_state_changing=has_state_changing,
            )

        return CommandSecurityResult("allow", "命令安全，由 Agent 自动执行。")


security_service = CommandSecurityService()

