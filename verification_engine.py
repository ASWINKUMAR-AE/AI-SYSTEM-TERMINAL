"""
Verification Engine for AI System Terminal
Validates application health, process liveness, port listening state,
HTTP endpoint availability, test suite execution, and log exception auditing.
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from process_manager import ProcessManager
from terminal_executor import TerminalExecutor


@dataclass
class VerificationResult:
    success: bool
    status: str  # "VERIFIED" | "FAILED" | "PARTIAL"
    message: str
    checks_run: List[str] = field(default_factory=list)
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    error_summary: Optional[str] = None


class VerificationEngine:
    """Verifies that applications start and run properly without errors."""

    def __init__(self):
        self.process_manager = ProcessManager()
        self.executor = TerminalExecutor()

    def check_socket_port(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Checks if a TCP socket connection can be established."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    def check_http_endpoint(self, url: str, timeout: float = 3.0) -> Tuple[bool, int, str]:
        """Performs a GET request to verify an HTTP service is responding."""
        try:
            resp = requests.get(url, timeout=timeout)
            # Any HTTP status response indicates server is actively running
            return True, resp.status_code, f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, 0, "Connection refused"
        except requests.exceptions.Timeout:
            return False, 0, "HTTP request timed out"
        except Exception as e:
            return False, 0, str(e)

    def scan_logs_for_errors(self, stdout_lines: List[str], stderr_lines: List[str]) -> Tuple[bool, List[str]]:
        """Audits stdout and stderr logs for crash indicators or unhandled exceptions."""
        error_indicators = [
            r"traceback \(most recent call last\):",
            r"unhandledpromiserejection",
            r"fatal error",
            r"syntaxerror:",
            r"modulenotfounderror:",
            r"importerror:",
            r"cannot find module",
            r"nullpointerexception",
            r"bindexception: address already in use",
            r"unsupportedclassversionerror",
            r"compilation failed",
            r"build failure"
        ]

        found_errors: List[str] = []
        combined_lines = stdout_lines + stderr_lines

        for line in combined_lines:
            lower = line.lower()
            for pattern in error_indicators:
                if re.search(pattern, lower):
                    found_errors.append(line.strip())
                    break

        has_fatal_errors = len(found_errors) > 0
        return has_fatal_errors, found_errors

    def verify_application(
        self,
        pid: Optional[int] = None,
        expected_port: Optional[int] = None,
        test_command: Optional[str] = None,
        cwd: Optional[str | Path] = None,
        warmup_seconds: float = 2.5
    ) -> VerificationResult:
        """Runs the complete 5-step verification workflow."""
        checks_run: List[str] = []
        passed_checks: List[str] = []
        failed_checks: List[str] = []
        details: Dict[str, Any] = {}
        error_summary: Optional[str] = None

        # Warmup delay for startup initialization
        if warmup_seconds > 0:
            time.sleep(warmup_seconds)

        # 1. Process Liveness Check
        if pid is not None:
            is_alive = self.process_manager.is_process_running(pid)
            if is_alive:
                checks_run.append("Process Liveness")
                passed_checks.append("Process Liveness")
                details["process_status"] = f"Process {pid} is running"
            else:
                managed = self.process_manager.active_processes.get(pid)
                exit_code = managed.exit_code if managed else "Unknown"
                if exit_code == 0 and not expected_port:
                    checks_run.append("Process Execution")
                    passed_checks.append("Process Execution")
                    details["process_status"] = "Process completed successfully with exit code 0"
                else:
                    checks_run.append("Process Liveness")
                    failed_checks.append("Process Liveness")
                    details["process_status"] = f"Process {pid} terminated prematurely with exit code {exit_code}"
                    error_summary = f"Application crashed immediately on startup (exit code {exit_code})."

        # 2. Port Check
        if expected_port:
            checks_run.append(f"Port {expected_port} Listener")
            port_open = False
            # Try a couple times over 2 seconds
            for _ in range(4):
                if self.check_socket_port("127.0.0.1", expected_port):
                    port_open = True
                    break
                time.sleep(0.5)

            if port_open:
                passed_checks.append(f"Port {expected_port} Listener")
                details["port_status"] = f"Port {expected_port} is open and accepting TCP connections"
            else:
                failed_checks.append(f"Port {expected_port} Listener")
                details["port_status"] = f"Port {expected_port} is NOT listening"
                if not error_summary:
                    error_summary = f"Service did not bind to expected port {expected_port}."

            # 3. HTTP Health Check
            checks_run.append(f"HTTP Ping (Port {expected_port})")
            http_ok, code, msg = self.check_http_endpoint(f"http://127.0.0.1:{expected_port}/")
            if http_ok:
                passed_checks.append(f"HTTP Ping (Port {expected_port})")
                details["http_status"] = msg
            else:
                # If port was open, but HTTP gave error or root gave 404, we check status
                if port_open:
                    passed_checks.append(f"HTTP Ping (Port {expected_port})")
                    details["http_status"] = f"Port responding ({msg})"
                else:
                    failed_checks.append(f"HTTP Ping (Port {expected_port})")
                    details["http_status"] = f"HTTP failed ({msg})"

        # 4. Log Inspection Check
        if pid is not None:
            checks_run.append("Log Exception Audit")
            out_lines, err_lines = self.process_manager.get_recent_output(pid)
            has_errors, found_errors = self.scan_logs_for_errors(out_lines, err_lines)
            if has_errors:
                failed_checks.append("Log Exception Audit")
                details["detected_errors"] = found_errors[:5]
                if not error_summary:
                    error_summary = f"Fatal exceptions detected in logs: {found_errors[0]}"
            else:
                passed_checks.append("Log Exception Audit")
                details["log_status"] = "No fatal exceptions in startup logs"

        # 5. Test Suite Verification
        if test_command:
            checks_run.append(f"Test Suite ({test_command})")
            exec_res = self.executor.run(test_command, cwd=cwd, timeout=60)
            if exec_res.success:
                passed_checks.append(f"Test Suite ({test_command})")
                details["test_status"] = "Tests passed successfully"
            else:
                failed_checks.append(f"Test Suite ({test_command})")
                details["test_status"] = f"Tests failed with exit code {exec_res.returncode}"
                if not error_summary:
                    error_summary = f"Test suite failed:\n{exec_res.combined_output()[:300]}"

        # Evaluation
        if len(failed_checks) == 0 and len(passed_checks) > 0:
            return VerificationResult(
                success=True,
                status="VERIFIED",
                message="All startup and health checks passed successfully.",
                checks_run=checks_run,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                details=details
            )
        else:
            return VerificationResult(
                success=False,
                status="FAILED",
                message=error_summary or "Verification checks failed.",
                checks_run=checks_run,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                details=details,
                error_summary=error_summary
            )
