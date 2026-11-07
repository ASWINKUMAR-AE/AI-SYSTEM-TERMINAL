"""
Vireonix AI Client for AI System Terminal
Handles communication with the Vireonix AI API, conversation persistence,
exponential backoff retries, JSON parsing, and specialized diagnosis prompts.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from config import get_history_path, load_config


class VireonixClient:
    """Robust client for the Vireonix AI chat completions API."""

    def __init__(self, api_url: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None):
        self.config = load_config()
        self.api_url = api_url or self.config.get("api_url", "https://vireonix.ai/v1/chat/completions")
        self.model = model or self.config.get("model", "auto")
        self.api_key = api_key or self.config.get("api_key", "")
        self.timeout = self.config.get("timeout", 60)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1.5)
        self.session = requests.Session()

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-System-Terminal/1.0"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def test_connection(self) -> Tuple[bool, str]:
        """Tests connectivity with the Vireonix AI API using retries."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}]
        }
        last_err = ""
        delay = self.retry_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(
                    self.api_url,
                    json=payload,
                    headers=self._build_headers(),
                    timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    return True, f"Connection successful! Response: '{content}'"
                
                last_err = f"Status {resp.status_code}: {resp.text[:150]}"
                if resp.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                return False, last_err
            except Exception as e:
                last_err = str(e)
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                return False, f"Connection failed: {last_err}"

        return False, f"Connection failed after {self.max_retries} attempts: {last_err}"

    def send_messages(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_retries: Optional[int] = None
    ) -> str:
        """Sends a full list of messages to Vireonix AI with exponential backoff retries."""
        retries = max_retries if max_retries is not None else self.max_retries
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }

        last_error = ""
        current_delay = self.retry_delay

        for attempt in range(1, retries + 1):
            try:
                resp = self.session.post(
                    self.api_url,
                    json=payload,
                    headers=self._build_headers(),
                    timeout=self.timeout
                )

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"].get("content", "")
                    return ""

                # Handle transient 500, 502, 503, 504 errors
                if resp.status_code in (500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text[:150]}"
                    if attempt < retries:
                        time.sleep(current_delay)
                        current_delay *= 2
                        continue

                # Unrecoverable 4xx error
                raise RuntimeError(f"Vireonix AI API error {resp.status_code}: {resp.text}")

            except (requests.Timeout, requests.ConnectionError) as conn_err:
                last_error = f"Network error ({conn_err.__class__.__name__}): {conn_err}"
                if attempt < retries:
                    time.sleep(current_delay)
                    current_delay *= 2
                    continue
                break
            except Exception as e:
                raise RuntimeError(f"Failed to communicate with Vireonix AI API: {e}")

        raise RuntimeError(
            f"Vireonix AI API request failed after {retries} attempts. Last error: {last_error}"
        )

    def chat(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        use_history: bool = True
    ) -> str:
        """Sends a chat prompt, managing system prompt and persistent history."""
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            default_sys = (
                "You are an expert AI Systems Engineer and Autonomous Terminal Assistant integrated into Windows PowerShell. "
                "Provide direct, concise, practical answers with markdown and copy-pasteable commands or code."
            )
            messages.append({"role": "system", "content": default_sys})

        if use_history:
            history = self.load_history()
            messages.extend(history)

        messages.append({"role": "user", "content": user_prompt})

        response_text = self.send_messages(messages)

        if use_history and response_text:
            self.append_history("user", user_prompt)
            self.append_history("assistant", response_text)

        return response_text

    def diagnose_error(
        self,
        error_log: str,
        project_context: Dict[str, Any],
        system_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Asks Vireonix AI to diagnose an error and return a structured JSON diagnosis."""
        system_prompt = (
            "You are a master software debugger and DevOps agent. "
            "Analyze the given error log, project context, and system environment. "
            "You MUST respond ONLY with a valid JSON object matching the requested schema. "
            "Do NOT wrap with prose outside the JSON. "
            "JSON Schema:\n"
            "{\n"
            '  "root_cause": "concise description of what failed",\n'
            '  "explanation": "clear explanation for developer",\n'
            '  "error_type": "Dependency | Syntax | PortConflict | Config | Runtime | Classpath | Environment",\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "smallest_fix_description": "short summary of the minimal reliable fix",\n'
            '  "required_actions": [\n'
            "    {\n"
            '      "action_type": "install_dependency | edit_file | run_command | kill_port",\n'
            '      "target": "file path, package name, or command",\n'
            '      "details": "exact change or instructions"\n'
            "    }\n"
            "  ],\n"
            '  "validation_commands": ["command to verify fix"]\n'
            "}"
        )

        user_content = (
            f"=== ERROR LOG / STACK TRACE ===\n{error_log[:4000]}\n\n"
            f"=== PROJECT CONTEXT ===\n{json.dumps(project_context, indent=2)}\n\n"
            f"=== SYSTEM CONTEXT ===\n{json.dumps(system_context, indent=2)}\n\n"
            "Diagnose the root cause and provide the minimal reliable fix in the required JSON format."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        raw = self.send_messages(messages, temperature=0.1)
        return self._extract_json(raw, fallback_error=error_log)

    def generate_file_fix(
        self,
        file_path: str,
        current_content: str,
        error_context: str,
        fix_description: str
    ) -> str:
        """Asks Vireonix AI to fix a specific source or configuration file."""
        system_prompt = (
            "You are an automated software repair engine. Your job is to output the corrected version of the file. "
            "Output ONLY the complete, corrected file contents inside a single code block. "
            "Do not include conversational filler."
        )

        user_content = (
            f"File to repair: {file_path}\n"
            f"Issue / Fix required: {fix_description}\n"
            f"Related Error:\n{error_context[:2000]}\n\n"
            f"Current file content:\n```\n{current_content}\n```\n\n"
            "Return the entire corrected file content inside ```...```."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        raw = self.send_messages(messages, temperature=0.1)
        return self._extract_code_block(raw) or raw.strip()

    def _extract_json(self, text: str, fallback_error: str = "") -> Dict[str, Any]:
        """Extracts JSON object from text, handling markdown blocks."""
        text_clean = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_clean)
        candidate = match.group(1).strip() if match else text_clean

        # Find first { and last }
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1:
            candidate = candidate[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            # Fallback structure
            return {
                "root_cause": "Error detected in application execution",
                "explanation": text[:500] if text else "Failed to parse AI diagnosis",
                "error_type": "Runtime",
                "confidence": 0.5,
                "smallest_fix_description": "Review and correct application error",
                "required_actions": [],
                "validation_commands": []
            }

    def _extract_code_block(self, text: str) -> Optional[str]:
        """Extracts content from a markdown code block."""
        match = re.search(r"```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```", text)
        if match:
            return match.group(1)
        match_simple = re.search(r"```([\s\S]*?)```", text)
        if match_simple:
            return match_simple.group(1).strip()
        return None

    def load_history(self) -> List[Dict[str, str]]:
        """Loads conversation history from history.json."""
        hist_path = get_history_path()
        if not hist_path.exists():
            return []
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    limit = self.config.get("history_limit", 25)
                    return data[-limit:]
        except Exception:
            pass
        return []

    def append_history(self, role: str, content: str) -> None:
        """Appends a message to conversation history."""
        hist_path = get_history_path()
        history = self.load_history()
        history.append({"role": role, "content": content})
        limit = self.config.get("history_limit", 25)
        history = history[-limit:]
        try:
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

    def clear_history(self) -> None:
        """Clears conversation history."""
        hist_path = get_history_path()
        if hist_path.exists():
            try:
                hist_path.unlink()
            except Exception:
                pass
