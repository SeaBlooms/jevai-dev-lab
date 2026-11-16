"""Load and hash the checked-in Jev system prompt."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from jevai.config import SYSTEM_PROMPT_PATH


@dataclass(frozen=True)
class Persona:
    text: str
    sha256: str
    path: Path
    mtime_ns: int


def load_persona(path: Path | None = None) -> Persona:
    prompt_path = path or SYSTEM_PROMPT_PATH
    raw = prompt_path.read_text(encoding="utf-8")
    text = raw.strip()
    if not text:
        raise ValueError(f"Persona file is empty: {prompt_path}")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Persona(
        text=text,
        sha256=digest,
        path=prompt_path,
        mtime_ns=prompt_path.stat().st_mtime_ns,
    )


class PersonaCache:
    """Reload system.md when the file changes on disk."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or SYSTEM_PROMPT_PATH
        self._persona: Persona | None = None

    def get(self) -> Persona:
        current_mtime = self._path.stat().st_mtime_ns
        if self._persona is None or self._persona.mtime_ns != current_mtime:
            self._persona = load_persona(self._path)
        return self._persona
