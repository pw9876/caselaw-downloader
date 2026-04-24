"""Client for the National Archives Find Case Law public API."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterator

import requests

SITE_BASE = "https://caselaw.nationalarchives.gov.uk"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "tna": "https://caselaw.nationalarchives.gov.uk",
}

# Public rate limit: 1 000 requests per rolling 5-minute window
_MIN_DELAY = 0.31  # ~194 req/min, safely under 200 req/min ceiling

_COUNT_RE = re.compile(r"([\d,]+)\s+documents?\s+found", re.IGNORECASE)


@dataclass
class CaseSummary:
    title: str
    uri: str        # UUID e.g. "d-9aa2342e-0f33-4a94-9597-3eed9f72b50f"
    slug: str       # path e.g. "ukftt/tc/2026/613"
    neutral_citation: str
    published: str
    updated: str
    html_url: str
    xml_url: str
    pdf_url: str
    links: dict[str, str] = field(default_factory=dict)


def _parse_entry(entry: ET.Element) -> CaseSummary:
    def txt(tag: str) -> str:
        el = entry.find(tag, _NS)
        return el.text.strip() if el is not None and el.text else ""

    title = txt("atom:title")
    published = txt("atom:published")
    updated = txt("atom:updated")

    uri_el = entry.find("tna:uri", _NS)
    uri = uri_el.text.strip() if uri_el is not None and uri_el.text else ""

    ncn_el = entry.find(f"{{{_NS['tna']}}}identifier[@type='ukncn']")
    neutral_citation = (
        ncn_el.text.strip() if ncn_el is not None and ncn_el.text else ""
    )
    slug = ncn_el.get("slug", "") if ncn_el is not None else ""

    html_url = xml_url = pdf_url = ""
    links: dict[str, str] = {}
    for link in entry.findall("atom:link", _NS):
        rel = link.get("rel", "")
        href = link.get("href", "")
        mime = link.get("type", "")
        if not href:
            continue
        links[f"{rel}:{mime}"] = href
        if rel == "alternate":
            if "pdf" in mime:
                pdf_url = href
            elif "xml" in mime or "akn" in mime:
                xml_url = href
            elif not mime:
                html_url = href

    if not html_url and slug:
        html_url = f"{SITE_BASE}/{slug}"
    if not xml_url and slug:
        xml_url = f"{SITE_BASE}/{slug}/data.xml"

    return CaseSummary(
        title=title,
        uri=uri,
        slug=slug,
        neutral_citation=neutral_citation,
        published=published,
        updated=updated,
        html_url=html_url,
        xml_url=xml_url,
        pdf_url=pdf_url,
        links=links,
    )


class CaselawClient:
    def __init__(
        self,
        courts: list[str],
        date_from: str | None = None,
        date_to: str | None = None,
        session: requests.Session | None = None,
        delay: float = _MIN_DELAY,
    ) -> None:
        self.courts = courts
        self.date_from = date_from
        self.date_to = date_to
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

    def _date_params(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if self.date_from:
            year, month, day = self.date_from.split("-")
            p["from_date_0"] = day
            p["from_date_1"] = month
            p["from_date_2"] = year
        if self.date_to:
            year, month, day = self.date_to.split("-")
            p["to_date_0"] = day
            p["to_date_1"] = month
            p["to_date_2"] = year
        return p

    def _fetch_page(self, page: int, per_page: int = 50) -> ET.Element:
        params: dict[str, object] = {
            "court": self.courts,
            "page": page,
            "per_page": per_page,
            "order": "-date",
            **self._date_params(),
        }
        resp = self._get(f"{SITE_BASE}/atom.xml", **params)
        return ET.fromstring(resp.content)

    def total_results(self) -> int:
        resp = self._get(
            f"{SITE_BASE}/search",
            court=self.courts,
            **self._date_params(),
        )
        m = _COUNT_RE.search(resp.text)
        if m:
            return int(m.group(1).replace(",", ""))
        root = self._fetch_page(page=1, per_page=50)
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
