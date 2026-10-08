"""
test_citation_lint.py
---------------------
Lint test ensuring citation integrity across the GridSentinel repository.
Scans repo text files for arXiv identifiers and DOIs, asserting that any
such identifier is present in docs/REFERENCES.md.

Standard library only (re, os, pathlib, pytest).
"""

from pathlib import Path
import re
import pytest

# Regex patterns per specification
ARXIV_PATTERN = re.compile(r"arXiv:\s?(\d{4}\.\d{4,5})", re.IGNORECASE)
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>)]+", re.IGNORECASE)

# Target text extensions
TEXT_EXTENSIONS = {".md", ".py", ".ts", ".tsx", ".json", ".txt"}

# Excluded directories and files
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "test-results",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}

EXCLUDED_FILES = {
    "package-lock.json",
    "poetry.lock",
    "CITATION_AUDIT.md",
}


def get_repo_root() -> Path:
    """Find repository root containing docs/REFERENCES.md."""
    # This test is located in gridsentinel/backend/tests/
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "docs" / "REFERENCES.md").exists():
            return parent
        if (parent / "gridsentinel" / "docs" / "REFERENCES.md").exists():
            return parent / "gridsentinel"
    # Fallback
    return current.parent.parent


def get_canonical_references(repo_root: Path) -> str:
    """Read docs/REFERENCES.md contents."""
    ref_file = repo_root / "docs" / "REFERENCES.md"
    assert ref_file.exists(), f"docs/REFERENCES.md not found at {ref_file}"
    return ref_file.read_text(encoding="utf-8")


def normalize_identifier(raw: str) -> str:
    """Clean trailing punctuation from matched identifier."""
    return raw.rstrip(".,;:)")


def scan_repo_for_unverified_identifiers(repo_root: Path):
    """Scan all text files for arXiv IDs and DOIs not present in docs/REFERENCES.md."""
    canonical_text = get_canonical_references(repo_root)
    unverified = []

    for path in repo_root.rglob("*"):
        # Check directory exclusion
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        # Skip docs/REFERENCES.md itself
        if path.name == "REFERENCES.md" and "docs" in path.parts:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel_path = path.relative_to(repo_root)
        for line_num, line in enumerate(content.splitlines(), 1):
            # Check arXiv IDs
            for match in ARXIV_PATTERN.finditer(line):
                full_match = normalize_identifier(match.group(0))
                arxiv_id = match.group(1)
                if arxiv_id not in canonical_text and full_match not in canonical_text:
                    unverified.append((str(rel_path), line_num, full_match))

            # Check DOIs
            for match in DOI_PATTERN.finditer(line):
                doi = normalize_identifier(match.group(0))
                if doi not in canonical_text:
                    unverified.append((str(rel_path), line_num, doi))

    return unverified


def test_all_repo_citations_are_canonical():
    """Verify that all arXiv IDs and DOIs in the repo match docs/REFERENCES.md."""
    repo_root = get_repo_root()
    unverified = scan_repo_for_unverified_identifiers(repo_root)

    if unverified:
        details = "\n".join(
            f"  {file}:{line} -> {identifier}"
            for file, line, identifier in unverified
        )
        pytest.fail(
            f"Found {len(unverified)} unverified citation identifier(s) not listed in docs/REFERENCES.md:\n{details}"
        )
