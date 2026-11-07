"""
Terminal Execution Engine for AI System Terminal
Safely executes PowerShell and CMD commands with streaming, timeout control,
exit code tracking, and execution history logging.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import get_execution_log_path


@dataclass
class ExecutionResult:
    command: str
    shell: str
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool = False
    success: bool = False

    def combined_output(self) -> str:
        out = self.stdout.strip()
        err = self.stderr.strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err


class TerminalExecutor:
    """Executes commands through controlled subprocesses."""

    def __init__(self, default_shell: str = "powershell"):
        self.default_shell = default_shell

    def _get_shell_cmd(self, command: str, shell: str) -> List[str]:
        """Builds subprocess command arguments for the specified shell."""
        if shell.lower() in ("cmd", "batch"):
            return ["cmd.exe", "/c", command]
        else:
            ps_cmd = command.strip()
            # If executable is quoted, PowerShell requires & call operator
            if ps_cmd.startswith('"') and not ps_cmd.startswith('&'):
                ps_cmd = f"& {ps_cmd}"
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-Command", ps_cmd
            ]

    def run(
        self,
        command: str,
        cwd: Optional[str | Path] = None,
        timeout: int = 120,
        shell: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        output_callback: Optional[Callable[[str], None]] = None
    ) -> ExecutionResult:
        """Executes a command and returns an ExecutionResult."""
        target_shell = shell or self.default_shell
        target_cwd = str(Path(cwd).resolve()) if cwd else os.getcwd()
        full_cmd = self._get_shell_cmd(command, target_shell)

        cmd_env = dict(os.environ)
        # Ensure utf-8 encoding in powershell
        cmd_env["PYTHONIOENCODING"] = "utf-8"
        if env:
            cmd_env.update(env)

        start_time = time.time()
        timed_out = False
        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        try:
            process = subprocess.Popen(
                full_cmd,
                cwd=target_cwd,
                env=cmd_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False
            )

            # If callback is provided, read stdout line by line
            if output_callback and process.stdout:
                for line in iter(process.stdout.readline, ""):
                    stdout_chunks.append(line)
                    try:
                        output_callback(line)
                    except Exception:
                        pass
                process.stdout.close()
                _, stderr_data = process.communicate(timeout=max(5, timeout - int(time.time() - start_time)))
                if stderr_data:
                    stderr_chunks.append(stderr_data)
            else:
                stdout_data, stderr_data = process.communicate(timeout=timeout)
                if stdout_data:
                    stdout_chunks.append(stdout_data)
                if stderr_data:
                    stderr_chunks.append(stderr_data)

            returncode = process.returncode

        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            try:
                out_rem, err_rem = process.communicate(timeout=3)
                if out_rem:
                    stdout_chunks.append(out_rem)
                if err_rem:
                    stderr_chunks.append(err_rem)
            except Exception:
                pass
            returncode = -1
            stderr_chunks.append(f"\n[Command timed out after {timeout} seconds]")

        except Exception as e:
            returncode = -1
            stderr_chunks.append(f"\n[Execution error: {e}]")

        duration = time.time() - start_time
        stdout_str = "".join(stdout_chunks)
        stderr_str = "".join(stderr_chunks)
        success = (returncode == 0) and not timed_out

        result = ExecutionResult(
            command=command,
            shell=target_shell,
            cwd=target_cwd,
            returncode=returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_sec=round(duration, 2),
            timed_out=timed_out,
            success=success
        )

        self._log_execution(result)
        return result

    def _log_execution(self, result: ExecutionResult) -> None:
        """Appends command result to execution_log.json."""
        try:
            log_path = get_execution_log_path()
            entries: List[Dict] = []
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                        if not isinstance(entries, list):
                            entries = []
                except Exception:
                    entries = []

            # Keep last 100 entries
            entries.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "command": result.command,
                "shell": result.shell,
                "cwd": result.cwd,
                "returncode": result.returncode,
                "duration_sec": result.duration_sec,
                "timed_out": result.timed_out,
                "success": result.success,
                "output_preview": result.combined_output()[:200]
            })
            entries = entries[-100:]

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
        except Exception:
            pass
