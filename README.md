# ZetHub — Autonomous AI System Terminal & Error Fixer
### Powered by zethub

A production-grade, globally accessible AI-powered system terminal manager and autonomous debugger integrated directly into Windows PowerShell and CMD. It understands natural-language requests, executes controlled commands, analyzes stack traces, generates targeted patches, applies safe fixes with rollback checkpoints, and verifies application stability.

---

## Architecture Overview

```text
ai-terminal/
├── main.py                # Main CLI entrypoint, argument router, Rich UI & REPL
├── ai_client.py           # Vireonix AI API client, exponential backoff retries, JSON parser
├── command_router.py      # Natural language intent classifier & pipeline dispatcher
├── terminal_executor.py   # Controlled PowerShell & CMD subprocess execution & history logging
├── environment_scanner.py # Discovers runtimes (Python, Java, Node, PHP), ports & tools
├── project_detector.py    # Auto-identifies language, framework, configs, and entrypoints
├── error_analyzer.py      # Error log parsing, exception categorization, AI diagnosis
├── auto_repair.py         # Autonomous 5-step repair loop, backups, patch applicator
├── java_manager.py        # Java/JAR diagnostics, manifest parser, bytecode verification
├── process_manager.py     # Background server management, process trees, port releasing
├── verification_engine.py # 5-step verification: process alive, port, HTTP health, logs
├── safety_manager.py      # Risk categorization, blocked patterns, user confirmations
├── config.py              # User settings, persistent configuration, paths
├── requirements.txt       # Dependencies (requests, rich, psutil, prompt_toolkit)
├── install.ps1            # Windows PowerShell one-click installer
├── uninstall.ps1          # Uninstaller
└── README.md              # Documentation & user manual
```

---

## 1. Quick Installation

To install globally for PowerShell and CMD:

```powershell
cd ai-terminal
.\install.ps1
```

The installer will:
1. Detect your Windows environment and active PowerShell version.
2. Locate the optimal Python 3 installation (`Python 3.10+`).
3. Install required packages (`requests`, `rich`, `psutil`, `prompt_toolkit`).
4. Generate `ai.cmd` and `ai.ps1` global wrappers in `$HOME\.ai-terminal\bin`.
5. Permanently register `$HOME\.ai-terminal\bin` in your User `PATH` and PowerShell profile.
6. Test connectivity to `https://vireonix.ai/v1/chat/completions`.
7. Verify terminal execution.

Once installed, open any new terminal window and run:

```powershell
ai "Hello"
```

---

## 2. Global Terminal Usage & Examples

### Chat Mode (Code Generation & Explanations)
Generates code, answers questions, or explains technical topics without modifying files:

```powershell
ai "Give Python code for KNN"
ai "Explain what causes an UnsupportedClassVersionError in Java"
ai "How do I configure Vite with HTTPS?"
```

### System & Environment Inspection
Gathers actual local evidence from your Windows machine:

```powershell
ai "Check my Python installation"
ai doctor
```

Output includes:
- Python versions, active virtual environments, package managers (`pip`, `uv`, `poetry`)
- Java JDK/JRE version, `javac`, `JAVA_HOME`, Maven (`mvn`), Gradle (`gradle`)
- Node.js, `npm`, `pnpm`, `yarn`, `bun`
- Git repository status and branch
- Active listening developer ports (3000, 5000, 8000, 8080) and conflicting PIDs

### Autonomous Error Detection and Repair
Executes the full 5-step autonomous repair cycle:

```powershell
ai "Fix my project errors and run it"
# or
ai auto "Fix this project and run it"
```

#### Workflow Progression:
1. **[SCAN]**: Detects project language, framework, dependencies, and configuration.
2. **[CHECK]**: Inspects runtimes, dependencies, and port availability.
3. **[RUN]**: Attempts to launch or build the application.
4. **[ERROR]**: If startup fails, extracts stack traces and logs.
5. **[AI]**: Queries Vireonix AI with ground-truth error context to determine the root cause.
6. **[FIX]**: Creates a backup snapshot in `.ai-terminal/backups/<timestamp>`, installs missing dependencies, frees conflicting ports, or applies targeted code patches.
7. **[TEST]**: Runs verification checks (process liveness, port binding, HTTP health check, log audit).
8. **Status: VERIFIED**: Only reported if all checks pass successfully.

### Java and JAR Automatic Manager
Specialized support for Java and JAR applications:

```powershell
ai "Check this JAR file, fix the error, and run it"
```

Automatically:
- Reads `META-INF/MANIFEST.MF` for `Main-Class` and `Start-Class`.
- Inspects bytecode major version (e.g., 65 = Java 21, 61 = Java 17, 52 = Java 8).
- Validates compatibility against the installed Java runtime.
- Identifies missing classpath dependencies or port conflicts.
- Launches and verifies the application.

### Safety & Rollback
Before applying any file modification, a snapshot is saved. To revert changes made by the AI fixer:

```powershell
ai rollback
```

---

## 3. Operating Modes

| Mode | Command Syntax | Behavior |
| :--- | :--- | :--- |
| **Chat** | `ai chat "query"` | Answers questions and outputs code without executing shell commands or altering files. |
| **Assist** | `ai assist "query"` | Gathers evidence, proposes fixes, and asks interactive `[y/N]` permission before each action. |
| **Auto** | `ai auto "query"` | Automatically executes preapproved low-risk actions (installing missing packages, building, testing) while prompting for high-risk actions. |
| **Interactive REPL** | `ai` (no args) | Launches an interactive command shell with real-time prompt and rich markdown output. |

---

## 4. Configuration

Stored in `$HOME\.ai-terminal\config.json`:

```json
{
  "api_url": "https://vireonix.ai/v1/chat/completions",
  "model": "auto",
  "api_key": "",
  "timeout": 60,
  "max_retries": 3,
  "retry_delay": 1.5,
  "default_mode": "auto",
  "max_repair_attempts": 3
}
```

### Environment Variable Overrides:
- `VIREONIX_API_URL`: Custom API endpoint
- `VIREONIX_MODEL`: Target model (default: `auto`)
- `VIREONIX_API_KEY`: Optional Bearer authentication token
- `VIREONIX_TIMEOUT`: Timeout in seconds (default: `60`)

---

## 5. Uninstallation

To remove global PATH entries and wrappers:

```powershell
cd ai-terminal
.\uninstall.ps1
```

To purge all configuration and history as well:

```powershell
.\uninstall.ps1 -PurgeAll
```

