"""
Environment Scanner for AI System Terminal
Gathers ground-truth system evidence: runtimes (Python, Java, Node, PHP),
build tools, package managers, git repos, active ports, processes, and environment variables.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil


class EnvironmentScanner:
    """Scans the local Windows workstation to discover developer tools and active state."""

    def __init__(self):
        pass

    def run_cmd_quick(self, cmd: List[str], timeout: int = 5) -> Tuple[int, str, str]:
        """Runs a quick command and returns (returncode, stdout, stderr)."""
        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False
            )
            return p.returncode, p.stdout.strip(), p.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    def scan_python(self) -> Dict[str, Any]:
        """Scans Python environments, virtual environments, and package managers."""
        py_info: Dict[str, Any] = {
            "current_executable": sys.executable,
            "current_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "in_virtualenv": hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix),
            "virtual_env_path": os.environ.get("VIRTUAL_ENV"),
            "pip_available": False,
            "uv_available": False,
            "poetry_available": False,
            "conda_available": False
        }

        # Check pip
        rc, out, _ = self.run_cmd_quick([sys.executable, "-m", "pip", "--version"])
        if rc == 0:
            py_info["pip_available"] = True
            py_info["pip_version"] = out.split()[1] if len(out.split()) > 1 else out

        # Check uv
        if shutil.which("uv"):
            py_info["uv_available"] = True
            rc, out, _ = self.run_cmd_quick(["uv", "--version"])
            py_info["uv_version"] = out

        # Check poetry
        if shutil.which("poetry"):
            py_info["poetry_available"] = True

        # Check conda
        if shutil.which("conda"):
            py_info["conda_available"] = True

        return py_info

    def scan_java(self) -> Dict[str, Any]:
        """Scans Java JDK, JRE, javac, JAVA_HOME, Maven, Gradle."""
        java_info: Dict[str, Any] = {
            "java_installed": False,
            "javac_installed": False,
            "java_home": os.environ.get("JAVA_HOME"),
            "maven_installed": False,
            "gradle_installed": False
        }

        # Check java
        rc, out, err = self.run_cmd_quick(["java", "-version"])
        # java -version outputs to stderr
        version_str = err or out
        if rc == 0 or "version" in version_str.lower():
            java_info["java_installed"] = True
            first_line = version_str.splitlines()[0] if version_str.splitlines() else version_str
            java_info["java_version"] = first_line

        # Check javac
        rc, out, err = self.run_cmd_quick(["javac", "-version"])
        if rc == 0:
            java_info["javac_installed"] = True
            java_info["javac_version"] = (out or err).strip()

        # Check maven
        rc, out, _ = self.run_cmd_quick(["mvn.cmd" if os.name == "nt" else "mvn", "-v"])
        if rc == 0:
            java_info["maven_installed"] = True
            java_info["maven_version"] = out.splitlines()[0] if out.splitlines() else out

        # Check gradle
        rc, out, _ = self.run_cmd_quick(["gradle.bat" if os.name == "nt" else "gradle", "-v"])
        if rc == 0:
            java_info["gradle_installed"] = True
            java_info["gradle_version"] = out.splitlines()[0] if out.splitlines() else out

        return java_info

    def scan_node(self) -> Dict[str, Any]:
        """Scans Node.js, npm, pnpm, yarn, bun."""
        node_info: Dict[str, Any] = {
            "node_installed": False,
            "npm_installed": False,
            "pnpm_installed": False,
            "yarn_installed": False,
            "bun_installed": False
        }

        rc, out, _ = self.run_cmd_quick(["node", "-v"])
        if rc == 0:
            node_info["node_installed"] = True
            node_info["node_version"] = out

        rc, out, _ = self.run_cmd_quick(["npm.cmd" if os.name == "nt" else "npm", "-v"])
        if rc == 0:
            node_info["npm_installed"] = True
            node_info["npm_version"] = out

        if shutil.which("pnpm") or shutil.which("pnpm.cmd"):
            node_info["pnpm_installed"] = True
        if shutil.which("yarn") or shutil.which("yarn.cmd"):
            node_info["yarn_installed"] = True
        if shutil.which("bun") or shutil.which("bun.cmd"):
            node_info["bun_installed"] = True

        return node_info

    def scan_php(self) -> Dict[str, Any]:
        """Scans PHP and Composer."""
        php_info: Dict[str, Any] = {
            "php_installed": False,
            "composer_installed": False
        }

        rc, out, _ = self.run_cmd_quick(["php", "-v"])
        if rc == 0:
            php_info["php_installed"] = True
            php_info["php_version"] = out.splitlines()[0] if out.splitlines() else out

        rc, out, _ = self.run_cmd_quick(["composer.bat" if os.name == "nt" else "composer", "-V"])
        if rc == 0:
            php_info["composer_installed"] = True
            php_info["composer_version"] = out.splitlines()[0] if out.splitlines() else out

        return php_info

    def scan_git(self, cwd: Optional[str | Path] = None) -> Dict[str, Any]:
        """Scans Git installation and repo status."""
        git_info: Dict[str, Any] = {
            "git_installed": False,
            "is_repo": False,
            "branch": None,
            "clean": True
        }

        rc, out, _ = self.run_cmd_quick(["git", "--version"])
        if rc == 0:
            git_info["git_installed"] = True
            git_info["git_version"] = out

        target_dir = cwd or os.getcwd()
        try:
            p = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            if p.returncode == 0:
                git_info["is_repo"] = True
                lines = p.stdout.strip().splitlines()
                if lines:
                    branch_line = lines[0]
                    if branch_line.startswith("## "):
                        git_info["branch"] = branch_line[3:].split("...")[0]
                    git_info["clean"] = (len(lines) == 1)
        except Exception:
            pass

        return git_info

    def scan_active_ports(self, common_ports: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Scans common development and database ports for active listeners."""
        if not common_ports:
            common_ports = [80, 443, 3000, 3001, 3306, 5000, 5173, 5432, 6379, 8000, 8080, 8443, 9000]

        active: List[Dict[str, Any]] = []
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr and conn.laddr.port in common_ports:
                    proc_name = "Unknown"
                    if conn.pid:
                        try:
                            proc = psutil.Process(conn.pid)
                            proc_name = proc.name()
                        except Exception:
                            pass
                    active.append({
                        "port": conn.laddr.port,
                        "ip": conn.laddr.ip,
                        "pid": conn.pid,
                        "process_name": proc_name
                    })
        except Exception:
            # Fallback to socket test if psutil net_connections has permission error
            for port in common_ports:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        active.append({
                            "port": port,
                            "ip": "127.0.0.1",
                            "pid": None,
                            "process_name": "Active listener"
                        })
        return active

    def scan_all(self, cwd: Optional[str | Path] = None) -> Dict[str, Any]:
        """Performs a comprehensive scan of the local environment."""
        return {
            "python": self.scan_python(),
            "java": self.scan_java(),
            "node": self.scan_node(),
            "php": self.scan_php(),
            "git": self.scan_git(cwd),
            "active_ports": self.scan_active_ports(),
            "os": {
                "system": os.name,
                "platform": sys.platform,
                "cwd": str(Path(cwd).resolve()) if cwd else os.getcwd()
            }
        }
