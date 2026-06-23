"""Command execution sandbox — multi-layer defense for bash/cmd tools.

L1: Environment variable whitelist
L2: Path reference prescan (safe_path for paths in command strings)
L3: Threat pattern detection (categorized, BLOCK vs WARN)
L4: OS-level sandbox (bwrap / sandbox-exec / Job Objects, silent degrade)

ContextVar injection via Container, same pattern as all other services.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from config.configs import WORKDIR
from utils.path_tools import safe_path

logger = logging.getLogger(__name__)

# ── default env whitelist ────────────────────────────────────

_DEFAULT_ENV_WHITELIST: set[str] = {
    "PATH", "HOME", "USER", "USERNAME",
    "TEMP", "TMP", "TMPDIR",
    "SYSTEMROOT", "SYSTEMDRIVE",   # Windows
    "SHELL",                        # Unix
    "LANG", "LC_ALL",              # locale
    "TERM",                         # terminal
}

if sys.platform == "win32":
    _DEFAULT_ENV_WHITELIST.update({
        "COMSPEC", "PATHEXT", "WINDIR",
        "ALLUSERSPROFILE", "APPDATA", "LOCALAPPDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)",
        "PROGRAMDATA", "CommonProgramFiles", "CommonProgramFiles(x86)",
    })


# ── threat patterns ──────────────────────────────────────────

class ThreatResult:
    """Result of threat detection."""
    def __init__(self, blocked: bool, rules: list[str]):
        self.blocked = blocked
        self.rules = rules

    def __bool__(self) -> bool:
        return self.blocked


# (pattern_regex, category, severity)
# severity: "BLOCK" or "WARN"
_THREAT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # ── BLOCK: file destruction ──
    (re.compile(r'\brm\s+(?:-[rRf]+\s+)*/'), "file-destruction", "BLOCK"),
    (re.compile(r'\brm\s+(?:-[rRf]+\s+)*\*'), "file-destruction", "BLOCK"),
    (re.compile(r'\bshred\b'), "file-destruction", "BLOCK"),
    (re.compile(r'\bwipe\b'), "file-destruction", "BLOCK"),
    (re.compile(r'\bdel\s+/[fF]\s+/[sS]'), "file-destruction", "BLOCK"),
    # ── BLOCK: system destruction ──
    (re.compile(r'\bmkfs\b'), "system-destruction", "BLOCK"),
    (re.compile(r'\bdd\s+if='), "system-destruction", "BLOCK"),
    (re.compile(r'>\s*/dev/sd'), "system-destruction", "BLOCK"),
    (re.compile(r'\bformat\s+[cdefgh]:'), "system-destruction", "BLOCK"),
    (re.compile(r'\bdiskpart\b'), "system-destruction", "BLOCK"),
    (re.compile(r'\bbcdedit\b'), "system-destruction", "BLOCK"),
    # ── BLOCK: information theft ──
    (re.compile(r'\bcurl\b.*\|\s*(?:bash|sh|python|perl)'), "info-theft", "BLOCK"),
    (re.compile(r'\bwget\b.*\|\s*(?:bash|sh|python|perl)'), "info-theft", "BLOCK"),
    (re.compile(r'/etc/(?:shadow|passwd|sudoers)'), "info-theft", "BLOCK"),
    (re.compile(r'\bwmic\s+diskdrive\b'), "info-theft", "BLOCK"),
    # ── WARN: path traversal (explicit) ──
    (re.compile(r'\bcd\s+/(?:etc|var|root|tmp|home|usr|opt|dev|proc|sys)\b'), "path-traversal", "WARN"),
    # ── WARN: resource abuse ──
    (re.compile(r':\(\)\s*\{\s*:\|:&\s*\}\s*;:'), "resource-abuse", "WARN"),
    (re.compile(r'\byes\s*>\s*/dev/'), "resource-abuse", "WARN"),
    (re.compile(r'\bwhile\s+true\s*;\s*do\b'), "resource-abuse", "WARN"),
    (re.compile(r'\bfor\s*\(\(.*;\s*;\s*;.*\)\)'), "resource-abuse", "WARN"),
]


class SandboxBlockedError(Exception):
    """Raised when a BLOCK-level threat is detected."""
    def __init__(self, rules: list[str]):
        self.rules = rules
        super().__init__(f"Blocked: {', '.join(rules)}")


# ── Sandbox ──────────────────────────────────────────────────

class Sandbox:
    """Multi-layer command execution sandbox."""

    def __init__(
        self,
        workdir: Path | None = None,
        env_whitelist: set[str] | None = None,
    ):
        self.workdir = Path(workdir) if workdir else WORKDIR
        self.env_whitelist = (
            env_whitelist if env_whitelist is not None
            else _DEFAULT_ENV_WHITELIST
        )

    # ── L4: OS sandbox ──────────────────────────────────────

    @staticmethod
    def _find_bwrap() -> str | None:
        """Locate bwrap (bubblewrap) binary. Returns path or None."""
        return shutil.which("bwrap")

    @staticmethod
    def _find_sandbox_exec() -> str | None:
        """macOS sandbox-exec availability."""
        return shutil.which("sandbox-exec")

    def os_sandbox_available(self) -> str | None:
        """Check which OS sandbox is available.

        Returns 'bwrap', 'sandbox-exec', 'jobobject', or None.
        """
        if sys.platform == "linux" and self._find_bwrap():
            return "bwrap"
        if sys.platform == "darwin" and self._find_sandbox_exec():
            return "sandbox-exec"
        if sys.platform == "win32":
            return "jobobject"  # always available via subprocess flags
        return None

    def wrap_command(self, command: str) -> tuple[str, dict[str, str]]:
        """Wrap command with OS-level sandbox if available.

        Returns (wrapped_command, extra_subprocess_kwargs).
        Silent degrade: returns (command, {}) when unavailable.
        """
        sandbox = self.os_sandbox_available()

        if sandbox == "bwrap":
            wrapped = (
                f"bwrap "
                f"--ro-bind /usr /usr "
                f"--ro-bind /bin /bin "
                f"--ro-bind /lib /lib "
                f"--ro-bind /lib64 /lib64 "
                f"--ro-bind /sbin /sbin "
                f"--bind {self.workdir} {self.workdir} "
                f"--dev /dev "
                f"--proc /proc "
                f"--chdir {self.workdir} "
                f"--unshare-all "
                f"-- {command}"
            )
            return wrapped, {}

        elif sandbox == "sandbox-exec":
            profile = (
                f'(version 1)\n'
                f'(allow default)\n'
                f'(deny file-write* (subpath "/"))\n'
                f'(allow file-write* (subpath "{self.workdir}"))\n'
            )
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".sb", delete=False, prefix="sandbox_"
            )
            try:
                tmp.write(profile)
                tmp.close()
                wrapped = f"sandbox-exec -f {tmp.name} -- {command}"
                return wrapped, {}
            except Exception:
                return command, {}

        elif sandbox == "jobobject":
            # Windows: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
            return command, {
                "creationflags": (
                    0x00000200 |  # CREATE_NEW_PROCESS_GROUP
                    0x00000008    # DETACHED_PROCESS (no console)
                )
            }

        return command, {}

    # ── L1: environment sanitization ─────────────────────────

    def build_safe_env(self) -> dict[str, str]:
        """Clear all inherited env vars, keep only whitelisted ones.

        HOME is overridden to workdir.
        """
        safe: dict[str, str] = {}
        for key in self.env_whitelist:
            value = os.environ.get(key)
            if value is not None:
                safe[key] = value
        # HOME = workdir (prevent access to user home)
        safe["HOME"] = str(self.workdir)
        return safe

    # ── L2: path prescan ─────────────────────────────────────

    def prescan_paths(self, command: str) -> list[str]:
        """Extract path-like strings from command and validate with safe_path.

        Returns list of violating paths (empty = all clear).
        """
        violations: list[str] = []
        path_candidates: set[str] = set()

        # Absolute Unix paths
        for m in re.finditer(r'(?<!\w)/(?:[a-zA-Z0-9._-]+/)*[a-zA-Z0-9._-]+', command):
            path_candidates.add(m.group())

        # Absolute Windows paths
        for m in re.finditer(r'[a-zA-Z]:\\(?:[a-zA-Z0-9._ -]+\\)*[a-zA-Z0-9._ -]*', command):
            path_candidates.add(m.group())

        # ../ and ..\ patterns (relative traversal)
        for m in re.finditer(r'(?:\.\./)+[a-zA-Z0-9._-]*', command):
            path_candidates.add(m.group())
        for m in re.finditer(r'(?:\.\.\\)+[a-zA-Z0-9._ -]*', command):
            path_candidates.add(m.group())

        # $HOME, $TMP, %USERPROFILE% etc.
        # Match $VAR/path/... or $VAR (non-greedy, stop at whitespace/semicolons)
        for m in re.finditer(r'\$(?:HOME|TMP|TMPDIR|TMPDIR)(?:/[^\s;|&]*)?', command):
            path_candidates.add(m.group())
        for m in re.finditer(r'%(?:USERPROFILE|APPDATA|LOCALAPPDATA|TEMP|TMP)%(?:\\[^\s;|&]*)?', command):
            path_candidates.add(m.group())

        for candidate in path_candidates:
            try:
                safe_path(candidate)
            except ValueError:
                violations.append(candidate)

        return violations

    # ── L3: threat detection ─────────────────────────────────

    def detect_threats(self, command: str) -> ThreatResult:
        """Run command through categorized threat patterns.

        Returns ThreatResult with blocked flag and matched rule names.
        """
        matched_block: list[str] = []
        matched_warn: list[str] = []
        for pattern, category, severity in _THREAT_PATTERNS:
            if pattern.search(command):
                if severity == "BLOCK":
                    matched_block.append(f"{category}:{severity}")
                else:
                    matched_warn.append(f"{category}:{severity}")
        if matched_block:
            return ThreatResult(blocked=True, rules=matched_block)
        return ThreatResult(blocked=False, rules=matched_warn)

    # ── combined sanitization ────────────────────────────────

    def sanitize(
        self, command: str
    ) -> tuple[str, dict[str, str], list[str], dict]:
        """Run L1→L4.

        Returns:
            (safe_command, safe_env, warnings, extra_subprocess_kwargs)
        Raises:
            SandboxBlockedError if BLOCK-level threat detected.
        """
        warnings: list[str] = []

        # L1: environment
        safe_env = self.build_safe_env()

        # L2: path prescan
        path_violations = self.prescan_paths(command)
        for v in path_violations:
            warnings.append(f"path violation: {v}")

        # L3: threat detection
        threat = self.detect_threats(command)
        for r in threat.rules:
            if "BLOCK" in r:
                raise SandboxBlockedError([r])
            warnings.append(f"threat detected: {r}")

        # L4: OS sandbox
        safe_command, extra_kwargs = self.wrap_command(command)
        if safe_command != command:
            warnings.append(f"os-sandbox: wrapped with {self.os_sandbox_available()}")

        return safe_command, safe_env, warnings, extra_kwargs
