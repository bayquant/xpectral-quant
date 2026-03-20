#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports

# Other imports
import polars as pl

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

def ffill_inside(expr: pl.Expr) -> pl.Expr:
    # True from the start up to the *last* non-null; False after that
    mask = expr.is_not_null().reverse().cum_max().reverse()

    return pl.when(mask).then(expr.forward_fill()).otherwise(None)


df = pl.DataFrame({
    "a": [None, 1, None, 2, None, None],
    "b": [5, None, None, 7, None, 9],
})

df_out = df.with_columns(
    ffill_inside(pl.col("a")).alias("a"),
    ffill_inside(pl.col("b")).alias("b"),
)

print(df_out)

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------
