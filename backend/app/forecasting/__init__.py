"""Weekly demand forecasting per SKU (phase 5a).

Modelled level: units per SKU per Monday week, from weekly_sales. Region and channel
figures are a top-down allocation of the SKU forecast (app.services.forecast_read),
never modelled.

    calendar.py    known-in-advance inputs: festival windows, planned promotions
    data.py        the weekly history, and `until()`, the only way a model sees it
    models/        seasonal naive, ETS, Prophet, LightGBM behind one interface
    intervals.py   80% / 95% intervals from backtest errors, the same for every model
    metrics.py     WAPE, bias, MASE, coverage
    oracle.py      the ONLY module that reads the ground truth: expected demand and
                   shock weeks, for scoring. No model or feature may import it.
    backtest.py    rolling origins, scoring, champions
    production.py  champions trained on all history: the forecast the app shows
    store.py       runs, forecasts and metrics in the database
    report.py      docs/backtest-report.md
"""
