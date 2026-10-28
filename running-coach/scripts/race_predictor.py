#!/usr/bin/env python3
"""
Race Time Predictor

Predicts race performance using multiple methods:
1. Riegel formula:  T2 = T1 × (D2/D1)^1.06
2. CTL-based adjustment (higher fitness → better endurance)
3. Daniels' VDOT (VO2max equivalent) method
4. Recent training load trend analysis

Usage:
  python race_predictor.py 42195          # predict full marathon
  python race_predictor.py 21097 --json   # predict half marathon, JSON output
  python race_predictor.py 42195 --method all --days 90
"""

import json
import sys
import math
from datetime import datetime, timedelta
from typing import Optional

# Add parent dir to path for importing intervals_client
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervals_client import (
    IntervalsClient, format_seconds, format_pace, km_to_mile
)


# ── Race distances reference ────────────────────────────────

RACE_DISTANCES = {
    "5k": 5000,
    "10k": 10000,
    "15k": 15000,
    "half": 21097.5,  # half marathon
    "25k": 25000,
    "30k": 30000,
    "marathon": 42195,  # full marathon
    "50k": 50000,
    "50m": 80467,
    "100k": 100000,
}

RACE_NAMES = {v: k for k, v in RACE_DISTANCES.items()}


def parse_distance(d: str) -> float:
    """Parse distance string like 'marathon', 'half', '10k', '42195'."""
    d_lower = d.lower().replace(" ", "").replace("_", "")
    if d_lower in RACE_DISTANCES:
        return RACE_DISTANCES[d_lower]
    try:
        return float(d)
    except ValueError:
        raise ValueError(f"Unknown distance: {d}. Try: 5k, 10k, half, marathon")


# ── Prediction Models ───────────────────────────────────────

def riegel_formula(t1_seconds: float, d1_m: float, d2_m: float) -> float:
    """
    Riegel formula: T2 = T1 × (D2/D1)^β
    β = 1.06 (standard), or adjust for ultra distances.

    Reference: Peter Riegel, "Athletics Records and Human Endurance"
    """
    # Adjust beta for very long distances
    if d2_m > 42195:
        beta = 1.07
    elif d2_m < 3000:
        beta = 1.05
    else:
        beta = 1.06

    return t1_seconds * ((d2_m / d1_m) ** beta)


def riegel_from_multiple(performances: list, target_m: float) -> dict:
    """
    Predict target race time using Riegel formula from multiple recent performances.

    performances: list of {"distance_m": float, "time_s": float, "date": str}
    target_m: target race distance in meters

    Returns: predicted time, range, and individual predictions
    """
    if not performances:
        return {"error": "No performance data available"}

    predictions = []
    for perf in performances:
        try:
            pred = riegel_formula(perf["time_s"], perf["distance_m"], target_m)
            predictions.append({
                "from_distance": perf["distance_m"],
                "from_time_s": perf["time_s"],
                "from_time_str": format_seconds(perf["time_s"]),
                "from_date": perf.get("date", ""),
                "predicted_time_s": round(pred),
                "predicted_time_str": format_seconds(round(pred)),
                "predicted_pace": format_pace(pred / (target_m / 1000)),
            })
        except Exception:
            continue

    if not predictions:
        return {"error": "Could not compute predictions"}

    times = [p["predicted_time_s"] for p in predictions]
    avg_time = sum(times) / len(times)
    stdev = (sum((t - avg_time) ** 2 for t in times) / len(times)) ** 0.5

    return {
        "target_distance_m": target_m,
        "target_name": RACE_NAMES.get(target_m, f"{target_m/1000:.1f}k"),
        "predicted_time_s": round(avg_time),
        "predicted_time_str": format_seconds(round(avg_time)),
        "predicted_pace": format_pace(avg_time / (target_m / 1000)),
        "confidence_range": {
            "optimistic": format_seconds(round(max(0, avg_time - stdev))),
            "conservative": format_seconds(round(avg_time + stdev)),
        },
        "stdev_seconds": round(stdev),
        "num_predictions": len(predictions),
        "individual_predictions": predictions,
    }


def daniels_vdot(race_time_s: float, race_distance_m: float) -> float:
    """
    Estimate VDOT (VO2max equivalent) using Daniels' formula.

    Reference: Jack Daniels, "Daniels' Running Formula"

    VDOT = f(time, distance) using the formulas from the tables.
    This uses an approximation from Daniels' book.
    """
    # Convert to minutes and meters
    time_min = race_time_s / 60
    dist_km = race_distance_m / 1000

    # VDOT is estimated from race performance
    # Using simplified formula for marathon and shorter
    velocity = dist_km / (time_min / 60)  # km/h

    # Calculate % of VO2max sustainable for this duration
    # Simplified from Daniels' tables
    if time_min < 10:
        percent_vo2max = 0.98
    elif time_min < 30:
        percent_vo2max = 0.95
    elif time_min < 60:
        percent_vo2max = 0.92
    elif time_min < 120:
        percent_vo2max = 0.88
    elif time_min < 180:
        percent_vo2max = 0.85
    elif time_min < 240:
        percent_vo2max = 0.82
    else:
        percent_vo2max = 0.80

    # VO2 = velocity * oxygen cost per km (ml/kg/min)
    oxygen_cost = velocity * 4.0 / percent_vo2max  # Simplified

    return oxygen_cost


def vdot_predicted_time(vdot: float, target_distance_m: float) -> float:
    """Given a VDOT value, predict time for a target distance."""
    dist_km = target_distance_m / 1000

    # Estimate sustainable velocity from VDOT
    time_min = dist_km / (vdot / 4.0)  # rough approximation

    # Adjust for duration-specific efficiency
    if time_min < 10:
        factor = 0.98
    elif time_min < 30:
        factor = 0.95
    elif time_min < 60:
        factor = 0.92
    elif time_min < 120:
        factor = 0.88
    elif time_min < 180:
        factor = 0.85
    elif time_min < 240:
        factor = 0.82
    else:
        factor = 0.80

    time_min = dist_km / (vdot * factor / 4.0)
    return time_min * 60  # back to seconds


def ctl_adjustment(prediction_s: float, ctl: float,
                   target_distance_m: float) -> dict:
    """
    Adjust prediction based on Chronic Training Load (CTL).

    Higher CTL → better prepared for longer distances.
    CTL is effectively a "fitness" score based on TSS/d training load.
    """
    dist_km = target_distance_m / 1000

    # CTL ranges and adjustment factors
    if ctl <= 0:
        return {"adjustment": 1.0, "note": "Insufficient training data (CTL=0), no adjustment"}

    # Marathon-specific CTL benchmarks
    # CTL 30-40: basic fitness
    # CTL 40-60: good aerobic base
    # CTL 60-80: strong, can handle marathon
    # CTL 80+: elite level

    if dist_km < 10:
        # Short races: CTL matters less
        ctl_expected = 30
    elif dist_km < 25:
        ctl_expected = 50
    elif dist_km < 45:
        ctl_expected = 70
    else:
        ctl_expected = 85

    # If CTL is below expected, prediction is optimistic
    # If CTL is above expected, prediction is accurate or conservative
    if ctl >= ctl_expected:
        adjustment = 1.0  # Well prepared, prediction is reliable
        note = f"CTL {ctl:.0f} ≥ {ctl_expected:.0f}, well prepared"
    else:
        # Penalty factor: less fit = slower
        ratio = ctl / ctl_expected
        # Non-linear: small gaps matter more
        if ratio > 0.8:
            adjustment = 1.0 + (1 - ratio) * 0.15
            note = f"CTL {ctl:.0f} is slightly below target {ctl_expected:.0f}"
        elif ratio > 0.6:
            adjustment = 1.15 + (0.8 - ratio) * 0.5
            note = f"CTL {ctl:.0f} is moderately below target {ctl_expected:.0f}"
        else:
            adjustment = 1.25 + (0.6 - ratio) * 1.0
            note = f"CTL {ctl:.0f} is significantly below target {ctl_expected:.0f}"

    return {"adjustment": adjustment, "note": note}


def recent_training_trend(client: IntervalsClient, days: int = 42) -> dict:
    """Analyze recent training trend for prediction confidence."""
    wellness = client.get_wellness(
        oldest=(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    )

    if len(wellness) < 7:
        return {"trend": "unknown", "confidence": "low",
                "note": "Insufficient wellness data (< 7 days)"}

    # Calculate CTL trend (last 7 days vs previous 7 days)
    recent = sorted(wellness, key=lambda x: x.get("id", ""), reverse=True)
    last_week = [w.get("ctl", 0) for w in recent[:7] if w.get("ctl") is not None]
    prev_week = [w.get("ctl", 0) for w in recent[7:14] if w.get("ctl") is not None]

    if not last_week or not prev_week:
        return {"trend": "unknown", "confidence": "low"}

    avg_last = sum(last_week) / len(last_week)
    avg_prev = sum(prev_week) / len(prev_week)

    if avg_last - avg_prev > 0.5:
        trend = "increasing"
        confidence = "medium"
        note = "Fitness is improving (+{:.1f} CTL/week)".format(avg_last - avg_prev)
    elif avg_last - avg_prev < -0.5:
        trend = "decreasing"
        confidence = "low"
        note = "Fitness is declining ({:.1f} CTL/week), prediction may be optimistic".format(avg_last - avg_prev)
    else:
        trend = "stable"
        confidence = "good"
        note = "Fitness is stable"

    return {"trend": trend, "confidence": confidence, "note": note}


# ── Main Predictor ──────────────────────────────────────────

class RacePredictor:
    """Combined race time predictor using multiple methods."""

    def __init__(self, client: IntervalsClient):
        self.client = client

    def predict(self, target_distance_m: float,
                method: str = "all", days: int = 180) -> dict:
        """
        Predict race time for target distance.

        Params:
            target_distance_m: target race distance in meters
            method: "riegel", "vdot", "all"
            days: lookback period for training data

        Returns: comprehensive prediction dict
        """
        result = {
            "target": {
                "distance_m": target_distance_m,
                "distance_name": RACE_NAMES.get(target_distance_m,
                                                  f"{target_distance_m/1000:.1f}K"),
                "distance_km": round(target_distance_m / 1000, 1),
                "predicted_at": datetime.now().isoformat(),
            },
        }

        # Get recent activities (runs only)
        oldest = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        activities = self.client.get_all_activities("Run", days_back=days)

        runs = [a for a in activities if a.get("type") == "Run" and a.get("distance", 0) > 0]

        if not runs:
            return {"error": f"No running activities found in the last {days} days"}

        result["data_summary"] = {
            "total_runs": len(runs),
            "lookback_days": days,
            "total_distance_km": round(sum(a.get("distance", 0) for a in runs) / 1000, 1),
            "avg_pace": self._avg_pace(runs),
            "longest_run_km": round(max(a.get("distance", 0) for a in runs) / 1000, 1),
        }

        # ── 1. Performance-based predictions ──
        performances = []
        for a in runs:
            distance = a.get("distance", 0)
            moving_time = a.get("moving_time", 0)
            if distance >= 1000 and moving_time > 0:  # at least 1km
                performances.append({
                    "distance_m": distance,
                    "time_s": moving_time,
                    "date": a.get("start_date_local", ""),
                })

        if method in ("riegel", "all"):
            # Use the 5 best recent performances (sorted by distance/time ratio)
            performances_sorted = sorted(
                performances,
                key=lambda p: p["distance_m"] / max(p["time_s"], 1),
                reverse=True
            )[:5]

            riegel_result = riegel_from_multiple(performances_sorted, target_distance_m)
            if "error" not in riegel_result:
                result["riegel"] = riegel_result

        # ── 2. CTL-based adjustment ──
        fitness = self.client.get_current_fitness()
        ctl = fitness.get("ctl", 0)

        result["fitness"] = {
            "ctl": ctl,
            "atl": fitness.get("atl", 0),
            "tsb": fitness.get("tsb"),
            "hrv": fitness.get("hrv"),
            "resting_hr": fitness.get("resting_hr"),
        }

        # Apply CTL adjustment to Riegel prediction
        if "riegel" in result:
            ctl_adj = ctl_adjustment(
                result["riegel"]["predicted_time_s"],
                ctl,
                target_distance_m
            )
            result["riegel"]["ctl_adjustment"] = ctl_adj
            adjusted_time = round(result["riegel"]["predicted_time_s"] * ctl_adj["adjustment"])
            result["riegel"]["adjusted_time_s"] = adjusted_time
            result["riegel"]["adjusted_time_str"] = format_seconds(adjusted_time)
            result["riegel"]["adjusted_pace"] = format_pace(
                adjusted_time / (target_distance_m / 1000)
            )

        # ── 3. Training trend ──
        result["training_trend"] = recent_training_trend(self.client)

        # ── 4. Final recommendation ──
        result["recommendation"] = self._recommendation(result, target_distance_m)

        return result

    def _avg_pace(self, runs: list) -> str:
        """Calculate weighted average pace from runs."""
        total_time = sum(a.get("moving_time", 0) for a in runs)
        total_dist = sum(a.get("distance", 0) for a in runs)
        if total_dist > 0:
            return format_pace(total_time / (total_dist / 1000))
        return "N/A"

    def _recommendation(self, result: dict, target_distance_m: float) -> list:
        """Generate human-readable recommendations."""
        recs = []

        dist_km = target_distance_m / 1000
        trend = result.get("training_trend", {})
        fitness = result.get("fitness", {})
        ctl = fitness.get("ctl", 0)
        tsb = fitness.get("tsb")

        # Check training volume vs race distance
        data = result.get("data_summary", {})
        longest_km = data.get("longest_run_km", 0)

        if dist_km > 21 and longest_km < dist_km * 0.7:
            recs.append(
                f"⚠️ Longest run ({longest_km:.0f}km) is less than 70% of target "
                f"({dist_km:.0f}km). Build up long runs gradually before race day."
            )

        # Check CTL
        if dist_km > 21 and ctl < 40:
            recs.append("📉 CTL is low for marathon. Focus on consistent base building with 3-4 easy runs + 1 long run per week.")
        elif dist_km > 21 and ctl < 60:
            recs.append("🔧 CTL is moderate. Add quality sessions (tempo, intervals) to your base mileage.")
        elif dist_km <= 21 and ctl < 30:
            recs.append("📉 CTL is low. Increase weekly mileage gradually (no more than 10% per week).")

        # Check TSB (form)
        if tsb is not None:
            if tsb > 10:
                recs.append("💪 High TSB: you're well-rested. Good time for a quality workout or race!")
            elif tsb < -25:
                recs.append("😴 Low TSB: you're fatigued. Prioritize recovery and easy runs.")
            elif tsb < -10:
                recs.append("😐 Negative TSB: training load is high. Monitor sleep and nutrition carefully.")

        # Training trend
        if trend.get("trend") == "increasing":
            recs.append("📈 Fitness is improving — prediction may be conservative.")
        elif trend.get("trend") == "decreasing":
            recs.append("📉 Fitness is declining — consider reducing intensity and building volume.")

        if not recs:
            recs.append("✅ Current training looks solid for your target. Stay consistent!")

        return recs

    def predict_benchmark(self) -> dict:
        """Predict all common race distances (5K/10K/Half/Full)."""
        distances = [5000, 10000, 21097.5, 42195]
        result = {"benchmarks": {}}
        for d in distances:
            pred = self.predict(d, method="riegel")
            if "riegel" in pred:
                result["benchmarks"][RACE_NAMES[d]] = {
                    "predicted": pred["riegel"]["predicted_time_str"],
                    "pace": pred["riegel"]["predicted_pace"],
                }
                if "adjusted_time_str" in pred["riegel"]:
                    result["benchmarks"][RACE_NAMES[d]]["adjusted"] = pred["riegel"]["adjusted_time_str"]

        result["fitness"] = self.client.get_current_fitness()
        result["recommendations"] = self.predict(42195).get("recommendation", [])
        return result


# ── CLI ─────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Race Time Predictor")
    parser.add_argument("distance", nargs="?", default="42195",
                        help="Target distance (5k, 10k, half, marathon, or meters)")
    parser.add_argument("--method", default="all",
                        choices=["riegel", "vdot", "all"])
    parser.add_argument("--days", type=int, default=180,
                        help="Days of training data to analyze (default: 180)")
    parser.add_argument("--benchmark", action="store_true",
                        help="Predict all common race distances")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON")

    args = parser.parse_args()
    client = IntervalsClient()
    predictor = RacePredictor(client)

    try:
        if args.benchmark:
            result = predictor.predict_benchmark()
        else:
            target_m = parse_distance(args.distance)
            result = predictor.predict(target_m, method=args.method, days=args.days)

        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
