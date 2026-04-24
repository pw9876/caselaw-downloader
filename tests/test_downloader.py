"""Tests for caselaw_downloader.downloader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import requests

from caselaw_downloader.api import CaseSummary
from caselaw_downloader.downloader import _safe_path, download_all, download_case


def _make_case(slug: str = "ukftt/tc/2024/1") -> CaseSummary:
    return CaseSummary(
        title="Smith v HMRC",
        uri=f"d-uuid-{slug.replace('/', '-')}",
        slug=slug,
        neutral_citation="[2024] UKFTT 1 (TC)",
        published="2024-03-01T00:00:00Z",
        updated="2024-03-01T00:00:00Z",
        html_url=f"https://caselaw.nationalarchives.gov.uk/{slug}",
        xml_url=f"https://caselaw.nationalarchives.gov.uk/{slug}/data.xml",
        pdf_url="https://assets.caselaw.nationalarchives.gov.uk/uuid/uuid.pdf",
    )


def _make_client(cases: list[CaseSummary], content: bytes = b"data") -> MagicMock:
    client = MagicMock()
    client.iter_cases.return_value = iter(cases)
    client.fetch_bytes.return_value = content
    return client


class TestSafePath:
    def test_basic_slug(self):
        p = _safe_path("ukftt/tc/2024/1")
        assert str(p) == "ukftt/tc/2024/1"

    def test_slug_with_special_chars(self):
        p = _safe_path("ukftt/tc/2024/foo bar")
        assert " " not in str(p)

    def test_returns_path_object(self):
        assert isinstance(_safe_path("ukftt/tc/2024/1"), Path)


class TestDownloadCase:
    def test_xml_written(self, tmp_path):
        client = _make_client([], content=b"<xml/>")
        case = _make_case()
        paths = download_case(client, case, tmp_path, {"xml"})
        assert len(paths) == 1
        assert paths[0].name == "case.xml"
        assert paths[0].read_bytes() == b"<xml/>"

    def test_pdf_written(self, tmp_path):
        client = _make_client([], content=b"%PDF")
        case = _make_case()
        paths = download_case(client, case, tmp_path, {"pdf"})
        assert len(paths) == 1
        assert paths[0].name == "case.pdf"

    def test_html_written(self, tmp_path):
        client = _make_client([], content=b"<html/>")
        case = _make_case()
        paths = download_case(client, case, tmp_path, {"html"})
        assert len(paths) == 1
        assert paths[0].name == "case.html"

    def test_multiple_formats(self, tmp_path):
        client = _make_client([], content=b"data")
        case = _make_case()
        paths = download_case(client, case, tmp_path, {"xml", "pdf"})
        names = {p.name for p in paths}
        assert "case.xml" in names
        assert "case.pdf" in names

    def test_creates_subdirectory_from_slug(self, tmp_path):
        client = _make_client([], content=b"data")
        case = _make_case("ukftt/tc/2024/99")
        download_case(client, case, tmp_path, {"xml"})
        assert (tmp_path / "ukftt" / "tc" / "2024" / "99").is_dir()

    def test_empty_url_skipped(self, tmp_path):
        client = _make_client([], content=b"data")
        case = _make_case()
        case.xml_url = ""
        paths = download_case(client, case, tmp_path, {"xml"})
        assert paths == []

    def test_fetch_bytes_called_with_correct_url(self, tmp_path):
        client = _make_client([], content=b"data")
        case = _make_case()
        download_case(client, case, tmp_path, {"xml"})
        client.fetch_bytes.assert_called_once_with(case.xml_url)

    def test_http_error_skipped_with_warning(self, tmp_path, capsys):
        client = _make_client([], content=b"data")
        client.fetch_bytes.side_effect = requests.HTTPError("403 Forbidden")
        case = _make_case()
        paths = download_case(client, case, tmp_path, {"pdf"})
        assert paths == []
        assert "Warning" in capsys.readouterr().err

    def test_existing_file_not_refetched(self, tmp_path):
        client = _make_client([], content=b"new data")
        case = _make_case()
        dest_dir = tmp_path / "ukftt" / "tc" / "2024" / "1"
        dest_dir.mkdir(parents=True)
        (dest_dir / "case.xml").write_bytes(b"original")
        paths = download_case(client, case, tmp_path, {"xml"})
        client.fetch_bytes.assert_not_called()
        assert len(paths) == 1
        assert paths[0].read_bytes() == b"original"

    def test_existing_file_included_in_returned_paths(self, tmp_path):
        client = _make_client([], content=b"new data")
        case = _make_case()
        dest_dir = tmp_path / "ukftt" / "tc" / "2024" / "1"
        dest_dir.mkdir(parents=True)
        existing = dest_dir / "case.xml"
        existing.write_bytes(b"original")
        paths = download_case(client, case, tmp_path, {"xml"})
        assert paths == [existing]

    def test_missing_format_fetched_when_other_exists(self, tmp_path):
        client = _make_client([], content=b"pdf data")
        case = _make_case()
        dest_dir = tmp_path / "ukftt" / "tc" / "2024" / "1"
        dest_dir.mkdir(parents=True)
        (dest_dir / "case.xml").write_bytes(b"existing xml")
        paths = download_case(client, case, tmp_path, {"xml", "pdf"})
        client.fetch_bytes.assert_called_once_with(case.pdf_url)
        names = {p.name for p in paths}
        assert names == {"case.xml", "case.pdf"}


class TestDownloadAll:
    def test_downloads_all_cases(self, tmp_path):
        cases = [_make_case("ukftt/tc/2024/1"), _make_case("ukftt/tc/2024/2")]
        client = _make_client(cases, content=b"<xml/>")
        paths = download_all(client, tmp_path, {"xml"})
        assert len(paths) == 2

    def test_respects_limit(self, tmp_path):
        cases = [_make_case(f"ukftt/tc/2024/{i}") for i in range(5)]
        client = _make_client(cases, content=b"<xml/>")
        paths = download_all(client, tmp_path, {"xml"}, limit=3)
        assert len(paths) == 3

    def test_creates_output_dir(self, tmp_path):
        new_dir = tmp_path / "new_output"
        client = _make_client([], content=b"data")
        download_all(client, new_dir, {"xml"})
        assert new_dir.is_dir()

    def test_progress_callback_called(self, tmp_path):
        cases = [_make_case("ukftt/tc/2024/1")]
        client = _make_client(cases, content=b"data")
        calls = []
        download_all(client, tmp_path, {"xml"}, progress_cb=lambda c, p, e: calls.append((c, p)))
        assert len(calls) == 1
        assert calls[0][0].slug == "ukftt/tc/2024/1"

    def test_http_error_passed_to_callback(self, tmp_path):
        cases = [_make_case("ukftt/tc/2024/1")]
        client = _make_client(cases, content=b"data")
        client.fetch_bytes.side_effect = requests.HTTPError("403 Forbidden")
        collected: list = []
        download_all(client, tmp_path, {"pdf"}, progress_cb=lambda c, p, e: collected.extend(e))
        assert len(collected) == 1
        assert "403" in collected[0][1]

    def test_empty_results_returns_empty_list(self, tmp_path):
        client = _make_client([], content=b"data")
        paths = download_all(client, tmp_path, {"xml"})
        assert paths == []

    def test_limit_none_downloads_all(self, tmp_path):
        cases = [_make_case(f"ukftt/tc/2024/{i}") for i in range(10)]
        client = _make_client(cases, content=b"data")
        paths = download_all(client, tmp_path, {"xml"}, limit=None)
        assert len(paths) == 10

    def test_resume_skips_already_downloaded(self, tmp_path):
        cases = [_make_case("ukftt/tc/2024/1")]
        client = _make_client(cases, content=b"new")
        dest_dir = tmp_path / "ukftt" / "tc" / "2024" / "1"
        dest_dir.mkdir(parents=True)
        (dest_dir / "case.xml").write_bytes(b"original")
        paths = download_all(client, tmp_path, {"xml"})
        client.fetch_bytes.assert_not_called()
        assert len(paths) == 1
        assert paths[0].read_bytes() == b"original"
