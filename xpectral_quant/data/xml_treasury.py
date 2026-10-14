# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

# Third-party imports
import polars as pl

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["USTreasuryRates"]

_LIVE_BASE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml"
)
_ARCHIVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/daily-treasury-rate-archives/par-yield-curve-rates-1990-2023.xml"
)
_ARCHIVE_CUTOFF_YEAR = 2023
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
}

# Rate fields are prefixed ``bc_`` (Bond Constant Maturity) -- Treasury's own
# naming convention from the XML feed. These are par yield curve rates, not
# spot rates, expressed as percentages (e.g. 3.68 means 3.68%).
_BC_TAGS = {
    "bc_1month": "d:BC_1MONTH",
    "bc_2month": "d:BC_2MONTH",
    "bc_3month": "d:BC_3MONTH",
    "bc_6month": "d:BC_6MONTH",
    "bc_1year": "d:BC_1YEAR",
    "bc_2year": "d:BC_2YEAR",
    "bc_5year": "d:BC_5YEAR",
    "bc_10year": "d:BC_10YEAR",
    "bc_30year": "d:BC_30YEAR",
}

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class USTreasuryRates:
    """Fetch daily US Treasury par yield curve rates into Polars.

    The par yield curve relates the par yield on a security to its time to
    maturity, based on closing market bid prices on the most recently
    auctioned Treasury securities in the over-the-counter market. Par yields
    are derived from input market prices -- indicative quotations obtained by
    the Federal Reserve Bank of New York at approximately 3:30 PM ET each
    business day.

    https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics
    """

    def get_rates(self, start_date: date, end_date: date) -> pl.LazyFrame:
        """Fetch Treasury par yield curve rates for [start_date, end_date].

        Args:
            start_date: First date of the range, inclusive.
            end_date: Last date of the range, inclusive.

        Returns:
            LazyFrame with a ``date`` index column followed by one ``bc_*``
            column per maturity, sorted ascending by date and filtered to the
            requested range.
        """
        rows = []
        if start_date.year <= _ARCHIVE_CUTOFF_YEAR:
            rows.extend(_fetch_xml(_ARCHIVE_URL))
        for year in range(
            max(start_date.year, _ARCHIVE_CUTOFF_YEAR + 1), end_date.year + 1
        ):
            url = f"{_LIVE_BASE_URL}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
            rows.extend(_fetch_xml(url))

        df = pl.DataFrame(rows)
        # Archive and live feeds can overlap at the year boundary; keep the
        # later fetch's row for a duplicated date (the live feed, since it is
        # always fetched after the archive for the years it covers).
        df = df.unique(subset="date", keep="last")
        df = df.filter(pl.col("date").is_between(start_date, end_date))
        df = df.sort("date")

        return df.lazy()


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


def _fetch_xml(url: str) -> list[dict]:
    """Fetch and parse a Treasury XML feed, returning all entries as row dicts.

    The timeout bounds each blocking socket operation, not the request
    end-to-end: a pathological slow-drip server could stretch the total
    beyond 30 seconds, but every individual stall is bounded, so a stalled
    feed raises instead of hanging indefinitely.
    """
    with urllib.request.urlopen(url, timeout=30) as response:
        root = ET.parse(response).getroot()
    return [_parse_entry(entry) for entry in root.findall("atom:entry", _NS)]


def _parse_entry(entry: ET.Element) -> dict:
    """Extract a single row dict from an Atom feed <entry> element."""
    props = entry.find("atom:content/m:properties", _NS)
    row = {"date": date.fromisoformat(props.find("d:NEW_DATE", _NS).text[:10])}
    row.update({name: _float(props, tag) for name, tag in _BC_TAGS.items()})
    return row


def _float(props: ET.Element, tag: str) -> float | None:
    """Return the float value of an XML tag, or None if the tag is missing or empty."""
    el = props.find(tag, _NS)
    if el is None or el.text is None:
        return None
    return float(el.text)
