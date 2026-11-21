"""Load saved test prompts from prompts/cases/*.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from jevai.config import CASES_DIR, BackendName, parse_backend


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    prompt: str
    backend: BackendName | None = None
    json_mode: bool = False


def load_cases(directory: Path | None = None) -> list[Case]:
    cases_dir = directory or CASES_DIR
    if not cases_dir.is_dir():
        return []

    cases: list[Case] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        case_id = str(data.get("id") or path.stem).strip()
        title = str(data.get("title") or case_id).strip()
        prompt = str(data.get("prompt") or "").strip()
        if not case_id or not prompt:
            raise ValueError(f"Case {path.name} needs non-empty id and prompt")
        try:
            backend = parse_backend(data.get("backend"))
        except ValueError as exc:
            raise ValueError(f"Case {path.name}: {exc}") from exc
        cases.append(
            Case(
                id=case_id,
                title=title,
                prompt=prompt,
                backend=backend,
                json_mode=bool(data.get("json_mode", False)),
            )
        )
    return cases


def get_case(case_id: str, directory: Path | None = None) -> Case | None:
    for case in load_cases(directory):
        if case.id == case_id:
            return case
    return None
