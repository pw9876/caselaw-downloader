"""Download case law documents to the local filesystem."""

from __future__ import annotations

import re
from pathlib import Path

from caselaw_downloader.api import CaseSummary, CaselawClient

Format = str  # "html" | "xml" | "pdf"

_SAFE_RE = re.compile(r"[^\w\-/]")


def _safe_path(slug: str) -> Path:
    """Convert a case slug like 'ukut/tcc/2024/1' into a safe relative path."""
    return Path(_SAFE_RE.sub("_", slug))


def download_case(
    client: CaselawClient,
    case: CaseSummary,
    output_dir: Path,
    formats: set[Format],
) -> list[Path]:
    """Download requested formats for a single case. Returns paths written."""
    base = output_dir / _safe_path(case.slug or case.uri)
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    format_map: dict[Format, tuple[str, str]] = {
        "html": (case.html_url, "case.html"),
        "xml": (case.xml_url, "case.xml"),
        "pdf": (case.pdf_url, "case.pdf"),
    }

    for fmt in formats:
        url, filename = format_map[fmt]
        if not url:
            continue
        dest = base / filename
        data = client.fetch_bytes(url)
        dest.write_bytes(data)
        written.append(dest)

    return written


def download_all(
    client: CaselawClient,
    output_dir: Path,
    formats: set[Format],
    limit: int | None = None,
    progress_cb=None,
) -> list[Path]:
    """Download all cases matching the client's court filter.

    Args:
        client: Configured API client.
        output_dir: Root directory for downloaded files.
        formats: Which formats to download ("html", "xml", "pdf").
        limit: Cap the number of cases downloaded (None = no cap).
        progress_cb: Optional callable(case, paths) invoked after each case.

    Returns:
        All file paths written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    all_paths: list[Path] = []
    count = 0

    for case in client.iter_cases():
        if limit is not None and count >= limit:
            break
        paths = download_case(client, case, output_dir, formats)
        all_paths.extend(paths)
        count += 1
        if progress_cb:
            progress_cb(case, paths)

    return all_paths
