from __future__ import annotations

import secrets
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .application import Application
from .config import Settings, get_settings

app = typer.Typer(help="JARVIS Home administration CLI", no_args_is_help=True)
console = Console()


@app.command()
def init(
    env_file: Path = typer.Option(Path(".env"), help="Environment file to create"),
    force: bool = typer.Option(False, help="Overwrite an existing .env"),
) -> None:
    """Create secure local configuration and the master encryption key."""
    if env_file.exists() and not force:
        raise typer.BadParameter(f"{env_file} already exists; use --force to replace it")
    template = Path(".env.example")
    if not template.exists():
        raise typer.BadParameter("Run this command from the repository root")
    session_secret = secrets.token_urlsafe(48)
    admin_password = secrets.token_urlsafe(18)
    content = template.read_text(encoding="utf-8")
    content = content.replace("replace-with-at-least-32-random-characters", session_secret).replace(
        "replace-this-now", admin_password
    )
    env_file.write_text(content, encoding="utf-8")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    settings.ensure_directories()
    application = Application(settings)
    application.audit.record("system", "configuration.init", str(env_file), "success")
    console.print("[bold green]JARVIS Home initialized.[/bold green]")
    console.print(f"Admin user: [bold]{settings.admin_username}[/bold]")
    console.print(f"Initial password: [bold yellow]{admin_password}[/bold yellow]")
    console.print("Store this password safely; it is not recoverable from the database.")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8787),
    reload: bool = typer.Option(False),
) -> None:
    """Run the JARVIS API and dashboard."""
    import uvicorn

    uvicorn.run("jarvis_home.main:app", host=host, port=port, reload=reload)


@app.command()
def backup() -> None:
    """Create an atomic backup of the database and encrypted configuration."""
    service = Application(get_settings()).backups
    result = service.create()
    console.print(f"[green]Backup created:[/green] {result['path']}")
    console.print(f"SHA-256: {result['sha256']}")


@app.command()
def doctor() -> None:
    """Run local configuration and integrity checks."""
    settings = get_settings()
    application = Application(settings)
    table = Table(title="JARVIS Home doctor")
    table.add_column("Check")
    table.add_column("Result")
    errors = settings.validate_production()
    table.add_row("Production configuration", "OK" if not errors else "; ".join(errors))
    audit_ok, broken_at = application.audit.verify_chain()
    table.add_row("Audit chain", "OK" if audit_ok else f"BROKEN at row {broken_at}")
    table.add_row("Database", str(settings.database_path))
    table.add_row("Master key", str(settings.master_key_file))
    table.add_row("Workspace roots", ", ".join(map(str, settings.workspace_root_list)) or "none")
    table.add_row("Shell", "enabled" if settings.enable_shell else "disabled")
    console.print(table)


@app.command()
def reset_local_data(yes: bool = typer.Option(False, "--yes", help="Confirm destructive reset")) -> None:
    """Delete local database and backups. The master key is preserved."""
    if not yes:
        raise typer.BadParameter("Pass --yes to confirm")
    settings = get_settings()
    if settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    console.print("[yellow]Local data reset complete.[/yellow]")


if __name__ == "__main__":
    app()
