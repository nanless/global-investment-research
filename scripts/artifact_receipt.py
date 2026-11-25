"""Bind one compiled PDF/Word pair to the exact inputs read by the compiler."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class FrozenInputs:
    root: Path
    source: Path
    hashes: dict[str, str]


def equity_render_inputs(market: str, *, flagship: bool) -> list[str]:
    return [
        "equity/pdf_common.py",
        "equity/docx_embed.py",
        f"equity/build_{market}_pdf.py",
        f"equity/report_meta_{market}.json" if flagship else "equity/build_daily.py",
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for data in iter(lambda: file.read(65536), b""):
            digest.update(data)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def freeze_inputs(
    source: Path, *, inputs: Iterable[Path] = (), root: Path = ROOT,
) -> FrozenInputs:
    """Capture report inputs before the compiler reads them."""
    root = root.resolve()
    source = source.resolve()
    hashes = {_relative(root, path): sha256_file(path) for path in (source, *inputs)}
    return FrozenInputs(root, source, hashes)


def write_receipt(frozen: FrozenInputs, pdf: Path, docx: Path) -> None:
    """Write a receipt only after both requested outputs have been produced."""
    source = frozen.source
    if pdf.resolve() != source.with_suffix(".pdf") or docx.resolve() != source.with_suffix(".docx"):
        raise ValueError("The PDF and Word files must share the frozen Markdown stem.")
    outputs = {file.suffix[1:]: sha256_file(file) for file in (pdf, docx)}
    for relative, expected in frozen.hashes.items():
        if sha256_file(frozen.root / relative) != expected:
            raise ValueError(f"Report input changed during compilation: {relative}")
    receipt = {
        "schema": 1,
        "source": _relative(frozen.root, source),
        "inputs": frozen.hashes,
        "outputs": outputs,
    }
    target = source.with_suffix(".artifacts.json")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as file:
        tmp = Path(file.name)
        try:
            json.dump(receipt, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)


def verify_receipt(
    source: Path, *, repository: Path, tree: Path, inputs: Iterable[str], outputs: dict[str, str],
) -> None:
    """Verify a receipt against an isolated Git tree and copies of the final binaries."""
    repository, tree = repository.resolve(), tree.resolve()
    source_key = _relative(repository, source)
    target = source.with_suffix(".artifacts.json")
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Compile the PDF/Word pair to create its receipt: {source_key}")
    try:
        receipt = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid artifact receipt for {source_key}: {exc}") from exc
    paths = PurePosixPath(source_key).parts
    source_aliases = {source_key}
    if (
        len(paths) == 5 and paths[0] in {"gold", "equity"} and paths[1:3] == ("daily", "archive")
        and re.fullmatch(r"\d{4}-\d{2}", paths[3]) and paths[4].startswith(f"{paths[3]}-")
    ):
        # Moving an issue into its month does not change the manuscript bytes.
        source_aliases.add(PurePosixPath(paths[0], "daily", paths[4]).as_posix())
    if (
        not isinstance(receipt, dict) or receipt.get("schema") != 1
        or not isinstance(receipt.get("source"), str) or receipt["source"] not in source_aliases
    ):
        raise ValueError(f"Artifact receipt does not identify {source_key}")
    original_source = receipt["source"]
    recorded = receipt.get("inputs")
    if not isinstance(recorded, dict) or not {original_source, *inputs}.issubset(recorded):
        raise ValueError(f"Artifact receipt lacks required render inputs for {source_key}")
    for relative, expected in recorded.items():
        current = source_key if relative == original_source else relative
        candidate = tree / current
        if (
            _relative(tree, candidate) != current or not isinstance(expected, str)
            or not SHA256.fullmatch(expected) or not candidate.is_file()
            or sha256_file(candidate) != expected
        ):
            raise ValueError(f"Report artifacts are stale for {source_key}: {relative}")
    if receipt.get("outputs") != outputs:
        raise ValueError(f"PDF/Word fingerprints do not match the receipt for {source_key}")
