# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date

# Third-party imports
import pandas as pd

# First-party imports
from xpectral.data.rest_databento import DatabentoREST

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Two quotes as ``DBNStore.to_df`` returns them: ``ts_recv`` is the index and
# ``symbol`` is the raw OCC symbol.
_QUOTES = pd.DataFrame(
    {
        "symbol": ["AAPL  240119C00190000", "AAPL1 240119P00007500"],
        "bid_px_00": [3.10, 0.05],
        "ask_px_00": [3.20, 0.10],
    },
    index=pd.Index(
        pd.to_datetime(["2024-01-02 14:31", "2024-01-02 14:31"], utc=True),
        name="ts_recv",
    ),
)

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def test_get_option_quotes_parses_occ_symbols_and_tags_ticker():
    requests = []

    class _FakeStore:
        def to_df(self, tz):
            return _QUOTES.tz_convert(tz)

    class _FakeTimeseries:
        def get_range(self, **kwargs):
            requests.append(kwargs)
            return _FakeStore()

    client = DatabentoREST(api_key="db-" + "x" * 29)
    client._client.timeseries = _FakeTimeseries()

    df = client.get_option_quotes(["AAPL"], "2024-01-02", "2024-01-03").collect()

    assert requests[0]["symbols"] == ["AAPL.OPT"]
    assert requests[0]["stype_in"] == "parent"
    assert df.columns[:7] == [
        "ts_recv",
        "ticker",
        "symbol",
        "root",
        "expiration",
        "option_type",
        "strike",
    ]
    assert df["ticker"].to_list() == ["AAPL", "AAPL"]
    assert df["root"].to_list() == ["AAPL", "AAPL1"]
    assert df["expiration"].to_list() == [date(2024, 1, 19), date(2024, 1, 19)]
    assert df["option_type"].to_list() == ["C", "P"]
    assert df["strike"].to_list() == [190.0, 7.5]
    assert str(df["ts_recv"].dtype.time_zone) == "America/New_York"
