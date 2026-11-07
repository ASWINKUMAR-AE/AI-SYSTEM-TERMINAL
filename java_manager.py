"""
Java and JAR Automatic Manager for AI System Terminal
Inspects JAR metadata, manifest, bytecode versions, detects Java runtime compatibility,
diagnoses classpath and port errors, builds and launches Java applications.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BYTECODE_VERSION_MAP = {
    45: "Java 1.1",
    46: "Java 1.2",
    47: "Java 1.3",
    48: "Java 1.4",
    49: "Java 5",
    50: "Java 6",
    51: "Java 7",
    52: "Java 8",
    53: "Java 9",
    54: "Java 10",
    55: "Java 11",
    56: "Java 12",
    57: "Java 13",
    58: "Java 14",
    59: "Java 15",
    60: "Java 16",
    61: "Java 17 (LTS)",
    62: "Java 18",
    63: "Java 19",
    64: "Java 20",
    65: "Java 21 (LTS)",
    66: "Java 22",
    67: "Java 23"
}


@dataclass
class JarMetadata:
    path: str
    main_class: Optional[str] = None
    start_class: Optional[str] = None
    build_jdk: Optional[str] = None
    created_by: Optional[str] = None
    class_path: Optional[str] = None
    spring_boot_version: Optional[str] = None
    bytecode_major_version: Optional[int] = None
    required_java_version: Optional[str] = None
    is_executable: bool = False
    files_count: int = 0
    embedded_dependencies: List[str] = field(default_factory=list)


class JavaManager:
    """Manages Java runtimes, JAR inspections, builds, and execution."""

    def __init__(self, workspace: Optional[str | Path] = None):
        self.workspace = Path(workspace).resolve() if workspace else Path.cwd().resolve()

    def get_installed_java_info(self) -> Dict[str, Any]:
        """Detects the active Java version and JAVA_HOME."""
        info: Dict[str, Any] = {
            "installed": False,
            "version_string": "",
            "major_version": 0,
            "java_home": os.environ.get("JAVA_HOME"),
            "javac_available": False
        }

        try:
            p = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=5)
            # java -version outputs to stderr
            output = p.stderr or p.stdout
            if "version" in output.lower():
                info["installed"] = True
                first_line = output.splitlines()[0] if output.splitlines() else output
                info["version_string"] = first_line

                # Extract major version number (e.g., 21.0.10 or 1.8.0)
                m = re.search(r'version\s+"(\d+)(?:\.(\d+))?', output, re.IGNORECASE)
                if m:
                    v1 = int(m.group(1))
                    v2 = int(m.group(2)) if m.group(2) else 0
                    info["major_version"] = v2 if v1 == 1 else v1
        except Exception:
            pass

        if shutil.which("javac"):
            info["javac_available"] = True

        return info

    def inspect_jar(self, jar_path: str | Path) -> JarMetadata:
        """Inspects JAR manifest, bytecode major version, and dependencies."""
        target = Path(jar_path)
        if not target.is_absolute():
            target = (self.workspace / target).resolve()

        if not target.exists():
            raise FileNotFoundError(f"JAR file not found: {target}")

        meta = JarMetadata(path=str(target))

        try:
            with zipfile.ZipFile(target, "r") as z:
                meta.files_count = len(z.infolist())

                # Check manifest
                manifest_name = None
                for n in z.namelist():
                    if n.upper() == "META-INF/MANIFEST.MF":
                        manifest_name = n
                        break

                if manifest_name:
                    content = z.read(manifest_name).decode("utf-8", errors="ignore")
                    for line in content.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            k = k.strip()
                            v = v.strip()
                            if k.lower() == "main-class":
                                meta.main_class = v
                                meta.is_executable = True
                            elif k.lower() == "start-class":
                                meta.start_class = v
                                meta.is_executable = True
                            elif k.lower() == "build-jdk":
                                meta.build_jdk = v
                            elif k.lower() == "created-by":
                                meta.created_by = v
                            elif k.lower() == "class-path":
                                meta.class_path = v
                            elif "spring-boot" in k.lower():
                                meta.spring_boot_version = v

                # Find first class file to check bytecode version
                for n in z.namelist():
                    if n.endswith(".class") and not n.startswith("META-INF/"):
                        raw = z.read(n)[:8]
                        if len(raw) >= 8 and raw[:4] == b"\xca\xfe\xba\xbe":
                            _, major = struct.unpack(">HH", raw[4:8])
                            meta.bytecode_major_version = major
                            meta.required_java_version = BYTECODE_VERSION_MAP.get(major, f"Bytecode {major}")
                            break

                # Check for nested JARs / dependencies (e.g. in Spring Boot BOOT-INF/lib)
                for n in z.namelist():
                    if (n.startswith("BOOT-INF/lib/") or n.startswith("WEB-INF/lib/")) and n.endswith(".jar"):
                        meta.embedded_dependencies.append(Path(n).name)

        except Exception as e:
            pass

        return meta

    def check_compatibility(self, meta: JarMetadata) -> Tuple[bool, str]:
        """Checks if current Java runtime is compatible with the JAR."""
        java_info = self.get_installed_java_info()
        if not java_info["installed"]:
            return False, "Java runtime is not installed or not in PATH."

        current_major = java_info["major_version"]
        required_major = None

        if meta.bytecode_major_version:
            # Map bytecode major (e.g. 65 -> Java 21)
            # bytecode 45 = Java 1.1, ..., 52 = Java 8, 53 = 9, 61 = 17, 65 = 21
            if meta.bytecode_major_version >= 45:
                required_major = meta.bytecode_major_version - 44

        if required_major and current_major < required_major:
            return False, (
                f"Incompatible Java version! JAR requires {meta.required_java_version} (bytecode {meta.bytecode_major_version}), "
                f"but installed Java is {java_info['version_string']} (version {current_major})."
            )

        if not meta.is_executable:
            return False, "JAR manifest does not specify a Main-Class or Start-Class entry point."

        return True, f"JAR is compatible with installed {java_info['version_string']}."

    def diagnose_java_error(self, stderr: str, stdout: str) -> Dict[str, Any]:
        """Parses common Java exceptions and diagnostics."""
        combined = f"{stdout}\n{stderr}"
        diagnosis = {
            "error_type": "Unknown",
            "root_cause": "",
            "recommended_fix": "",
            "can_auto_fix": False
        }

        if "UnsupportedClassVersionError" in combined:
            diagnosis["error_type"] = "JavaVersionMismatch"
            diagnosis["root_cause"] = "The application was compiled for a newer Java runtime than currently installed."
            diagnosis["recommended_fix"] = "Upgrade local Java runtime or recompile targeting the installed Java version."
            diagnosis["can_auto_fix"] = False

        elif "ClassNotFoundException" in combined or "NoClassDefFoundError" in combined:
            m = re.search(r'(?:ClassNotFoundException|NoClassDefFoundError):\s*([a-zA-Z0-9_.$/]+)', combined)
            missing_class = m.group(1) if m else "Unknown class"
            diagnosis["error_type"] = "ClasspathMissing"
            diagnosis["root_cause"] = f"Missing class dependency on classpath: {missing_class}"
            diagnosis["recommended_fix"] = "Add missing dependency to classpath (-cp) or build configuration (pom.xml / build.gradle)."
            diagnosis["can_auto_fix"] = False

        elif "BindException" in combined or "Address already in use" in combined:
            m = re.search(r'port\s+(\d+)', combined, re.IGNORECASE)
            port = m.group(1) if m else "8080"
            diagnosis["error_type"] = "PortConflict"
            diagnosis["root_cause"] = f"Network port {port} is already in use by another process."
            diagnosis["recommended_fix"] = f"Start with alternative port: -Dserver.port={int(port)+1} or terminate the conflicting process."
            diagnosis["can_auto_fix"] = True
            diagnosis["alternative_port"] = int(port) + 1

        elif "NoSuchMethodError" in combined:
            diagnosis["error_type"] = "DependencyConflict"
            diagnosis["root_cause"] = "Incompatible JAR dependency versions loaded at runtime."
            diagnosis["recommended_fix"] = "Align transitive dependency versions in pom.xml / build.gradle."
            diagnosis["can_auto_fix"] = False

        return diagnosis

