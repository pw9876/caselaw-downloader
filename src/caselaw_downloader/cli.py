"""CLI entry point for caselaw-downloader."""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import click

from caselaw_downloader.api import CaselawClient
from caselaw_downloader.downloader import download_all

DEFAULT_COURTS = ["ukut/tcc", "ukftt/tc"]
VALID_FORMATS = {"html", "xml", "pdf"}


@click.command()
@click.option(
    "--output",
    "-o",
    default="./cases",
    show_default=True,
    type=click.Path(file_okay=False, writable=True),
    help="Directory to save downloaded cases.",
)
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    default=["pdf"],
    show_default=True,
    type=click.Choice(["html", "xml", "pdf"], case_sensitive=False),
    help="File format(s) to download. Can be specified multiple times.",
)
@click.option(
    "--court",
    "-c",
    "courts",
    multiple=True,
    default=DEFAULT_COURTS,
    show_default=True,
    help="Court code(s) to filter by (e.g. ukut/tcc). Can be specified multiple times.",
)
@click.option(
    "--limit",
    "-n",
    default=None,
    type=int,
    help="Maximum number of cases to download (default: all).",
)
@click.option(
    "--count",
    is_flag=True,
    default=False,
    help="Print the total number of matching cases and exit.",
)
@click.option(
    "--date-from",
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include cases published on or after this date.",
)
@click.option(
    "--date-to",
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include cases published on or before this date.",
)
def main(
    output: str,
    formats: tuple[str, ...],
    courts: tuple[str, ...],
    limit: int | None,
    count: bool,
    date_from: str | None,
    date_to: str | None,
) -> None:
    """Download case law from The National Archives Find Case Law service.

    By default downloads all Tax Chamber and Upper Tribunal Tax and Chancery
    cases in PDF format.

    \b
    Examples:
      caselaw-downloader --format xml --format pdf --limit 10
      caselaw-downloader --court ukftt/tc --output ./tax-cases
      caselaw-downloader --count
      caselaw-downloader --date-from 2024-01-01 --date-to 2024-12-31 --count
    """
    for label, val in (("--date-from", date_from), ("--date-to", date_to)):
        if val is not None:
            try:
                date.fromisoformat(val)
            except ValueError:
                raise click.BadParameter(f"must be YYYY-MM-DD, got {val!r}", param_hint=label)

    if date_from and date_to and date.fromisoformat(date_from) > date.fromisoformat(date_to):
        raise click.UsageError(
            f"--date-from ({date_from}) must not be after --date-to ({date_to})"
        )

    client = CaselawClient(courts=list(courts), date_from=date_from, date_to=date_to)

    if count:
        total = client.total_results()
        parts = [f"courts: {', '.join(courts)}"]
        if date_from:
            parts.append(f"from {date_from}")
        if date_to:
            parts.append(f"to {date_to}")
        click.echo(f"{total} cases found for {', '.join(parts)}")
        if total == 0:
            click.echo(
                f"Warning: no cases found. Verify court code(s) are correct: {', '.join(courts)}",
                err=True,
            )
        return

    fmt_set = {f.lower() for f in formats}
    output_path = Path(output)

    click.echo(f"Courts : {', '.join(courts)}")
    click.echo(f"Formats: {', '.join(sorted(fmt_set))}")
    click.echo(f"Output : {output_path.resolve()}")
    if date_from:
        click.echo(f"From   : {date_from}")
    if date_to:
        click.echo(f"To     : {date_to}")
    if limit:
        click.echo(f"Limit  : {limit}")
    click.echo()

    downloaded = 0
    manifest_rows: list[dict] = []
    all_errors: list[tuple[str, str]] = []

    def on_case(case, paths, errors):
        nonlocal downloaded
        downloaded += 1
        label = case.neutral_citation or case.uri or case.title
        click.echo(f"[{downloaded}] {label} — {len(paths)} file(s)")
        manifest_rows.append({
            "neutral_citation": case.neutral_citation,
            "title": case.title,
            "published": case.published[:10] if case.published else "",
            "slug": case.slug,
            "files": ";".join(str(p.relative_to(output_path)) for p in paths),
        })
        all_errors.extend(errors)

    try:
        all_paths = download_all(
            client=client,
            output_dir=output_path,
            formats=fmt_set,
            limit=limit,
            progress_cb=on_case,
        )
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(1)

    click.echo()
    dest = output_path.resolve()
    click.echo(f"Done. {downloaded} case(s), {len(all_paths)} file(s) saved to {dest}")
    if downloaded == 0:
        click.echo(
            f"Warning: no cases downloaded. Verify court code(s) are correct: {', '.join(courts)}",
            err=True,
        )

    if manifest_rows:
        manifest_path = output_path / "manifest.csv"
        with manifest_path.open("w", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["neutral_citation", "title", "published", "slug", "files"]
            )
            writer.writeheader()
            writer.writerows(manifest_rows)
        click.echo(f"Manifest : {manifest_path.resolve()}")

    if all_errors:
        errors_path = output_path / "errors.log"
        errors_path.write_text("".join(f"{u}\t{m}\n" for u, m in all_errors))
        click.echo(
            f"Warning: {len(all_errors)} file(s) skipped — see {errors_path.resolve()}",
            err=True,
        )
