"""Tests for caselaw_downloader.cli."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from caselaw_downloader.api import CaseSummary
from caselaw_downloader.cli import main


def _make_case(slug: str = "ukftt/tc/2024/1") -> CaseSummary:
    return CaseSummary(
        title="Test v HMRC",
        uri=f"d-uuid-{slug.replace('/', '-')}",
        slug=slug,
        neutral_citation="[2024] UKFTT 1 (TC)",
        published="2024-03-01T00:00:00Z",
        updated="2024-03-01T00:00:00Z",
        html_url=f"https://example.com/{slug}",
        xml_url=f"https://example.com/{slug}/data.xml",
        pdf_url="https://assets.example.com/uuid.pdf",
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
            patch("caselaw_downloader.cli.CaselawClient"),
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
            courts = MockClient.call_args.kwargs["courts"]
        assert "ukut/tcc" in courts
        assert "ukftt/tc" in courts

    def test_default_format_is_pdf(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = []
            runner.invoke(main, ["--output", str(tmp_path)])
            _, kwargs = mock_dl.call_args
        assert kwargs.get("formats") == {"pdf"}

    def test_format_option(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = []
            runner.invoke(main, ["--output", str(tmp_path), "--format", "xml"])
            _, kwargs = mock_dl.call_args
        assert "xml" in kwargs.get("formats", set())

    def test_zero_download_warns(self, tmp_path):
        runner = CliRunner(mix_stderr=False)
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all") as mock_dl,
        ):
            mock_dl.return_value = []
            result = runner.invoke(main, ["--output", str(tmp_path)])
        assert "Warning" in result.stderr
        assert "court" in result.stderr.lower()

    def test_manifest_written(self, tmp_path):
        runner = CliRunner()
        case = _make_case()
        pdf_path = tmp_path / "ukftt" / "tc" / "2024" / "1" / "case.pdf"

        def fake_download(**kwargs):
            kwargs["progress_cb"](case, [pdf_path], [])
            return [pdf_path]

        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all", side_effect=fake_download),
        ):
            runner.invoke(main, ["--output", str(tmp_path)])

        manifest = tmp_path / "manifest.csv"
        assert manifest.exists()
        content = manifest.read_text()
        assert "[2024] UKFTT 1 (TC)" in content
        assert "Test v HMRC" in content
        assert "ukftt/tc/2024/1" in content

    def test_manifest_not_written_for_zero_cases(self, tmp_path):
        runner = CliRunner()
        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all", return_value=[]),
        ):
            runner.invoke(main, ["--output", str(tmp_path)])
        assert not (tmp_path / "manifest.csv").exists()

    def test_error_log_written(self, tmp_path):
        runner = CliRunner(mix_stderr=False)
        case = _make_case()

        def fake_download(**kwargs):
            kwargs["progress_cb"](case, [], [("https://example.com/f.pdf", "403 Forbidden")])
            return []

        with (
            patch("caselaw_downloader.cli.CaselawClient"),
            patch("caselaw_downloader.cli.download_all", side_effect=fake_download),
        ):
            result = runner.invoke(main, ["--output", str(tmp_path)])

        errors_log = tmp_path / "errors.log"
        assert errors_log.exists()
        assert "https://example.com/f.pdf" in errors_log.read_text()
        assert "Warning" in result.stderr
        assert "errors.log" in result.stderr

    def test_count_zero_warns(self):
        runner = CliRunner(mix_stderr=False)
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 0
            result = runner.invoke(main, ["--count", "--court", "ukftt/bad"])
        assert "Warning" in result.stderr
        assert "ukftt/bad" in result.stderr

    def test_date_range_passed_to_client(self):
        runner = CliRunner()
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 5
            args = ["--count", "--date-from", "2024-01-01", "--date-to", "2024-12-31"]
            runner.invoke(main, args)
            kwargs = MockClient.call_args.kwargs
        assert kwargs["date_from"] == "2024-01-01"
        assert kwargs["date_to"] == "2024-12-31"

    def test_count_output_includes_date_range(self):
        runner = CliRunner()
        with patch("caselaw_downloader.cli.CaselawClient") as MockClient:
            MockClient.return_value.total_results.return_value = 7
            args = ["--count", "--date-from", "2024-01-01", "--date-to", "2024-06-30"]
            result = runner.invoke(main, args)
        assert "2024-01-01" in result.output
        assert "2024-06-30" in result.output

    def test_inverted_date_range_rejected(self):
        runner = CliRunner()
        args = ["--count", "--date-from", "2026-01-01", "--date-to", "2024-12-31"]
        result = runner.invoke(main, args)
        assert result.exit_code == 2
        assert "--date-from" in result.output

    def test_invalid_date_format_rejected(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--count", "--date-from", "01-01-2024"])
        assert result.exit_code == 2
        assert "YYYY-MM-DD" in result.output
