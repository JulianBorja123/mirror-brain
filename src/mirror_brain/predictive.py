"""
Mirror Brain v3 — Predictive Engine.
Temporal pattern detection and projection for entity emotional trajectories.

Uses only stdlib: math, statistics, datetime, json, sqlite3.
No external dependencies required.
"""

import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .tools import EMOTION_INDICES


class PredictiveEngine:
    """Temporal pattern detection and projection engine.

    Operates on the daily_index table to detect cycles, project future
    values, flag anomalies, report trends, and find correlations
    between entities.

    All computation is done manually with Python stdlib only
    (math, statistics, datetime, json, sqlite3).
    """

    def __init__(self, registry):
        """Initialise the predictive engine.

        Args:
            registry: An EntityRegistry instance with .db and .resolve().
        """
        self.registry = registry
        self._ensure_projections_table()

    # ── Schema ──────────────────────────────────────────────────

    def _ensure_projections_table(self):
        """Create the projections table if it doesn't exist."""
        self.registry.db.execute("""
            CREATE TABLE IF NOT EXISTS projections (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_uuid     TEXT NOT NULL,
                metric          TEXT NOT NULL,
                projected_value REAL NOT NULL,
                confidence      REAL NOT NULL,
                horizon_days    INTEGER NOT NULL,
                method          TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT ''
            )
        """)
        self.registry.db.commit()

    # ── Internal helpers ─────────────────────────────────────────

    def _resolve_entity(self, entity_name: str) -> tuple[Optional[str], str]:
        """Resolve entity name to UUID and a searchable name.

        Tries registry.resolve() first. Falls back to the raw name
        so LIKE searches on key_entities still work.

        Returns (uuid_or_none, search_name).
        """
        uuid_ = None
        try:
            uuid_ = self.registry.resolve(entity_name)
        except Exception:
            pass

        if uuid_:
            info = None
            try:
                info = self.registry.get(uuid_)
            except Exception:
                pass
            search_name = (
                info.get("canonical_name", entity_name) if info else entity_name
            )
        else:
            search_name = entity_name

        return uuid_, search_name

    def _get_metric_index(self, metric: str) -> int:
        """Look up the positional index of *metric* in emotional_arc."""
        idx = EMOTION_INDICES.get(metric)
        if idx is None:
            raise ValueError(
                f"Unknown metric: {metric!r}. "
                f"Valid metrics: {list(EMOTION_INDICES.keys())}"
            )
        return idx

    def _fetch_entity_series(
        self,
        entity_name: str,
        metric: str,
        limit: Optional[int] = None,
    ) -> list[tuple[str, float]]:
        """Fetch a time series of *metric* values for *entity_name*.

        Scans daily_index rows whose key_entities contains
        *entity_name*, extracts the metric from emotional_arc,
        and returns a list of (date_str, value) ordered by date
        ascending.

        Args:
            entity_name: Entity canonical name or alias.
            metric: Emotion metric name.
            limit: If set, return only the most recent N rows.

        Returns:
            List of (date_str, value) tuples.
        """
        _, search_name = self._resolve_entity(entity_name)
        metric_idx = self._get_metric_index(metric)

        try:
            rows = self.registry.db.execute(
                "SELECT date, emotional_arc FROM daily_index "
                "WHERE key_entities LIKE ? "
                "  AND emotional_arc != '[]' "
                "  AND emotional_arc != '' "
                "ORDER BY date ASC",
                (f"%{search_name}%",),
            ).fetchall()
        except Exception:
            return []

        series: list[tuple[str, float]] = []
        for row in rows:
            try:
                arc = json.loads(row[1]) if row[1] else []
            except (json.JSONDecodeError, TypeError):
                continue
            if len(arc) <= metric_idx:
                continue
            series.append((row[0], float(arc[metric_idx])))

        if limit is not None and len(series) > limit:
            series = series[-limit:]

        return series

    # ── Statistical primitives (stdlib only) ─────────────────────

    @staticmethod
    def _pearson_r(x: list[float], y: list[float]) -> float:
        """Compute Pearson correlation coefficient manually.

        Returns 0.0 when variance is zero or inputs are too short.
        """
        n = len(x)
        if n < 2 or n != len(y):
            return 0.0

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        # Sum of squared deviations
        ss_x = sum((xi - mean_x) ** 2 for xi in x)
        ss_y = sum((yi - mean_y) ** 2 for yi in y)

        if ss_x == 0 or ss_y == 0:
            return 0.0

        # Covariance
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))

        # Pearson r = cov / sqrt(ss_x * ss_y)
        return cov / math.sqrt(ss_x * ss_y)

    @staticmethod
    def _linear_regression(y: list[float]) -> tuple[float, float, float]:
        """Simple linear regression: y = slope * x + intercept.

        x values are assumed equally spaced: 0, 1, 2, …, n-1.

        Returns:
            (slope, intercept, r_squared)
        """
        n = len(y)
        if n < 2:
            return 0.0, (y[0] if y else 0.0), 0.0

        # x = [0, 1, 2, …, n-1]; mean_x = (n-1)/2
        mean_x = (n - 1) / 2.0
        mean_y = statistics.mean(y)

        # Slope = Σ((x_i - x̄)(y_i - ȳ)) / Σ((x_i - x̄)²)
        num = 0.0
        den = 0.0
        for i in range(n):
            dx = i - mean_x
            dy = y[i] - mean_y
            num += dx * dy
            den += dx * dx

        slope = num / den if den != 0 else 0.0
        intercept = mean_y - slope * mean_x

        # R-squared
        ss_res = 0.0
        ss_tot = 0.0
        for i in range(n):
            y_pred = slope * i + intercept
            ss_res += (y[i] - y_pred) ** 2
            ss_tot += (y[i] - mean_y) ** 2

        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        # Clamp to [0, 1] — can go slightly negative with a terrible fit
        r_squared = max(0.0, min(1.0, r_squared))

        return slope, intercept, r_squared

    # ── 1. Cycle detection ───────────────────────────────────────

    def detect_cycles(
        self,
        entity_name: str,
        metric: str = "oxytocin",
    ) -> dict:
        """Detect periodic cycles in an entity's emotional metric.

        Uses autocorrelation-like detection: computes the Pearson
        correlation between the time series and lagged copies of
        itself.  The lag with the highest correlation (beyond lag 0)
        is reported as the detected period.

        Args:
            entity_name: Entity canonical name or alias.
            metric: Emotion metric name (default 'oxytocin').

        Returns:
            {
                'has_cycle': bool,
                'period_days': int,
                'confidence': float,
            }
        """
        series = self._fetch_entity_series(entity_name, metric)

        if len(series) < 6:
            return {"has_cycle": False, "period_days": 0, "confidence": 0.0}

        values = [v for _, v in series]
        n = len(values)

        max_lag = n // 2
        best_lag = 0
        best_corr = -1.0

        for lag in range(2, max_lag + 1):
            # Aligned series: later portion vs earlier portion shifted by lag
            x = values[lag:]      # later values
            y = values[:-lag]     # earlier (lagged) values

            if len(x) < 3:
                continue

            r = self._pearson_r(x, y)

            # Also consider half-lag (harmonic) with a small discount
            half_lag = lag // 2
            if half_lag >= 2:
                xh = values[half_lag:]
                yh = values[:-half_lag]
                if len(xh) >= 3:
                    rh = self._pearson_r(xh, yh)
                    r = max(r, rh * 0.9)

            if r > best_corr:
                best_corr = r
                best_lag = lag

        has_cycle = best_corr > 0.5
        confidence = round(max(0.0, min(1.0, best_corr)), 4)

        return {
            "has_cycle": has_cycle,
            "period_days": best_lag if has_cycle else 0,
            "confidence": confidence,
        }

    # ── 2. Forward projection ────────────────────────────────────

    def project_next(
        self,
        entity_name: str,
        metric: str,
        days: int = 7,
    ) -> list[dict]:
        """Project the next N days using moving average + linear trend.

        Uses the last 14–30 days of data (preferring 30 when
        available).  Combines a simple moving average of the most
        recent 7 days with a linear trend fitted over the full
        window.  Projections are persisted in the ``projections``
        table.

        Args:
            entity_name: Entity canonical name or alias.
            metric: Emotion metric name.
            days: Number of days to project forward (default 7).

        Returns:
            List of ``{day, value, confidence}`` dicts.
        """
        uuid_, _ = self._resolve_entity(entity_name)
        series = self._fetch_entity_series(entity_name, metric)

        if len(series) < 7:
            return []

        # Use the last 14–30 days of data
        window = min(30, max(14, len(series)))
        recent = series[-window:]
        values = [v for _, v in recent]

        # Simple moving average of the last 7 available days
        sma_window = min(7, len(values))
        sma = statistics.mean(values[-sma_window:])

        # Linear trend over the full window
        slope, intercept, r_squared = self._linear_regression(values)

        # Blend trend projection with SMA for the base level
        last_trend_x = len(values) - 1
        last_trend_y = slope * last_trend_x + intercept
        base = 0.6 * last_trend_y + 0.4 * sma

        # Confidence: blend r² quality with data-quantity factor
        data_factor = min(1.0, len(series) / 30.0)
        confidence = round(min(1.0, max(0.1, r_squared)) * data_factor, 4)

        # Parse the last date for forward-day computation
        last_date_str = recent[-1][0]
        try:
            last_date = date.fromisoformat(last_date_str)
        except (ValueError, TypeError):
            last_date = date.today()

        projections: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for i in range(1, days + 1):
            projected_value = round(base + slope * i, 4)
            proj_date = last_date + timedelta(days=i)

            # Confidence decays with horizon distance
            horizon_confidence = round(
                confidence * max(0.05, 1.0 - 0.05 * i), 4
            )

            projections.append({
                "day": proj_date.isoformat(),
                "value": projected_value,
                "confidence": horizon_confidence,
            })

            # Persist to projections table
            if uuid_:
                try:
                    self.registry.db.execute(
                        "INSERT INTO projections "
                        "(entity_uuid, metric, projected_value, "
                        " confidence, horizon_days, method, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            uuid_,
                            metric,
                            projected_value,
                            horizon_confidence,
                            i,
                            "trend+sma",
                            now,
                        ),
                    )
                except Exception:
                    pass

        try:
            self.registry.db.commit()
        except Exception:
            pass

        return projections

    # ── 3. Anomaly detection ─────────────────────────────────────

    def anomaly_detect(
        self,
        entity_name: str,
        metric: str,
    ) -> list[dict]:
        """Flag outlier days using mean ± 2σ on the last 30 days.

        Args:
            entity_name: Entity canonical name or alias.
            metric: Emotion metric name.

        Returns:
            List of ``{date, value, zscore}`` dicts for flagged
            outliers.
        """
        series = self._fetch_entity_series(entity_name, metric, limit=30)

        if len(series) < 5:
            return []

        values = [v for _, v in series]
        mean = statistics.mean(values)
        std = (
            statistics.stdev(values)
            if len(values) > 1
            else 0.0
        )

        if std == 0:
            return []

        anomalies: list[dict] = []
        for date_str, val in series:
            zscore = (val - mean) / std
            if abs(zscore) > 2.0:
                anomalies.append({
                    "date": date_str,
                    "value": val,
                    "zscore": round(zscore, 4),
                })

        return anomalies

    # ── 4. Trend report ──────────────────────────────────────────

    def trend_report(
        self,
        entity_name: str,
        metric: str = "oxytocin",
        window: int = 30,
    ) -> dict:
        """Linear regression trend report on the last *window* days.

        Args:
            entity_name: Entity canonical name or alias.
            metric: Emotion metric name (default 'oxytocin').
            window: Number of days to analyse (default 30).

        Returns:
            {
                'direction': 'up' | 'down' | 'stable',
                'slope': float,
                'r_squared': float,
                'confidence': float,
            }
        """
        series = self._fetch_entity_series(entity_name, metric, limit=window)

        if len(series) < 5:
            return {
                "direction": "stable",
                "slope": 0.0,
                "r_squared": 0.0,
                "confidence": 0.0,
            }

        values = [v for _, v in series]
        slope, intercept, r_squared = self._linear_regression(values)

        # Normalise slope relative to the value range for direction
        value_range = max(values) - min(values)
        if value_range == 0:
            normalised_slope = 0.0
        else:
            # Scale slope to per-day change as fraction of range
            normalised_slope = (slope * len(values)) / value_range

        if normalised_slope > 0.1:
            direction = "up"
        elif normalised_slope < -0.1:
            direction = "down"
        else:
            direction = "stable"

        confidence = round(max(0.0, min(1.0, r_squared)), 4)

        return {
            "direction": direction,
            "slope": round(slope, 6),
            "r_squared": round(r_squared, 4),
            "confidence": confidence,
        }

    # ── 5. Cross-entity correlation ──────────────────────────────

    def correlation_find(
        self,
        entity_a: str,
        entity_b: str,
        metric: str,
    ) -> dict:
        """Compute Pearson r between two entities' emotional arcs.

        Only days where **both** entities appear in key_entities are
        used.  The metric values are aligned by date before computing
        the correlation.

        Args:
            entity_a: First entity canonical name or alias.
            entity_b: Second entity canonical name or alias.
            metric: Emotion metric name.

        Returns:
            {
                'pearson_r': float,
                'shared_days': int,
                'direction': 'positive' | 'negative' | 'none',
                'confidence': float,
            }
        """
        series_a = self._fetch_entity_series(entity_a, metric)
        series_b = self._fetch_entity_series(entity_b, metric)

        if not series_a or not series_b:
            return {
                "pearson_r": 0.0,
                "shared_days": 0,
                "direction": "none",
                "confidence": 0.0,
            }

        # Index series B by date for fast lookup
        b_by_date: dict[str, float] = {d: v for d, v in series_b}

        # Align on shared dates (preserve order from series_a)
        aligned_a: list[float] = []
        aligned_b: list[float] = []
        for date_str, val in series_a:
            if date_str in b_by_date:
                aligned_a.append(val)
                aligned_b.append(b_by_date[date_str])

        if len(aligned_a) < 3:
            return {
                "pearson_r": 0.0,
                "shared_days": len(aligned_a),
                "direction": "none",
                "confidence": 0.0,
            }

        r = self._pearson_r(aligned_a, aligned_b)
        r = round(r, 4)

        if r > 0.3:
            direction = "positive"
        elif r < -0.3:
            direction = "negative"
        else:
            direction = "none"

        # Confidence: strength of |r| modulated by sample size
        data_factor = min(1.0, len(aligned_a) / 15.0)
        confidence = round(abs(r) * data_factor, 4)

        return {
            "pearson_r": r,
            "shared_days": len(aligned_a),
            "direction": direction,
            "confidence": confidence,
        }
