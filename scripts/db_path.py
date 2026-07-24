#!/usr/bin/env python3
"""Resolve the collector SQLite path consistently for scripts and deployment."""

from __future__ import annotations

import os
from pathlib import Path


def _parse_dotenv_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    if value[0] in {"'", '"'}:
        quote = value[0]
        parsed: list[str] = []
        escaped = False
        for index, char in enumerate(value[1:], start=1):
            if escaped:
                if char not in {quote, "\\"}:
                    parsed.append("\\")
                parsed.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                trailing = value[index + 1 :].strip()
                if not trailing or trailing.startswith("#"):
                    return "".join(parsed)
                return value
            else:
                parsed.append(char)
        if escaped:
            parsed.append("\\")
        return value

    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value


def _dotenv_db_path(dotenv_path: Path) -> str | None:
    if not dotenv_path.is_file():
        return None

    configured = None
    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        export_parts = key.split(None, 1)
        if len(export_parts) == 2 and export_parts[0] == "export":
            key = export_parts[1].strip()
        if key != "DB_PATH":
            continue
        configured = _parse_dotenv_value(value) or None

    return configured


def resolve_db_path(project_root: str | Path | None = None) -> Path:
    root = (
        Path(project_root)
        if project_root is not None
        else Path(__file__).resolve().parent.parent
    )
    configured = os.environ.get("DB_PATH") or _dotenv_db_path(root / ".env")
    path = Path(configured).expanduser() if configured else root / "data" / "nichescope.db"
    if not path.is_absolute():
        path = root / path
    return path.resolve()


if __name__ == "__main__":
    print(resolve_db_path())
