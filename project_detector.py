"""
Project Detector for AI System Terminal
Automatically identifies project languages, frameworks, entry points,
dependency managers, configuration files, and standard run/test commands.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProjectInfo:
    root_path: str
    primary_language: str
    framework: Optional[str] = None
    project_type: str = "Unknown"
    entry_point: Optional[str] = None
    config_files: List[str] = field(default_factory=list)
    package_manager: Optional[str] = None
    install_command: Optional[str] = None
    build_command: Optional[str] = None
    run_command: Optional[str] = None
    test_command: Optional[str] = None
    jar_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProjectDetector:
    """Inspects a directory to identify the project ecosystem."""

    def __init__(self, workspace_path: Optional[str | Path] = None):
        self.workspace = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()

    def detect(self) -> ProjectInfo:
        """Runs the detection workflow on the workspace."""
        root = self.workspace
        config_files = self._find_config_files(root)
        jar_files = [str(f.relative_to(root)) for f in root.glob("*.jar")]

        # 1. Java Project Detection
        if (root / "pom.xml").exists():
            return self._detect_maven_project(root, config_files, jar_files)
        if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
            return self._detect_gradle_project(root, config_files, jar_files)
        if jar_files and not any((root / f).exists() for f in ["package.json", "pyproject.toml", "requirements.txt"]):
            return self._detect_jar_project(root, config_files, jar_files)

        # 2. Node / JS / TS Project Detection
        if (root / "package.json").exists():
            return self._detect_node_project(root, config_files, jar_files)

        # 3. Python Project Detection
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or list(root.glob("*.py")):
            return self._detect_python_project(root, config_files, jar_files)

        # 4. PHP Detection
        if (root / "composer.json").exists() or (root / "artisan").exists() or list(root.glob("*.php")):
            return self._detect_php_project(root, config_files, jar_files)

        # 5. Rust / Go / Other
        if (root / "Cargo.toml").exists():
            return ProjectInfo(
                root_path=str(root),
                primary_language="Rust",
                project_type="Rust Application",
                config_files=config_files,
                package_manager="cargo",
                build_command="cargo build",
                run_command="cargo run",
                test_command="cargo test"
            )

        # Default fallback
        return ProjectInfo(
            root_path=str(root),
            primary_language="Generic",
            project_type="Generic Directory",
            config_files=config_files,
            jar_files=jar_files
        )

    def _find_config_files(self, root: Path) -> List[str]:
        known = [
            "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
            "requirements.txt", "pyproject.toml", "Pipfile", "setup.py",
            "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
            "composer.json", "Cargo.toml", "go.mod", "Dockerfile", ".env",
            "tsconfig.json", "vite.config.js", "vite.config.ts", "next.config.js"
        ]
        found = []
        for name in known:
            if (root / name).exists():
                found.append(name)
        return found

    def _detect_python_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        framework = None
        entry_point = None

        # Check entry points
        candidates = ["main.py", "app.py", "server.py", "run.py", "index.py", "manage.py", "application.py"]
        for cand in candidates:
            if (root / cand).exists():
                entry_point = cand
                break

        if not entry_point:
            py_files = list(root.glob("*.py"))
            if py_files:
                entry_point = py_files[0].name

        # Detect Framework
        framework = "Python Script"
        if (root / "manage.py").exists():
            framework = "Django"
        else:
            # Check requirements.txt or pyproject.toml
            req_content = ""
            for fname in ["requirements.txt", "pyproject.toml"]:
                if (root / fname).exists():
                    try:
                        req_content += (root / fname).read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass
            if entry_point:
                try:
                    req_content += (root / entry_point).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass

            req_lower = req_content.lower()
            if "fastapi" in req_lower:
                framework = "FastAPI"
            elif "flask" in req_lower:
                framework = "Flask"
            elif "streamlit" in req_lower:
                framework = "Streamlit"

        # Select verified python executable (local .venv if present, otherwise sys.executable)
        local_venv = root / ".venv" / "Scripts" / "python.exe"
        py_exec = f'"{local_venv}"' if local_venv.exists() else f'"{sys.executable}"'

        # Determine run command
        run_cmd = f"{py_exec} {entry_point}" if entry_point else f"{py_exec} main.py"
        if framework == "FastAPI" and entry_point:
            mod = entry_point.replace(".py", "")
            run_cmd = f"{py_exec} -m uvicorn {mod}:app --reload"
        elif framework == "Django":
            run_cmd = f"{py_exec} manage.py runserver"
        elif framework == "Streamlit" and entry_point:
            run_cmd = f"{py_exec} -m streamlit run {entry_point}"

        install_cmd = f"{py_exec} -m pip install -r requirements.txt" if "requirements.txt" in config_files else f"{py_exec} -m pip install ."

        return ProjectInfo(
            root_path=str(root),
            primary_language="Python",
            framework=framework,
            project_type=f"Python ({framework})",
            entry_point=entry_point,
            config_files=config_files,
            package_manager="pip",
            install_command=install_cmd,
            run_command=run_cmd,
            test_command=f"{py_exec} -m unittest" if (root / "tests").exists() or list(root.glob("test_*.py")) else f"{py_exec} -m unittest",
            jar_files=jar_files
        )

    def _detect_node_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        pkg_json = root / "package.json"
        framework = "Node.js Application"
        run_cmd = "npm start"
        test_cmd = "npm test"
        build_cmd = None
        entry_point = None

        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                scripts = data.get("scripts", {})
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                if "dev" in scripts:
                    run_cmd = "npm run dev"
                elif "start" in scripts:
                    run_cmd = "npm start"

                if "build" in scripts:
                    build_cmd = "npm run build"

                if "next" in deps:
                    framework = "Next.js"
                elif "vite" in deps:
                    framework = "Vite"
                elif "react" in deps:
                    framework = "React"
                elif "vue" in deps:
                    framework = "Vue"
                elif "express" in deps:
                    framework = "Express"
                elif "nestjs" in deps:
                    framework = "NestJS"

                entry_point = data.get("main")
        except Exception:
            pass

        return ProjectInfo(
            root_path=str(root),
            primary_language="JavaScript/TypeScript",
            framework=framework,
            project_type=f"Node.js ({framework})",
            entry_point=entry_point,
            config_files=config_files,
            package_manager="npm",
            install_command="npm install",
            build_command=build_cmd,
            run_command=run_cmd,
            test_command=test_cmd,
            jar_files=jar_files
        )

    def _detect_maven_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        is_spring = False
        try:
            pom_text = (root / "pom.xml").read_text(encoding="utf-8", errors="ignore")
            if "spring-boot" in pom_text.lower():
                is_spring = True
        except Exception:
            pass

        framework = "Spring Boot" if is_spring else "Maven Java"
        run_cmd = "mvn spring-boot:run" if is_spring else "mvn compile exec:java"

        return ProjectInfo(
            root_path=str(root),
            primary_language="Java",
            framework=framework,
            project_type=f"Java ({framework})",
            config_files=config_files,
            package_manager="maven",
            install_command="mvn clean install -DskipTests",
            build_command="mvn clean package -DskipTests",
            run_command=run_cmd,
            test_command="mvn test",
            jar_files=jar_files
        )

    def _detect_gradle_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        return ProjectInfo(
            root_path=str(root),
            primary_language="Java",
            framework="Gradle Java",
            project_type="Java (Gradle)",
            config_files=config_files,
            package_manager="gradle",
            install_command="gradle build -x test",
            build_command="gradle build",
            run_command="gradle bootRun" if (root / "src").exists() else "gradle run",
            test_command="gradle test",
            jar_files=jar_files
        )

    def _detect_jar_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        main_jar = jar_files[0] if jar_files else "app.jar"
        return ProjectInfo(
            root_path=str(root),
            primary_language="Java",
            framework="JAR Executable",
            project_type="Standalone Java JAR",
            entry_point=main_jar,
            config_files=config_files,
            run_command=f"java -jar {main_jar}",
            jar_files=jar_files
        )

    def _detect_php_project(self, root: Path, config_files: List[str], jar_files: List[str]) -> ProjectInfo:
        is_laravel = (root / "artisan").exists()
        framework = "Laravel" if is_laravel else "PHP"
        run_cmd = "php artisan serve" if is_laravel else "php -S localhost:8000"

        return ProjectInfo(
            root_path=str(root),
            primary_language="PHP",
            framework=framework,
            project_type=f"PHP ({framework})",
            config_files=config_files,
            package_manager="composer",
            install_command="composer install",
            run_command=run_cmd,
            jar_files=jar_files
        )
