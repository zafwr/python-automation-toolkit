"""Plan and apply bulk file renames safely (dry run first, no overwrites)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class RenameError(ValueError):
    pass


@dataclass
class Rename:
    source: Path
    target: Path


def slugify(text: str) -> str:
    """'Fatura Ocak 2026 (1)' -> 'fatura-ocak-2026-1'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower() or "file"


def plan_renames(
    directory: Path,
    template: str,
    *,
    pattern: str = "*",
    start: int = 1,
) -> list[Rename]:
    """Build the list of renames without touching any file.

    Template fields:
      {index}  running number (supports formats like {index:03})
      {stem}   original name without extension
      {slug}   original name, lowercased and URL-safe
      {date}   file modification date, YYYY-MM-DD
      {ext}    original extension including the dot
    """
    if not directory.is_dir():
        raise RenameError(f"{directory} is not a folder")
    files = sorted(p for p in directory.glob(pattern) if p.is_file())

    plan = []
    for offset, path in enumerate(files):
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        try:
            name = template.format(
                index=start + offset, stem=path.stem, slug=slugify(path.stem), date=date, ext=path.suffix.lower()
            )
        except (KeyError, ValueError) as error:
            raise RenameError(f"invalid template '{template}': {error}") from error
        if "/" in name or "\\" in name:
            raise RenameError("template must not contain path separators")
        if path.name != name:
            plan.append(Rename(path, path.with_name(name)))

    targets = [r.target for r in plan]
    duplicates = {t.name for t in targets if targets.count(t) > 1}
    if duplicates:
        raise RenameError(f"template produces duplicate names: {', '.join(sorted(duplicates))}")
    sources = {r.source for r in plan}
    clashes = [t.name for t in targets if t.exists() and t not in sources]
    if clashes:
        raise RenameError(f"would overwrite existing files: {', '.join(sorted(clashes))}")
    return plan


def apply_renames(plan: list[Rename]) -> None:
    """Rename in two phases via temporary names, so swaps like a->b, b->a work."""
    temporary = []
    for index, item in enumerate(plan):
        temp = item.source.with_name(f".autotool-tmp-{index}{item.source.suffix}")
        item.source.rename(temp)
        temporary.append((temp, item.target))
    for temp, target in temporary:
        temp.rename(target)
