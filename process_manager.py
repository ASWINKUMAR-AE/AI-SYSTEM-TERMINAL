"""
Process Manager for AI System Terminal
Launches, monitors, tracks background application processes, inspects active ports,
and cleanly terminates processes and their child trees.
"""

from __future__ import annotations

import collections
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil


@dataclass
class ManagedProcess:
    pid: int
    command: str
    cwd: str
    start_time: float
    process: subprocess.Popen
    stdout_buffer: collections.deque = field(default_factory=lambda: collections.deque(maxlen=500))
    stderr_buffer: collections.deque = field(default_factory=lambda: collections.deque(maxlen=500))
    is_alive: bool = True
    exit_code: Optional[int] = None


class ProcessManager:
    """Manages background development servers and application processes."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active_processes: Dict[int, ManagedProcess] = {}
        return cls._instance

    def spawn_process(
        self,
        command: str,
        cwd: Optional[str | Path] = None,
        env: Optional[Dict[str, str]] = None,
        shell: str = "powershell"
    ) -> ManagedProcess:
        """Starts an application command in the background and attaches output listeners."""
        target_cwd = str(Path(cwd).resolve()) if cwd else os.getcwd()
        cmd_env = dict(os.environ)
        if env:
            cmd_env.update(env)

        if shell.lower() in ("cmd", "batch"):
            cmd_args = ["cmd.exe", "/c", command]
        else:
            ps_cmd = command.strip()
            if ps_cmd.startswith('"') and not ps_cmd.startswith('&'):
                ps_cmd = f"& {ps_cmd}"
            cmd_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]

        proc = subprocess.Popen(
            cmd_args,
            cwd=target_cwd,
            env=cmd_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

        managed = ManagedProcess(
            pid=proc.pid,
            command=command,
            cwd=target_cwd,
            start_time=time.time(),
            process=proc
        )

        # Thread to drain stdout
        def _read_stdout():
            try:
                for line in iter(proc.stdout.readline, ""):
                    managed.stdout_buffer.append(line.rstrip("\r\n"))
                proc.stdout.close()
            except Exception:
                pass

        # Thread to drain stderr
        def _read_stderr():
            try:
                for line in iter(proc.stderr.readline, ""):
                    managed.stderr_buffer.append(line.rstrip("\r\n"))
                proc.stderr.close()
            except Exception:
                pass

        t_out = threading.Thread(target=_read_stdout, daemon=True)
        t_err = threading.Thread(target=_read_stderr, daemon=True)
        t_out.start()
        t_err.start()

        self.active_processes[proc.pid] = managed
        return managed

    def is_process_running(self, pid: int) -> bool:
        """Checks if a managed PID is actively running."""
        managed = self.active_processes.get(pid)
        if not managed:
            try:
                return psutil.pid_exists(pid)
            except Exception:
                return False

        poll = managed.process.poll()
        if poll is None:
            managed.is_alive = True
            return True
        else:
            managed.is_alive = False
            managed.exit_code = poll
            return False

    def get_recent_output(self, pid: int, lines: int = 50) -> Tuple[List[str], List[str]]:
        """Returns recent stdout and stderr lines for a process."""
        managed = self.active_processes.get(pid)
        if not managed:
            return [], []
        # Brief pause to allow reading threads to flush if process just died
        time.sleep(0.1)
        out = list(managed.stdout_buffer)[-lines:]
        err = list(managed.stderr_buffer)[-lines:]
        return out, err

    def terminate_process(self, pid: int, timeout: int = 5) -> bool:
        """Terminates a process and its child tree."""
        try:
            # On Windows, taskkill /F /T terminates process and all child processes
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=timeout
                )
            else:
                p = psutil.Process(pid)
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()

            if pid in self.active_processes:
                self.active_processes[pid].is_alive = False
            return True
        except Exception:
            return False

    def find_process_on_port(self, port: int) -> Optional[Dict[str, Any]]:
        """Finds PID and name of process currently listening on given port."""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr and conn.laddr.port == port:
                    pid = conn.pid
                    name = "Unknown"
                    if pid:
                        try:
                            name = psutil.Process(pid).name()
                        except Exception:
                            pass
                    return {"port": port, "pid": pid, "name": name}
        except Exception:
            pass
        return None

    def kill_process_on_port(self, port: int) -> bool:
        """Finds and terminates process listening on the specified port."""
        proc_info = self.find_process_on_port(port)
        if proc_info and proc_info.get("pid"):
            return self.terminate_process(proc_info["pid"])
        return False
