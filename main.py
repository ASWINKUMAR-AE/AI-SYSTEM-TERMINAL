"""
Main CLI Entrypoint for AI System Terminal
Provides rich terminal UX, command parsing, interactive REPL, and Vireonix AI integration.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from ai_client import VireonixClient
from command_router import CommandRouter, Intent
from config import get_config_path, get_home_dir, load_config, save_config, set_setting
from environment_scanner import EnvironmentScanner
from project_detector import ProjectDetector
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from safety_manager import RiskLevel, SafetyManager

console = Console()


def print_banner(project_name: Optional[str] = None) -> None:
    """Prints the official AI System Terminal header banner."""
    header = (
        "[bold cyan]AI SYSTEM TERMINAL[/bold cyan]\n"
        "[dim]Powered by Vireonix AI[/dim]\n\n"
        f"[bold white]Project:[/bold white] [green]{project_name or 'Detecting...'}[/green]\n"
        f"[bold white]Environment:[/bold white] [yellow]Windows / PowerShell[/yellow]"
    )
    console.print(Panel(header, border_style="cyan", box=box.ROUNDED))


def progress_logger(step: str, message: str) -> None:
    """Displays formatted step badges."""
    colors = {
        "SCAN": "cyan",
        "CHECK": "blue",
        "ERROR": "red",
        "AI": "magenta",
        "FIX": "yellow",
        "TEST": "purple",
        "RUN": "green",
        "VERIFY": "bold green"
    }
    badge_color = colors.get(step, "white")
    console.print(f"[{badge_color}][{step}][/{badge_color}] {message}")


def interactive_confirm(title: str, description: str, risk: RiskLevel) -> bool:
    """Prompts user for interactive confirmation on sensitive actions."""
    risk_colors = {
        RiskLevel.LOW_RISK: "yellow",
        RiskLevel.MEDIUM_RISK: "dark_orange",
        RiskLevel.HIGH_RISK: "red",
        RiskLevel.BLOCKED: "bold red"
    }
    color = risk_colors.get(risk, "white")
    console.print(f"\n[{color}][APPROVAL REQUIRED - {risk.value}][/{color}] {title}")
    console.print(f"[dim]{description}[/dim]")
    return Confirm.ask("Do you approve this action?", default=False)


def handle_doctor(scanner: EnvironmentScanner) -> None:
    """Runs a full system environment check and displays a rich table."""
    with console.status("[cyan]Scanning system environment...[/cyan]", spinner="dots"):
        env = scanner.scan_all()

    table = Table(title="System Environment Diagnostic", box=box.ROUNDED)
    table.add_column("Component", style="cyan", no_wrap=True)
    table.add_column("Status / Version", style="white")
    table.add_column("Details", style="dim")

    # Python
    py = env["python"]
    table.add_row(
        "Python",
        f"{py.get('current_version', 'Unknown')}",
        f"Path: {py.get('current_executable')}, venv: {py.get('in_virtualenv')}"
    )

    # Java
    jv = env["java"]
    table.add_row(
        "Java JDK/JRE",
        f"{jv.get('java_version', 'Not installed')}",
        f"javac: {jv.get('javac_installed')}, JAVA_HOME: {jv.get('java_home')}"
    )

    # Node
    nd = env["node"]
    table.add_row(
        "Node.js",
        f"{nd.get('node_version', 'Not installed')}",
        f"npm: {nd.get('npm_version', 'Not installed')}"
    )

    # Git
    gt = env["git"]
    table.add_row(
        "Git",
        f"{gt.get('git_version', 'Not installed')}",
        f"Repo: {gt.get('is_repo')}, Branch: {gt.get('branch', 'None')}"
    )

    # Ports
    ports = env.get("active_ports", [])
    ports_str = ", ".join(f"{p['port']} ({p['process_name']})" for p in ports) if ports else "No conflicts detected"
    table.add_row("Active Dev Ports", str(len(ports)), ports_str)

    console.print(table)


def run_repl() -> None:
    """Interactive AI System Terminal REPL."""
    detector = ProjectDetector()
    proj = detector.detect()
    print_banner(proj.project_type)
    console.print("[dim]Type your request or 'exit' to quit. Prefix with 'chat:', 'assist:', or 'auto:' to switch modes.[/dim]\n")

    current_mode = "auto"
    router = CommandRouter()

    while True:
        try:
            user_input = Prompt.ask(f"[bold cyan]ai ({current_mode})[/bold cyan]").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[yellow]Exiting AI System Terminal.[/yellow]")
                break

            if user_input.lower() == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                print_banner(proj.project_type)
                continue

            # Switch mode
            mode_to_use = current_mode
            prompt = user_input
            if user_input.lower().startswith("chat:"):
                mode_to_use = "chat"
                prompt = user_input[5:].strip()
            elif user_input.lower().startswith("assist:"):
                mode_to_use = "assist"
                prompt = user_input[7:].strip()
            elif user_input.lower().startswith("auto:"):
                mode_to_use = "auto"
                prompt = user_input[5:].strip()

            result = router.handle_request(
                prompt=prompt,
                mode=mode_to_use,
                confirm_callback=interactive_confirm,
                progress_callback=progress_logger
            )

            # Display response
            if "response" in result and result["response"]:
                console.print()
                console.print(Markdown(result["response"]))
                console.print()

            if "verification" in result:
                verif = result["verification"]
                status_color = "bold green" if verif.status == "VERIFIED" else "bold red"
                console.print(f"\nStatus: [{status_color}]{verif.status}[/{status_color}]")
                console.print(f"[dim]{verif.message}[/dim]\n")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Session ended.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI System Terminal - Powered by Vireonix AI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("query", nargs="*", help="Natural language request or command")
    parser.add_argument("-m", "--mode", choices=["chat", "assist", "auto"], default=None, help="Operating mode")
    parser.add_argument("--doctor", action="store_true", help="Inspect system environment and developer runtimes")
    parser.add_argument("--inspect", action="store_true", help="Inspect current workspace project")
    parser.add_argument("--rollback", action="store_true", help="Restore previous file backup checkpoint")
    parser.add_argument("--clear-history", action="store_true", help="Clear conversation history")
    parser.add_argument("--test-api", action="store_true", help="Test connectivity to Vireonix AI API")

    args = parser.parse_args()
    config = load_config()
    mode = args.mode or config.get("default_mode", "auto")

    ai_client = VireonixClient()
    scanner = EnvironmentScanner()
    detector = ProjectDetector()
    router = CommandRouter(ai_client=ai_client)

    # 1. Test API flag
    if args.test_api:
        console.print("[cyan]Testing Vireonix AI API connection...[/cyan]")
        ok, msg = ai_client.test_connection()
        if ok:
            console.print(f"[green]SUCCESS:[/green] {msg}")
            sys.exit(0)
        else:
            console.print(f"[red]FAILED:[/red] {msg}")
            sys.exit(1)

    # 2. Clear history flag
    if args.clear_history:
        ai_client.clear_history()
        console.print("[green]Conversation history cleared.[/green]")
        sys.exit(0)

    # 3. Doctor flag
    if args.doctor:
        handle_doctor(scanner)
        sys.exit(0)

    # 4. Inspect flag
    if args.inspect:
        proj = detector.detect()
        print_banner(proj.project_type)
        console.print(f"[bold cyan]Project Type:[/bold cyan] {proj.project_type}")
        console.print(f"[bold cyan]Language:[/bold cyan] {proj.primary_language}")
        console.print(f"[bold cyan]Framework:[/bold cyan] {proj.framework}")
        console.print(f"[bold cyan]Entry Point:[/bold cyan] {proj.entry_point}")
        console.print(f"[bold cyan]Config Files:[/bold cyan] {', '.join(proj.config_files)}")
        console.print(f"[bold cyan]Run Command:[/bold cyan] {proj.run_command}")
        console.print(f"[bold cyan]Test Command:[/bold cyan] {proj.test_command}")
        sys.exit(0)

    # 5. Rollback flag
    if args.rollback:
        engine = router.repair_engine
        ok, msg = engine.rollback_latest()
        if ok:
            console.print(f"[green]{msg}[/green]")
        else:
            console.print(f"[red]{msg}[/red]")
        sys.exit(0 if ok else 1)

    # 6. If no query arguments provided, start interactive REPL
    if not args.query:
        run_repl()
        return

    # Check for subcommands in query args
    query_str = " ".join(args.query).strip()

    if query_str.lower() in ("doctor", "env", "system"):
        handle_doctor(scanner)
        return

    if query_str.lower() in ("inspect", "project"):
        proj = detector.detect()
        print_banner(proj.project_type)
        console.print(f"[bold cyan]Project Type:[/bold cyan] {proj.project_type}")
        console.print(f"[bold cyan]Run Command:[/bold cyan] {proj.run_command}")
        return

    if query_str.lower() in ("rollback", "undo"):
        ok, msg = router.repair_engine.rollback_latest()
        console.print(f"[{'green' if ok else 'red'}]{msg}[/{'green' if ok else 'red'}]")
        return

    if query_str.lower().startswith("chat "):
        mode = "chat"
        query_str = query_str[5:].strip()
    elif query_str.lower().startswith("assist "):
        mode = "assist"
        query_str = query_str[7:].strip()
    elif query_str.lower().startswith("auto "):
        mode = "auto"
        query_str = query_str[5:].strip()

    # Detect project context for banner
    proj = detector.detect()
    print_banner(proj.project_type)

    with console.status("[cyan]Processing with Vireonix AI...[/cyan]", spinner="dots"):
        result = router.handle_request(
            prompt=query_str,
            mode=mode,
            confirm_callback=interactive_confirm,
            progress_callback=progress_logger
        )

    # Render results
    if "response" in result and result["response"]:
        console.print()
        console.print(Markdown(result["response"]))
        console.print()

    if "verification" in result:
        verif = result["verification"]
        status_color = "bold green" if verif.status == "VERIFIED" else "bold red"
        console.print(f"\nStatus: [{status_color}]{verif.status}[/{status_color}]")
        console.print(f"[dim]{verif.message}[/dim]\n")


if __name__ == "__main__":
    main()

