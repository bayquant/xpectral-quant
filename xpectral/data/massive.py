#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime
from functools import lru_cache
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
import os

# Other imports
from massive import RESTClient
from massive.rest.models import Sort
import polars as pl
from ..utils.rate_limiter import RateLimiter

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

client = RESTClient(
    api_key=os.getenv("MASSIVE_API_KEY", ""), pagination=True, trace=False
)
_rate_limiter = RateLimiter(calls=5, per_seconds=60)

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

def get_aggregate_bars(
        tickers: List[str],
        multiplier: int,
        timespan: str,
        from_: Union[str, int, datetime, date],
        to: Union[str, int, datetime, date],
        adjusted: Optional[bool] = True,
        sort: Optional[Union[str, Sort]] = None,
        limit: Optional[int] = None
        ):
    # create kwargs dictionary from local variables (copy to avoid mutating locals directly)
    kwargs = locals().copy()
    # convert tickers to tuple for caching (lru_cache)
    kwargs["tickers"] = tuple(kwargs["tickers"])

    df = _get_aggregate_bars(**kwargs)

    return df

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------

@lru_cache(maxsize=10)
def _get_aggregate_bars(**kwargs):
    tickers = list(kwargs.pop("tickers"))

    aggs = []
    for ticker in tickers:
        _rate_limiter.acquire()
        for a in client.list_aggs(ticker=ticker, **kwargs):
            data = a.__dict__
            timestamp = data["timestamp"]
            long_format = [
                {"timestamp": timestamp, "ticker": ticker, "metric": key, "value": value}
                for key, value in data.items() if key != "timestamp"
            ]
            aggs.extend(long_format)

    df = pl.DataFrame(data=aggs)

    # transform unix timestamp to daily format
    _FREQ_MAP = {
        "second": "1s",
        "minute": "1m",
    }
    df = df.with_columns(
        pl.col("timestamp")
        .cast(pl.Datetime("ms"))
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone("America/New_York")
        .dt.truncate(_FREQ_MAP.get(kwargs.pop("timespan"), "1d"))
    )

    # pivot polars dataframe to semi-wide format
    df = df.pivot(
        values="value",
        index=["timestamp", "ticker"],
        on="metric"
    )

    return df.lazy()
