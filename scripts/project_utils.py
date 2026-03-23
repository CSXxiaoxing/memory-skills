#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_utils.py - Project root and memory path helpers.

Goals:
- Consistent project root detection (per SKILL.md rules)
- Stable brain.md resolution (.memory preferred, legacy brain.md supported)
- Shared helpers for memory directory resolution
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PROJECT_MARKERS = ["package.json", "Cargo.toml", "go.mod"]


def find_project_root(start_path: Optional[str | Path] = None) -> Path:
    """
    Detect project root by walking upward from start_path.

    Priority:
    1) .memory/brain.md exists
    2) .git exists
    3) package.json / Cargo.toml / go.mod exists
    4) fallback to start_path
    """
    start = Path(start_path or os.getcwd()).resolve()
    for candidate in [start] + list(start.parents):
        if (candidate / ".memory" / "brain.md").exists():
            return candidate
        if (candidate / ".git").exists():
            return candidate
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return start


def resolve_brain_path(
    start_path: Optional[str | Path] = None,
    explicit_path: Optional[str | Path] = None,
    prefer_dot_memory: bool = True,
) -> Path:
    """
    Resolve brain.md path.

    - If explicit_path provided, use it.
    - Otherwise detect project root and prefer .memory/brain.md if present.
    - Fallback to legacy root/brain.md if it exists.
    - If none exist, return preferred target (dot-memory by default).
    """
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    root = find_project_root(start_path)
    dot_brain = root / ".memory" / "brain.md"
    legacy_brain = root / "brain.md"

    if dot_brain.exists():
        return dot_brain
    if legacy_brain.exists():
        return legacy_brain
    return dot_brain if prefer_dot_memory else legacy_brain


def get_memory_dir(brain_path: str | Path) -> Path:
    """Return the memories directory based on brain.md location."""
    return Path(brain_path).parent / "memories"


def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists and return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
