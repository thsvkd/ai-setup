"""Integrity contract for the AGENTS.md documentation router.

AGENTS.md is always loaded into context, so it stays thin and delegates the
detailed rules to documents under `docs/`. The failure mode of that split is a
router that lies: a link to a document that does not exist sends the agent
hunting, a document nobody registered is a document nobody reads, and a document
registered but never routed is one nobody can reach. The previous AGENTS.md
shipped a reference to `docs/SPEC.md` that was never written.

Instructions cannot enforce this -- they are context, not configuration -- so the
check lives here instead.

Contracts pinned by this module:

1. Every `docs/...` path referenced by AGENTS.md either exists on disk or is
   registered in `docs/README.md` with the `planned` status.
2. Every document under `docs/` is registered in `docs/README.md`, either by
   name or through the directory that holds it.
3. Every live document in the index (`planned` or `authoritative`) is reachable
   from the router. Registration without a route is the mirror image of a
   dangling link, and it fails just as quietly.
4. The root AGENTS.md and the res/AGENTS.md template keep the same section
   structure. The root file calls itself an instance of the base, so a rule
   dropped from one side and not the other is a silent divergence.

Only the index's *table rows* count as registration. A document named in passing
in a sentence is not registered -- otherwise a line of prose could vouch for a
document the status table never tracks.

The base template's document links have no reason to resolve against this
repository -- it is copied into unrelated ones -- so contracts 1 to 3 do not
apply to it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = ROOT / "AGENTS.md"
BASE_AGENTS_MD = ROOT / "res" / "AGENTS.md"
DOCS = ROOT / "docs"
DOCS_INDEX = DOCS / "README.md"

# How the index writes an entry: `PRD.md`, `handoffs/<task>.md`, `adr/`
INDEX_TOKEN = re.compile(r"`([^`]+)`")
# A reference is any docs/ path inside a code span. Anchoring on the backtick
# itself would miss `cat docs/PRD.md`, and a reference that the scanner cannot
# see is a reference this module silently stops guarding.
DOC_REF = re.compile(r"docs/([^\s`,)]+)")
HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)

# Anthropic's guidance for an always-loaded instruction file. The refactor's
# whole premise, so it gets an assertion rather than a promise.
MAX_INSTRUCTION_LINES = 200

# The status vocabulary docs/README.md defines for itself. A fifth word invented
# in a table row would otherwise be mistaken for a document name.
STATUS_WORDS = {"authoritative", "draft", "planned", "historical"}
# Statuses that describe a document someone is meant to reach.
LIVE_STATUSES = {"authoritative", "planned"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _router_refs() -> set[str]:
    """Paths under `docs/` that AGENTS.md points at, deduplicated.

    A reference carrying angle brackets, such as `docs/handoffs/<task>.md`, is a
    naming placeholder rather than a real path, so it is excluded.
    """
    refs = set()
    for span in INDEX_TOKEN.findall(_read(AGENTS_MD)):
        for ref in DOC_REF.findall(span):
            ref = ref.strip().rstrip(".")
            if "<" in ref or ">" in ref:
                continue
            refs.add(ref)
    return refs


def _exists_case_sensitively(relative: str) -> bool:
    """`(DOCS / ref).exists()` ignores case on Windows and macOS.

    This repository targets four platforms, so a router that writes
    `docs/prd.md` must not pass here and then fail only on Linux CI.
    """
    current = DOCS
    for part in [p for p in relative.split("/") if p]:
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def _normalize_index_token(token: str) -> str:
    """`handoffs/<task>.md` registers the directory, not a file that never exists.

    The index names a per-task document by its pattern so a reader can see the
    naming convention. Taken literally it would register nothing real, so the
    angle-bracket form is folded back to the directory that holds those files.
    """
    if "<" in token or ">" in token:
        head, _, _ = token.rpartition("/")
        return f"{head}/" if head else token
    return token


def _index_entries() -> tuple[set[str], set[str]]:
    """Return (every token registered in the index, the subset that is live).

    Only table rows are read. Prose mentioning a document, including the status
    definitions at the top of the index, must not register anything.
    """
    registered: set[str] = set()
    live: set[str] = set()
    for line in _read(DOCS_INDEX).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        tokens = {token.strip() for token in INDEX_TOKEN.findall(line)}
        statuses = tokens & STATUS_WORDS
        tokens = {_normalize_index_token(t) for t in tokens - STATUS_WORDS}
        registered |= tokens
        if statuses & LIVE_STATUSES:
            live |= tokens
    return registered, live


def _same_target(a: str, b: str) -> bool:
    """Whether two paths name the same document or one holds the other.

    The index and the router spell directories differently: the router writes
    `handoffs/`, the index writes `handoffs/<task>.md`. Either side may be the
    directory, so containment is checked in both directions.
    """
    if a == b:
        return True
    if a.endswith("/") and b.startswith(a):
        return True
    if b.endswith("/") and a.startswith(b):
        return True
    return False


def _matches(ref: str, tokens: set[str]) -> bool:
    return any(_same_target(ref, token) for token in tokens)


def test_router_and_index_files_exist() -> None:
    """Guard the guards: a missing file would make the assertions below vacuous."""
    assert AGENTS_MD.is_file(), "the root AGENTS.md is missing"
    assert BASE_AGENTS_MD.is_file(), "res/AGENTS.md (the base template) is missing"
    assert DOCS_INDEX.is_file(), "docs/README.md (the documentation index) is missing"


def test_index_uses_only_its_own_status_vocabulary() -> None:
    """A fifth status word would silently register itself as a document name."""
    rows = [
        line for line in _read(DOCS_INDEX).splitlines()
        if line.lstrip().startswith("|") and "---" not in line
    ]
    # The header row names columns rather than documents, so it carries no status.
    unstatused = [
        row for row in rows[1:]
        if "`" in row and not (set(INDEX_TOKEN.findall(row)) & STATUS_WORDS)
    ]
    assert not unstatused, (
        "these index rows carry no status from the defined vocabulary "
        f"({', '.join(sorted(STATUS_WORDS))}):\n  " + "\n  ".join(unstatused)
    )


def test_router_refs_exist_or_are_registered_as_planned() -> None:
    """A document the router points at must exist, or be registered as planned."""
    registered, _ = _index_entries()
    planned = {
        _normalize_index_token(token.strip())
        for line in _read(DOCS_INDEX).splitlines()
        if line.lstrip().startswith("|") and "`planned`" in line
        for token in INDEX_TOKEN.findall(line)
        if token.strip() not in STATUS_WORDS
    }

    dangling = []
    for ref in sorted(_router_refs()):
        if _exists_case_sensitively(ref):
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


def test_planned_documents_do_not_exist_yet() -> None:
    """A written document still marked planned means the status table has gone stale.

    The dangling-link check passes the moment the file appears, so nothing else
    notices that the index still calls it unwritten.
    """
    stale = sorted(
        token for line in _read(DOCS_INDEX).splitlines()
        if line.lstrip().startswith("|") and "`planned`" in line
        for token in (_normalize_index_token(t.strip()) for t in INDEX_TOKEN.findall(line))
        if token not in STATUS_WORDS and _exists_case_sensitively(token)
    )
    assert not stale, (
        "these documents exist but docs/README.md still calls them planned: "
        + ", ".join(stale)
    )


def test_instruction_files_stay_under_the_line_budget() -> None:
    """Always-loaded instructions grow back unless something says no."""
    oversized = {
        path.name: len(_read(path).splitlines())
        for path in (AGENTS_MD, BASE_AGENTS_MD)
        if len(_read(path).splitlines()) >= MAX_INSTRUCTION_LINES
    }
    assert not oversized, (
        f"an instruction file must stay under {MAX_INSTRUCTION_LINES} lines: {oversized}"
    )


def test_every_live_index_entry_is_reachable_from_the_router() -> None:
    """The mirror of a dangling link: registered, tracked, and reachable by nobody."""
    _, live = _index_entries()
    refs = _router_refs()

    unreachable = sorted(
        token for token in live
        if not any(_same_target(token, ref) for ref in refs)
    )
    assert not unreachable, (
        "docs/README.md tracks these as live, but AGENTS.md never routes to them: "
        + ", ".join(unreachable)
    )


def test_root_instance_and_base_template_share_a_structure() -> None:
    """The root file claims to be an instance of the base, so the shape must match.

    Only the headings are compared: the base carries placeholders where the root
    carries this repository's real commands, and the root is free to add rules
    inside a section. A whole section appearing on one side only is the drift
    this catches -- when the two were byte-identical nothing could diverge, and
    that safety net went away the moment they were split.
    """
    root_sections = [f"{hashes} {title}" for hashes, title in HEADING.findall(_read(AGENTS_MD))]
    base_sections = [f"{hashes} {title}" for hashes, title in HEADING.findall(_read(BASE_AGENTS_MD))]

    assert root_sections == base_sections, (
        "AGENTS.md and res/AGENTS.md have drifted apart structurally:\n"
        f"  only in AGENTS.md:     {[s for s in root_sections if s not in base_sections]}\n"
        f"  only in res/AGENTS.md: {[s for s in base_sections if s not in root_sections]}"
    )


def test_every_doc_is_registered_in_the_index() -> None:
    """Write a document, register it. An unregistered document is never read.

    Subdirectories count as registered when the index tracks the directory, so a
    new handoff does not have to be listed one by one -- but a new directory, or
    a new top-level document, does.
    """
    registered, _ = _index_entries()

    orphans = []
    for path in sorted(DOCS.rglob("*.md")):
        if path == DOCS_INDEX:
            continue
        relative = path.relative_to(DOCS).as_posix()
        if _matches(relative, registered):
            continue
        orphans.append(relative)

    assert not orphans, (
        "these documents are not registered in docs/README.md: " + ", ".join(orphans)
    )
