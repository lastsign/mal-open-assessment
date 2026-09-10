"""The documents cite the code; this checks they cite it correctly.

Line numbers rot the moment anything is refactored, and a stale citation is
worse than none — it sends a reader to the wrong place while looking
authoritative. Every citation in the markdown is written as

    `symbol` (ledger/file.py:line)

and this test opens that line and checks the symbol is on it.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Two shapes: `symbol` (ledger/file.py:line) in prose, and the mermaid node
# label symbol()<br/><i>ledger/file.py:line</i> in the README diagram.
PROSE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`\s*\((ledger/\w+\.py):(\d+)\)")
DIAGRAM = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\(\)<br/><i>(ledger/\w+\.py):(\d+)</i>"
)
DOCS = sorted(ROOT.glob("*.md"))


def _citations() -> list[tuple[Path, str, str, int]]:
    found = []
    for doc in DOCS:
        text = doc.read_text()
        for pattern in (PROSE, DIAGRAM):
            for symbol, path, line in pattern.findall(text):
                found.append((doc, symbol, path, int(line)))
    return found


def test_the_documents_actually_cite_the_code() -> None:
    assert len(_citations()) >= 25, "citations have gone missing"


@pytest.mark.parametrize(
    "doc,symbol,path,line",
    _citations(),
    ids=lambda v: v.name if isinstance(v, Path) else str(v),
)
def test_every_citation_points_at_what_it_claims(
    doc: Path, symbol: str, path: str, line: int
) -> None:
    source = (ROOT / path).read_text().splitlines()
    assert line <= len(source), f"{doc.name}: {path}:{line} is past end of file"
    assert symbol in source[line - 1], (
        f"{doc.name} cites {symbol!r} at {path}:{line}, "
        f"which reads: {source[line - 1].strip()!r}"
    )
