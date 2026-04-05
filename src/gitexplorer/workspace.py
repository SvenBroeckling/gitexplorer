"""Platform-aware config directory and workspace persistence.

Config directory resolution order:
  - macOS   : ~/Library/Application Support/gitexplorer
  - Windows : %APPDATA%/gitexplorer
  - Linux   : $XDG_CONFIG_HOME/gitexplorer  (fallback: ~/.config/gitexplorer)
  - Fallback: ~/.gitexplorer  (used if the platform dir cannot be created)

State is stored in <config_dir>/workspaces.toml, keyed by repo root path.
"""
from __future__ import annotations

import os
import platform
import tomllib
from pathlib import Path


# ── config directory ──────────────────────────────────────────────────────────

def get_config_dir() -> Path:
    """Return (and create) the per-user gitexplorer config directory."""
    system = platform.system()

    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home()
    else:                                           # Linux / BSD / etc.
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".config"

    config_dir = base / "gitexplorer"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
    except OSError:
        fallback = Path.home() / ".gitexplorer"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _workspaces_file() -> Path:
    return get_config_dir() / "workspaces.toml"


# ── load / save ───────────────────────────────────────────────────────────────

def load_workspace(repo_root: Path) -> dict:
    """Return saved workspace data for *repo_root*, or ``{}`` if none exists."""
    wf = _workspaces_file()
    if not wf.exists():
        return {}
    try:
        with open(wf, "rb") as f:
            all_data = tomllib.load(f)
        return all_data.get(str(repo_root), {})
    except Exception:
        return {}


def save_workspace(repo_root: Path, data: dict) -> None:
    """Persist *data* for *repo_root* inside workspaces.toml.

    Other projects' entries are left untouched.
    """
    wf = _workspaces_file()

    # Read current file so we don't clobber other projects
    all_data: dict = {}
    if wf.exists():
        try:
            with open(wf, "rb") as f:
                all_data = tomllib.load(f)
        except Exception:
            pass

    all_data[str(repo_root)] = data

    try:
        wf.write_text(_to_toml(all_data), encoding="utf-8")
    except OSError:
        pass


# ── minimal TOML writer ───────────────────────────────────────────────────────
# tomllib (stdlib) is read-only; we only use str / list[str] values so a tiny
# custom serialiser is simpler than adding a dependency.

def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _to_toml(workspaces: dict[str, dict]) -> str:
    """Serialise *workspaces* to TOML (str and list[str] values only)."""
    parts: list[str] = []
    for section_key, section in workspaces.items():
        parts.append(f'["{_escape(section_key)}"]')
        for k, v in section.items():
            if isinstance(v, list):
                items = ", ".join(f'"{_escape(str(s))}"' for s in v)
                parts.append(f"{k} = [{items}]")
            else:
                parts.append(f'{k} = "{_escape(str(v))}"')
        parts.append("")
    return "\n".join(parts)
