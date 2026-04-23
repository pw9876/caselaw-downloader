"""Tests for caselaw_downloader.cli."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from caselaw_downloader.api import CaseSummary
from caselaw_downloader.cli import main


def _make_case(uri: str = "ukftt/tc/2024/1") -> CaseSummary:
    return CaseSummary(
        title="Test v HMRC",
        uri=uri,
        neutral_citation="[2024] UKFTT 1 (TC)",
        published="2024-03-01T00:00:00Z",
        updated="2024-03-01T00:00:00Z",
        html_url=f"https://example.com/{uri}",
        xml_url=f"https://example.com/{uri}/data.xml",
        pdf_url=f"https://example.com/{uri}/data.pdf",
    )


class TestCLI:
    def test_count_flag(self):
        runner = CliRunner()
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 42
            result = runner.invoke(main, ["--count"])
        assert result.exit_code == 0
        assert "42" in result.output

    def test_count_shows_courts(self):
        runner = CliRunner()
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 10
            result = runner.invoke(main, ["--count", "--court", "ukftt/tc"])
        assert "ukftt/tc" in result.output

    def test_download_success(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient") as MockClient,
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = [tmp_path / "case.xml"]
            result = runner.invoke(main, ["--output", str(tmp_path), "--limit", "1"])
        assert result.exit_code == 0

    def test_download_prints_summary(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = [tmp_path / "a.xml", tmp_path / "b.xml"]
            result = runner.invoke(main, ["--output", str(tmp_path)])
        assert "Done" in result.output

    def test_keyboard_interrupt_exits_cleanly(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all", side_effect=KeyboardInterrupt),
        ):
            result = runner.invoke(main, ["--output", str(tmp_path)])
        assert result.exit_code == 1

    def test_default_courts(self):
        runner = CliRunner()
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 0
            runner.invoke(main, ["--count"])
            call_kwargs = MockClient.call_args
            courts = call_kwargs.kwargs.get("courts") or call_kwargs[1].get("courts")
        assert "ukut/tcc" in courts
        assert "ukftt/tc" in courts

    def test_format_option(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = []
            runner.invoke(main, ["--output", str(tmp_path), "--format", "pdf"])
            _, kwargs = mock_dl.call_args
        assert "pdf" in kwargs.get("formats", set())
