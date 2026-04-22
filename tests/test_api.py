"""Tests for caselaw_downloader.api."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest
import requests

from caselaw_downloader.api import (
    API_BASE,
    CaselawClient,
    CaseSummary,
    _parse_entry,
)

ATOM_NS = "http://www.w3.org/2005/Atom"
TNA_NS = "http://www.legislation.gov.uk/namespaces/TNA"
OS_NS = "http://a9.com/-/spec/opensearch/1.1/"

_SINGLE_ENTRY_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}"
      xmlns:tna="{TNA_NS}"
      xmlns:openSearch="{OS_NS}">
  <openSearch:totalResults>1</openSearch:totalResults>
  <entry>
    <title>Smith v HMRC</title>
    <published>2024-03-01T00:00:00Z</published>
    <updated>2024-03-02T00:00:00Z</updated>
    <tna:uri>ukftt/tc/2024/1</tna:uri>
    <tna:identifier type="ukncn">[2024] UKFTT 1 (TC)</tna:identifier>
    <link rel="alternate" type="text/html" href="https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1"/>
    <link rel="xml" type="application/xml" href="https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1/data.xml"/>
    <link rel="pdf" type="application/pdf" href="https://caselaw.nationalarchives.gov.uk/ukftt/tc/2024/1/data.pdf"/>
  </entry>
</feed>"""

_EMPTY_FEED_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}" xmlns:openSearch="{OS_NS}">
  <openSearch:totalResults>0</openSearch:totalResults>
</feed>"""


def _mock_response(xml_text: str, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.content = xml_text.encode()
    resp.raise_for_status = MagicMock()
    return resp


class TestParseEntry:
    def _entry(self) -> ET.Element:
        root = ET.fromstring(_SINGLE_ENTRY_XML)
        return root.find(f"{{{ATOM_NS}}}entry")

    def test_title(self):
        case = _parse_entry(self._entry())
        assert case.title == "Smith v HMRC"

    def test_uri(self):
        case = _parse_entry(self._entry())
        assert case.uri == "ukftt/tc/2024/1"

    def test_neutral_citation(self):
        case = _parse_entry(self._entry())
        assert case.neutral_citation == "[2024] UKFTT 1 (TC)"

    def test_published(self):
        case = _parse_entry(self._entry())
        assert case.published == "2024-03-01T00:00:00Z"

    def test_html_url(self):
        case = _parse_entry(self._entry())
        assert "ukftt/tc/2024/1" in case.html_url

    def test_xml_url(self):
        case = _parse_entry(self._entry())
        assert case.xml_url.endswith("data.xml")

    def test_pdf_url(self):
        case = _parse_entry(self._entry())
        assert case.pdf_url.endswith("data.pdf")

    def test_missing_fields_return_empty_strings(self):
        bare = ET.fromstring(
            f'<entry xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}"></entry>'
        )
        case = _parse_entry(bare)
        assert case.title == ""
        assert case.uri == ""
        assert case.neutral_citation == ""


class TestCaselawClient:
    def _client(self, session: MagicMock) -> CaselawClient:
        return CaselawClient(courts=["ukftt/tc"], session=session, delay=0)

    def test_total_results(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_SINGLE_ENTRY_XML)
        client = self._client(session)
        assert client.total_results() == 1

    def test_total_results_no_opensearch_element(self):
        xml = f"""<feed xmlns="{ATOM_NS}" xmlns:tna="{TNA_NS}">
          <entry><title>X</title><tna:uri>ukftt/tc/2024/1</tna:uri>
            <published/><updated/>
          </entry>
        </feed>"""
        session = MagicMock()
        session.get.return_value = _mock_response(xml)
        client = self._client(session)
        # Falls back to counting entries
        assert client.total_results() == 1

    def test_iter_cases_yields_entries(self):
        responses = [
            _mock_response(_SINGLE_ENTRY_XML),
            _mock_response(_EMPTY_FEED_XML),
        ]
        session = MagicMock()
        session.get.side_effect = responses
        client = self._client(session)
        cases = list(client.iter_cases())
        assert len(cases) == 1
        assert isinstance(cases[0], CaseSummary)

    def test_iter_cases_stops_on_empty_feed(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        client = self._client(session)
        assert list(client.iter_cases()) == []

    def test_iter_cases_paginates(self):
        two_entries = _SINGLE_ENTRY_XML.replace(
            "</feed>",
            f"""  <entry>
    <title>Jones v HMRC</title>
    <published>2024-04-01T00:00:00Z</published>
    <updated>2024-04-01T00:00:00Z</updated>
    <tna:uri>ukftt/tc/2024/2</tna:uri>
    <tna:identifier type="ukncn">[2024] UKFTT 2 (TC)</tna:identifier>
  </entry>
</feed>""",
        )
        responses = [
            _mock_response(two_entries),
            _mock_response(_EMPTY_FEED_XML),
        ]
        session = MagicMock()
        session.get.side_effect = responses
        client = self._client(session)
        cases = list(client.iter_cases())
        assert len(cases) == 2

    def test_fetch_bytes_returns_content(self):
        session = MagicMock()
        session.get.return_value = _mock_response(b"PDF data".decode(), 200)
        client = self._client(session)
        data = client.fetch_bytes("https://example.com/case.pdf")
        assert data == b"PDF data"

    def test_http_error_raises(self):
        session = MagicMock()
        resp = MagicMock(spec=requests.Response)
        resp.raise_for_status.side_effect = requests.HTTPError("404")
        session.get.return_value = resp
        client = self._client(session)
        with pytest.raises(requests.HTTPError):
            client.fetch_bytes("https://example.com/missing.pdf")

    def test_courts_passed_as_params(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_EMPTY_FEED_XML)
        client = CaselawClient(courts=["ukut/tcc", "ukftt/tc"], session=session, delay=0)
        list(client.iter_cases())
        call_kwargs = session.get.call_args
        assert "court" in call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {})) or \
               any("court" in str(a) for a in call_kwargs.args)
