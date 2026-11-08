from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, enum_type, utcnow
from app.models.enums import ForecastRunKind, MetricWindow, ShockScope


class ForecastRun(Base):
    """One training run: a production forecast, or a backtest that scored every model.

    Enough to reproduce it: the data it saw (data_end_date, training_cutoff), the
    parameters and champions (params), the library versions and the random seed.
    """

    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ForecastRunKind] = mapped_column(enum_type(ForecastRunKind, "forecast_run_kind"))
    model: Mapped[str] = mapped_column(sa.String(40))  # "champion" (production) or "all" (backtest)
    data_end_date: Mapped[date] = mapped_column(sa.Date)  # last day with sales data
    training_cutoff: Mapped[date] = mapped_column(sa.Date)  # Monday of the last training week
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    params: Mapped[dict] = mapped_column(sa.JSON)
    library_versions: Mapped[dict] = mapped_column(sa.JSON)
    random_seed: Mapped[int] = mapped_column(sa.Integer)
    duration_seconds: Mapped[float] = mapped_column(sa.Float)


class Forecast(Base):
    """Weekly units for one SKU, horizon 1-26: the median and 80% / 95% intervals.

    Integer units, like every quantity here (and so byte-stable). `model` is the model
    that produced the row: a production run holds each SKU's champion. The intervals come
    from the model's own backtest errors, so a biased model can have its p50 outside its
    80% interval; the p50 is never moved into it (that would be a silent bias correction).
    """

    __tablename__ = "forecasts"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "product_id", "week", name="uq_forecasts_run_product_week"),
        sa.Index("ix_forecasts_product_run", "product_id", "run_id"),
        sa.CheckConstraint("horizon BETWEEN 1 AND 26", name="horizon_range"),
        sa.CheckConstraint("p50 >= 0 AND lo95 >= 0 AND lo95 <= lo80 AND lo80 <= hi80 AND hi80 <= hi95",
                           name="intervals_ordered"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(sa.ForeignKey("forecast_runs.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"))
    week: Mapped[date] = mapped_column(sa.Date)  # Monday
    horizon: Mapped[int] = mapped_column(sa.SmallInteger)
    model: Mapped[str] = mapped_column(sa.String(40))
    p50: Mapped[int] = mapped_column(sa.Integer)
    lo80: Mapped[int] = mapped_column(sa.Integer)
    hi80: Mapped[int] = mapped_column(sa.Integer)
    lo95: Mapped[int] = mapped_column(sa.Integer)
    hi95: Mapped[int] = mapped_column(sa.Integer)


class BacktestMetric(Base):
    """One score: a model (or "champion", "oracle") on one SKU (NULL = the headline SKUs
    pooled), one window, with or without shock weeks, at one horizon (NULL = 1-26 pooled).
    Coverage is NULL on the selection window, where the intervals were calibrated."""

    __tablename__ = "backtest_metrics"
    __table_args__ = (sa.Index("ix_backtest_metrics_run_model", "run_id", "model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(sa.ForeignKey("forecast_runs.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(sa.String(40))
    product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("products.id"))
    window: Mapped[MetricWindow] = mapped_column(enum_type(MetricWindow, "metric_window"))
    shocks: Mapped[ShockScope] = mapped_column(enum_type(ShockScope, "shock_scope"))
    horizon: Mapped[int | None] = mapped_column(sa.SmallInteger)
    n_weeks: Mapped[int] = mapped_column(sa.Integer)
    wape: Mapped[float | None] = mapped_column(sa.Float)
    bias: Mapped[float | None] = mapped_column(sa.Float)
    mase: Mapped[float | None] = mapped_column(sa.Float)
    coverage_80: Mapped[float | None] = mapped_column(sa.Float)
    coverage_95: Mapped[float | None] = mapped_column(sa.Float)
