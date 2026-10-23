"""Kernel namespace availability probe for scoped-command security tests.

Scoped-command tests execute real bash in kernel namespaces (user+mount
isolation). CI runners and containerized environments commonly deny
unprivileged user namespaces (Docker's default seccomp profile, hardened
apparmor), so these security-boundary tests skip there rather than fail.
"""

import subprocess

import pytest


def namespaces_available() -> bool:
    try:
        result = subprocess.run(
            ["unshare", "--user", "--map-root-user", "--mount", "true"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


requires_namespaces = pytest.mark.skipif(
    not namespaces_available(),
    reason="kernel user+mount namespaces unavailable (containerized/CI environment)",
)
