"""Client for the National Archives Find Case Law public API."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlparse

import requests

SITE_BASE = "https://caselaw.nationalarchives.gov.uk"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "tna": "http://www.legislation.gov.uk/namespaces/TNA",
}

# Public rate limit: 1 000 requests per rolling 5-minute window
_MIN_DELAY = 0.31  # ~194 req/min, safely under 200 req/min ceiling


@dataclass
class CaseSummary:
    title: str
    uri: str  # e.g. "ukut/tcc/2024/1"
    neutral_citation: str
    published: str
    updated: str
    html_url: str
    xml_url: str
    pdf_url: str


def _parse_entry(entry: ET.Element) -> CaseSummary:
    def txt(tag: str) -> str:
        el = entry.find(tag, _NS)
        return el.text.strip() if el is not None and el.text else ""

    title = txt("atom:title")
    published = txt("atom:published")
    updated = txt("atom:updated")

    neutral_citation = ""
    for id_el in entry.findall("tna:identifier", _NS):
        if id_el.get("type") == "ukncn" and id_el.text:
            neutral_citation = id_el.text.strip()
            break

    html_url = ""
    xml_url = ""
    pdf_url = ""
    for link in entry.findall("atom:link", _NS):
        href = link.get("href", "")
        mime = link.get("type", "")
        if not href:
            continue
        if "pdf" in mime:
            pdf_url = href
        elif "xml" in mime:
            xml_url = href
        elif not mime and link.get("rel") == "alternate":
            html_url = href

    uri = urlparse(html_url).path.lstrip("/") if html_url else ""

    return CaseSummary(
        title=title,
        uri=uri,
        neutral_citation=neutral_citation,
        published=published,
        updated=updated,
        html_url=html_url,
        xml_url=xml_url,
        pdf_url=pdf_url,
    )


class CaselawClient:
    def __init__(
        self,
        courts: list[str],
        session: requests.Session | None = None,
        delay: float = _MIN_DELAY,
    ) -> None:
        self.courts = courts
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "caselaw-downloader/0.1"})
        self.delay = delay
        self._last_request: float = 0.0

    def _get(self, url: str, **params) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        self._last_request = time.monotonic()
        return resp

    def _fetch_page(self, page: int, per_page: int = 50) -> ET.Element:
        params: dict[str, object] = {
            "court": self.courts,
            "page": page,
            "per_page": per_page,
            "order": "-date",
        }
        resp = self._get(f"{SITE_BASE}/atom.xml", **params)
        return ET.fromstring(resp.content)

    def total_results(self) -> int:
        root = self._fetch_page(page=1, per_page=1)
        total_el = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
        if total_el is not None and total_el.text:
            return int(total_el.text)
        return len(root.findall("atom:entry", _NS))

    def iter_cases(self, per_page: int = 50) -> Iterator[CaseSummary]:
        page = 1
        while True:
            root = self._fetch_page(page=page, per_page=per_page)
            entries = root.findall("atom:entry", _NS)
            if not entries:
                break
            for entry in entries:
                yield _parse_entry(entry)
            page += 1

    def fetch_bytes(self, url: str) -> bytes:
        return self._get(url).content
