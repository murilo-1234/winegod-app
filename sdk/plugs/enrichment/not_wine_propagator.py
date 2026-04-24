"""Gera patch para `scripts/wine_filter.py` com patterns NOT_WINE novos.

NAO aplica o patch. NAO commita. So escreve um `.diff` em
`reports/data_ops_not_wine_patches/` pronto para apply manual via
`git apply`.

Entrada: lista de itens classificados como `not_wine` (pelo sistema v3
ou pelo router). A funcao extrai um pattern candidato simples por item
(primeira substring curta significativa) e cruza com o conjunto atual
de `_NON_WINE_PATTERNS` do arquivo.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
WINE_FILTER_PATH = REPO_ROOT / "scripts" / "wine_filter.py"
PATCHES_DIR = REPO_ROOT / "reports" / "data_ops_not_wine_patches"


_PATTERNS_LIST_ANCHOR = "_NON_WINE_PATTERNS = ["
_PATTERN_LINE_RE = re.compile(r"^\s*r[\"']([^\"']+)[\"']\s*,?\s*(?:#.*)?$")

_WORD_SANITIZE_RE = re.compile(r"[^a-z0-9\s-]")
_MULTISPACE_RE = re.compile(r"\s+")


@dataclass
class PatchEntry:
    pattern: str
    source_name: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "source_name": self.source_name,
            "reason": self.reason,
        }


@dataclass
class PropagatorResult:
    new_patterns: list[PatchEntry] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    patch_path: Path | None = None


def _existing_patterns(wine_filter_text: str | None = None) -> list[str]:
    text = wine_filter_text if wine_filter_text is not None else (
        WINE_FILTER_PATH.read_text(encoding="utf-8") if WINE_FILTER_PATH.exists() else ""
    )
    patterns: list[str] = []
    in_list = False
    for line in text.splitlines():
        if _PATTERNS_LIST_ANCHOR in line:
            in_list = True
            continue
        if in_list:
            stripped = line.strip()
            if stripped.startswith("]"):
                break
            m = _PATTERN_LINE_RE.match(line)
            if m:
                patterns.append(m.group(1))
    return patterns


def _extract_candidate_pattern(name: str) -> str | None:
    """Extrai um pattern regex simples a partir de um nome NOT_WINE."""
    if not name:
        return None
    lowered = name.lower().strip()
    lowered = _WORD_SANITIZE_RE.sub(" ", lowered)
    lowered = _MULTISPACE_RE.sub(" ", lowered).strip()
    # Pega primeira palavra "forte" (>=5 chars) como candidato minimo.
    for token in lowered.split(" "):
        if len(token) >= 5 and token.isalpha():
            return re.escape(token)
    return None


def _is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _is_new_pattern(pattern: str, existing: list[str]) -> bool:
    lowered = pattern.lower()
    for ex in existing:
        if lowered == ex.lower():
            return False
        # pattern novo que e substring de um existente tambem ja esta coberto.
        if re.search(lowered, ex.lower(), flags=re.IGNORECASE):
            return False
    return True


def propose_patch(
    not_wine_items: Iterable[dict[str, Any]],
    *,
    wine_filter_text: str | None = None,
    max_new: int = 25,
) -> PropagatorResult:
    text = wine_filter_text if wine_filter_text is not None else (
        WINE_FILTER_PATH.read_text(encoding="utf-8") if WINE_FILTER_PATH.exists() else ""
    )
    existing = _existing_patterns(text)
    seen: set[str] = set()
    new_patterns: list[PatchEntry] = []
    skipped: list[dict[str, Any]] = []

    for item in not_wine_items:
        name = (
            item.get("full_name")
            or item.get("wine_name")
            or (item.get("wine_identity") or {}).get("nome")
            or ""
        )
        candidate = _extract_candidate_pattern(name)
        if not candidate:
            skipped.append({"name": name, "reason": "no_pattern_extractable"})
            continue
        if not _is_valid_regex(candidate):
            skipped.append({"name": name, "pattern": candidate, "reason": "invalid_regex"})
            continue
        if not _is_new_pattern(candidate, existing):
            skipped.append({"name": name, "pattern": candidate, "reason": "already_covered"})
            continue
        if candidate in seen:
            skipped.append({"name": name, "pattern": candidate, "reason": "duplicate_in_batch"})
            continue
        seen.add(candidate)
        new_patterns.append(
            PatchEntry(
                pattern=candidate,
                source_name=name,
                reason="propagator_candidate",
            )
        )
        if len(new_patterns) >= max_new:
            break

    diff_text = ""
    if text and new_patterns:
        diff_text = _build_diff(text, new_patterns)
    return PropagatorResult(
        new_patterns=new_patterns,
        skipped=skipped,
        diff=diff_text,
    )


def _build_diff(wine_filter_text: str, new_patterns: list[PatchEntry]) -> str:
    lines = wine_filter_text.splitlines(keepends=True)
    anchor_idx = None
    for i, line in enumerate(lines):
        if _PATTERNS_LIST_ANCHOR in line:
            anchor_idx = i
            break
    if anchor_idx is None:
        return ""
    insert_idx = anchor_idx + 1
    # Insere logo apos a abertura do list, formatando como `    r"pattern",`
    new_lines = list(lines)
    for entry in reversed(new_patterns):
        new_lines.insert(
            insert_idx,
            f'    r"{entry.pattern}",  # added by not_wine_propagator (source: {entry.source_name[:60]})\n',
        )
    diff = difflib.unified_diff(
        lines,
        new_lines,
        fromfile="scripts/wine_filter.py",
        tofile="scripts/wine_filter.py",
        n=3,
    )
    return "".join(diff)


def persist_patch(result: PropagatorResult, *, timestamp: str | None = None) -> Path | None:
    if not result.diff:
        return None
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = PATCHES_DIR / f"{ts}_wine_filter_patch.diff"
    path.write_text(result.diff, encoding="utf-8")
    result.patch_path = path
    return path


__all__ = [
    "PatchEntry",
    "PropagatorResult",
    "propose_patch",
    "persist_patch",
    "WINE_FILTER_PATH",
    "PATCHES_DIR",
]
