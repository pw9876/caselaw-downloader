"""CLI entry point for caselaw-downloader."""

from __future__ import annotations

import sys
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
    default=["xml"],
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
def main(output: str, formats: tuple[str, ...], courts: tuple[str, ...], limit: int | None, count: bool) -> None:
    """Download case law from The National Archives Find Case Law service.

    By default downloads all Tax Chamber and Upper Tribunal Tax and Chancery
    cases in XML format.

    \b
    Examples:
      caselaw-downloader --format xml --format pdf --limit 10
      caselaw-downloader --court ukftt/tc --output ./tax-cases
      caselaw-downloader --count
    """
    client = CaselawClient(courts=list(courts))

    if count:
        total = client.total_results()
        click.echo(f"{total} cases found for courts: {', '.join(courts)}")
        return

    fmt_set = {f.lower() for f in formats}
    output_path = Path(output)

    click.echo(f"Courts : {', '.join(courts)}")
    click.echo(f"Formats: {', '.join(sorted(fmt_set))}")
    click.echo(f"Output : {output_path.resolve()}")
    if limit:
        click.echo(f"Limit  : {limit}")
    click.echo()

    downloaded = 0

    def on_case(case, paths):
        nonlocal downloaded
        downloaded += 1
        label = case.neutral_citation or case.uri or case.title
        click.echo(f"[{downloaded}] {label} — {len(paths)} file(s)")

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
    click.echo(f"Done. {downloaded} case(s), {len(all_paths)} file(s) saved to {output_path.resolve()}")
