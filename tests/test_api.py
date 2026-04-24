"""Tests for caselaw_downloader.api."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest
import requests

from caselaw_downloader.api import (
    SITE_BASE,
    CaselawClient,
    CaseSummary,
    _parse_entry,
)

ATOM_NS = "http://www.w3.org/2005/Atom"
TNA_NS = "https://caselaw.nationalarchives.gov.uk"

_SINGLE_ENTRY_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}">
  <entry>
    <title>Smith v HMRC</title>
    <published>2024-03-01T00:00:00Z</published>
    <updated>2024-03-02T00:00:00Z</updated>
    <tna:uri>d-9aa2342e-0f33-4a94-9597-3eed9f72b50f</tna:uri>
    <tna:identifier slug="ukftt/tc/2024/1" type="ukncn">[2024] UKFTT 1 (TC)</tna:identifier>
    <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1"/>
    <link rel="alternate" type="application/akn+xml"
      href="https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1/data.xml"/>
    <link rel="alternate" type="application/pdf"
      href="https://assets.caselaw.nationalarchives.gov.uk/d-9aa2342e/d-9aa2342e.pdf"/>
  </entry>
</feed>"""

_EMPTY_FEED_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}">
</feed>"""

_SEARCH_HTML_WITH_COUNT = '<p class="results-count">1,234 documents found</p>'
_SEARCH_HTML_NO_COUNT = "<p>No results</p>"


def _mock_response(body: str | bytes, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    if isinstance(body, str):
        resp.content = body.encode()
        resp.text = body
    else:
        resp.content = body
        resp.text = body.decode()
    resp.raise_for_status = MagicMock()
    return resp


class TestParseEntry:
    def _entry(self) -> ET.Element:
        root = ET.fromstring(_SINGLE_ENTRY_XML)
        return root.find(f"{{{ATOM_NS}}}entry")

    def test_title(self):
        assert _parse_entry(self._entry()).title == "Smith v HMRC"

    def test_uuid_uri(self):
        assert _parse_entry(self._entry()).uri == "d-9aa2342e-0f33-4a94-9597-3eed9f72b50f"

    def test_slug(self):
        assert _parse_entry(self._entry()).slug == "ukftt/tc/2024/1"

    def test_neutral_citation(self):
        assert _parse_entry(self._entry()).neutral_citation == "[2024] UKFTT 1 (TC)"

    def test_published(self):
        assert _parse_entry(self._entry()).published == "2024-03-01T00:00:00Z"

    def test_html_url_no_type(self):
        case = _parse_entry(self._entry())
        assert case.html_url == "https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1"
        assert "data" not in case.html_url

    def test_xml_url_akn_type(self):
        assert _parse_entry(self._entry()).xml_url.endswith("data.xml")

    def test_pdf_url_from_assets(self):
        assert "assets" in _parse_entry(self._entry()).pdf_url

    def test_missing_fields_return_empty_strings(self):
        bare = ET.fromstring(f'<entry xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}"></entry>')
        case = _parse_entry(bare)
        assert case.title == ""
        assert case.uri == ""
        assert case.slug == ""
        assert case.neutral_citation == ""

    def test_html_fallback_uses_slug(self):
        xml = f"""<entry xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}">
          <title>X</title><published/><updated/>
          <tna:uri>some-uuid</tna:uri>
          <tna:identifier slug="ukftt/tc/2024/5" type="ukncn">[2024] UKFTT 5 (TC)</tna:identifier>
        </entry>"""
        case = _parse_entry(ET.fromstring(xml))
        assert case.html_url == f"{SITE_BASE}/ukftt/tc/2024/5"

    def test_xml_fallback_uses_slug(self):
        xml = f"""<entry xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}">
          <title>X</title><published/><updated/>
          <tna:uri>some-uuid</tna:uri>
          <tna:identifier slug="ukftt/tc/2024/5" type="ukncn">[2024] UKFTT 5 (TC)</tna:identifier>
        </entry>"""
        case = _parse_entry(ET.fromstring(xml))
        assert case.xml_url == f"{SITE_BASE}/ukftt/tc/2024/5/data.xml"


class TestCaselawClient:
    def _client(self, session: MagicMock, **kwargs) -> CaselawClient:
        return CaselawClient(courts=["ukftt/tc"], session=session, delay=0, **kwargs)

    def test_total_results_parses_html_count(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_SEARCH_HTML_WITH_COUNT)
        assert self._client(session).total_results() == 1234

    def test_total_results_count_with_comma(self):
        session = MagicMock()
        session.get.return_value = _mock_response("1,688 documents found")
        assert self._client(session).total_results() == 1688

    def test_total_results_falls_back_to_entry_count(self):
        session = MagicMock()
        session.get.side_effect = [
            _mock_response(_SEARCH_HTML_NO_COUNT),
            _mock_response(_SINGLE_ENTRY_XML),
        ]
        assert self._client(session).total_results() == 1

    def test_date_params_sent_to_atom_feed(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        list(self._client(session, date_from="2024-01-15", date_to="2024-12-31").iter_cases())
        params = session.get.call_args[1]["params"]
        assert params["from_date_0"] == "15"
        assert params["from_date_1"] == "01"
        assert params["from_date_2"] == "2024"
        assert params["to_date_0"] == "31"
        assert params["to_date_1"] == "12"
        assert params["to_date_2"] == "2024"

    def test_date_params_sent_to_search(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_SEARCH_HTML_WITH_COUNT)
        self._client(session, date_from="2024-06-01", date_to="2024-06-30").total_results()
        params = session.get.call_args[1]["params"]
        assert params["from_date_0"] == "01"
        assert params["from_date_1"] == "06"
        assert params["from_date_2"] == "2024"

    def test_no_date_params_when_not_set(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        list(self._client(session).iter_cases())
        params = session.get.call_args[1]["params"]
        assert "from_date_0" not in params
        assert "to_date_0" not in params

    def test_iter_cases_yields_entries(self):
        session = MagicMock()
        session.get.side_effect = [
            _mock_response(_SINGLE_ENTRY_XML),
            _mock_response(_EMPTY_FEED_XML),
        ]
        cases = list(self._client(session).iter_cases())
        assert len(cases) == 1
        assert isinstance(cases[0], CaseSummary)

    def test_iter_cases_stops_on_empty_feed(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        assert list(self._client(session).iter_cases()) == []

    def test_iter_cases_paginates(self):
        two_entries = _SINGLE_ENTRY_XML.replace(
            "</feed>",
            """  <entry>
    <title>Jones v HMRC</title>
    <published>2024-04-01T00:00:00Z</published>
    <updated>2024-04-01T00:00:00Z</updated>
    <tna:uri>d-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</tna:uri>
    <tna:identifier slug="ukftt/tc/2024/2" type="ukncn">[2024] UKFTT 2 (TC)</tna:identifier>
  </entry>
</feed>""",
        )
        session = MagicMock()
        session.get.side_effect = [
            _mock_response(two_entries),
            _mock_response(_EMPTY_FEED_XML),
        ]
        assert len(list(self._client(session).iter_cases())) == 2

    def test_fetch_bytes_returns_content(self):
        session = MagicMock()
        session.get.return_value = _mock_response(b"PDF data")
        assert self._client(session).fetch_bytes("https://example.com/case.pdf") == b"PDF data"

    def test_http_error_raises(self):
        session = MagicMock()
        resp = MagicMock(spec=requests.Response)
        resp.raise_for_status.side_effect = requests.HTTPError("404")
        session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            self._client(session).fetch_bytes("https://example.com/missing.pdf")

    def test_correct_atom_url_used(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        list(self._client(session).iter_cases())
        assert session.get.call_args[0][0] == f"{SITE_BASE}/atom.xml"
