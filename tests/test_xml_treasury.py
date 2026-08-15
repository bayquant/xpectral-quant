# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date

# Other imports
from xpectral.data import xml_treasury
from xpectral.data.xml_treasury import USTreasuryRates

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

_ARCHIVE_ROWS = [
    {"date": date(2023, 12, 29), "bc_1month": 5.5, "bc_10year": 3.88},
    {"date": date(2024, 1, 2), "bc_1month": 5.55, "bc_10year": 3.95},
]
_LIVE_2024_ROWS = [
    {"date": date(2024, 1, 2), "bc_1month": 5.55, "bc_10year": 3.95},
    {"date": date(2024, 1, 3), "bc_1month": 5.54, "bc_10year": 3.91},
]

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def test_get_rates_filters_and_sorts_within_range(monkeypatch):
    calls = []

    def _fake_fetch_xml(url):
        calls.append(url)
        if url == xml_treasury._ARCHIVE_URL:
            return _ARCHIVE_ROWS
        return _LIVE_2024_ROWS

    monkeypatch.setattr(xml_treasury, "_fetch_xml", _fake_fetch_xml)

    df = USTreasuryRates().get_rates(date(2023, 12, 29), date(2024, 1, 3)).collect()

    assert df["date"].to_list() == [
        date(2023, 12, 29),
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]
    assert df["bc_10year"].to_list() == [3.88, 3.95, 3.91]
    assert xml_treasury._ARCHIVE_URL in calls
    assert any("field_tdr_date_value=2024" in url for url in calls)


def test_get_rates_within_archive_year_skips_live_fetch(monkeypatch):
    calls = []

    def _fake_fetch_xml(url):
        calls.append(url)
        return _ARCHIVE_ROWS

    monkeypatch.setattr(xml_treasury, "_fetch_xml", _fake_fetch_xml)

    df = USTreasuryRates().get_rates(date(2023, 12, 29), date(2023, 12, 31)).collect()

    assert df["date"].to_list() == [date(2023, 12, 29)]
    assert calls == [xml_treasury._ARCHIVE_URL]


def test_get_rates_live_only_year_skips_archive(monkeypatch):
    calls = []

    def _fake_fetch_xml(url):
        calls.append(url)
        return _LIVE_2024_ROWS

    monkeypatch.setattr(xml_treasury, "_fetch_xml", _fake_fetch_xml)

    df = USTreasuryRates().get_rates(date(2024, 1, 1), date(2024, 1, 31)).collect()

    assert df["date"].to_list() == [date(2024, 1, 2), date(2024, 1, 3)]
    assert calls == [
        f"{xml_treasury._LIVE_BASE_URL}?data=daily_treasury_yield_curve&field_tdr_date_value=2024"
    ]
