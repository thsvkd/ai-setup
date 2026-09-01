"""Integrity contract for the AGENTS.md documentation router.

AGENTS.md is always loaded into context, so it stays thin and delegates the
detailed rules to documents under `docs/`. The failure mode of that split is a
router that lies: a link to a document that does not exist sends the agent
hunting, and a document nobody registered is a document nobody reads. The
previous AGENTS.md shipped a reference to `docs/SPEC.md` that was never written.

Instructions cannot enforce this — they are context, not configuration — so the
check lives here instead.

Contracts pinned by this module:

1. Every `docs/...` path referenced by AGENTS.md either exists on disk or is
   registered in `docs/README.md` with the `planned` status.
2. Every top-level document under `docs/` is registered in `docs/README.md`.

`res/AGENTS.md` is the template shipped to other projects, so its links have no
reason to resolve against this repository. It is out of scope here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = ROOT / "AGENTS.md"
DOCS = ROOT / "docs"
DOCS_INDEX = DOCS / "README.md"

# How the router writes a reference: `docs/PRD.md`, `docs/handoffs/`, `docs/adr/`
DOC_REF = re.compile(r"`docs/([^`]+)`")
# How the index writes an entry: `PRD.md`, `handoffs/<task>.md`, `adr/`
INDEX_TOKEN = re.compile(r"`([^`]+)`")

STATUS_WORDS = {"authoritative", "draft", "planned", "historical"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _router_refs() -> set[str]:
    """Paths under `docs/` that AGENTS.md points at, deduplicated.

    A reference carrying angle brackets, such as `docs/handoffs/<task>.md`, is a
    naming placeholder rather than a real path, so it is excluded.
    """
    return {
        ref.strip()
        for ref in DOC_REF.findall(_read(AGENTS_MD))
        if "<" not in ref and ">" not in ref
    }


def _index_entries() -> tuple[set[str], set[str]]:
    """Return (every token registered in the index, the subset marked planned)."""
    registered: set[str] = set()
    planned: set[str] = set()
    for line in _read(DOCS_INDEX).splitlines():
        tokens = {token.strip() for token in INDEX_TOKEN.findall(line)}
        # A status word is a status, not a document name.
        tokens -= STATUS_WORDS
        registered |= tokens
        if "`planned`" in line:
            planned |= tokens
    return registered, planned


def _matches(ref: str, tokens: set[str]) -> bool:
    """Whether one router reference is registered among the index tokens.

    The index drops the `docs/` prefix, and it writes a directory either as a
    bare name such as `handoffs/` or with a sample file such as
    `handoffs/<task>.md`. So a directory reference matches on prefix rather than
    on exact equality.
    """
    if ref in tokens:
        return True
    if ref.endswith("/"):
        return any(token.startswith(ref) for token in tokens)
    return False


def test_router_and_index_files_exist() -> None:
    """Guard the guards: a missing file would make the assertions below vacuous."""
    assert AGENTS_MD.is_file(), "the root AGENTS.md is missing"
    assert DOCS_INDEX.is_file(), "docs/README.md (the documentation index) is missing"


def test_router_refs_exist_or_are_registered_as_planned() -> None:
    """A document the router points at must exist, or be registered as planned."""
    registered, planned = _index_entries()

    dangling = []
    for ref in sorted(_router_refs()):
        if (DOCS / ref).exists():
            continue
        if _matches(ref, planned):
            continue
        if _matches(ref, registered):
            dangling.append(
                f"docs/{ref} — registered, but the file is missing and its status is not planned"
            )
        else:
            dangling.append(
                f"docs/{ref} — the file is missing and it is not registered in docs/README.md"
            )

    assert not dangling, (
        "the documentation router in AGENTS.md is broken:\n  " + "\n  ".join(dangling)
    )


def test_every_doc_is_registered_in_the_index() -> None:
    """Write a document, register it. An unregistered document is never read."""
    index = _read(DOCS_INDEX)
    orphans = [
        path.name
        for path in sorted(DOCS.glob("*.md"))
        if path.name != "README.md" and f"`{path.name}`" not in index
    ]
    assert not orphans, (
        "these documents are not registered in docs/README.md: " + ", ".join(orphans)
    )
