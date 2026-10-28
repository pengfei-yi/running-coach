#!/usr/bin/env python3
"""
Workout Advisor — Daily Training Recommendations

Analyzes current fitness state (CTL/ATL/TSB/HRV), recent activity history,
and training balance to recommend today's workout type, intensity, and
specific workout structure.

Usage:
  python workout_advisor.py                   # recommend today's workout
  python workout_advisor.py --json            # JSON output
  python workout_advisor.py --days 7          # show 7-day plan suggestions
"""

import json
import sys
import os
from datetime import datetime, timedelta
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervals_client import IntervalsClient


class WorkoutAdvisor:
    """Analyze training state and recommend workouts."""

    def __init__(self, client: IntervalsClient):
        self.client = client

    def advisor(self, lookback_days: int = 30) -> dict:
        """
        Generate workout recommendation for today.

        Considers:
        1. Current fitness state (CTL, ATL, TSB)
        2. HRV and resting HR trends
        3. Recent workout composition (what have you been doing?)
        4. Training balance (are you missing anything?)

        Returns: recommendation dict with rationale
        """
        result = {"date": datetime.now().strftime("%Y-%m-%d")}

        # ── 1. Current state ──
        fitness = self.client.get_current_fitness()
        result["fitness"] = {
            "ctl": fitness.get("ctl"),
            "atl": fitness.get("atl"),
            "tsb": fitness.get("tsb"),
            "hrv": fitness.get("hrv"),
            "resting_hr": fitness.get("resting_hr"),
        }

        # ── 2. Recent activity analysis ──
        oldest = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        activities = self.client.get_activities(oldest=oldest)
        runs = [a for a in activities if a.get("type") == "Run"]

        result["recent"] = self._analyze_recent(runs)

        # ── 3. Wellness trend ──
        wellness_data = self.client.get_wellness(oldest=oldest)
        result["wellness_trend"] = self._wellness_trend(wellness_data)

        # ── 4. Generate recommendation ──
        result["recommendation"] = self._recommend(result)

        return result

    def _analyze_recent(self, runs: list) -> dict:
        """Analyze recent running activities."""
        if not runs:
            return {
                "runs_last_7d": 0,
                "runs_last_30d": 0,
                "total_km_7d": 0,
                "total_km_30d": 0,
                "last_run_days_ago": None,
                "workout_types": None,
                "note": "No recent runs found — time to lace up!",
            }

        now = datetime.now()
        week_ago = now - timedelta(days=7)

        # Weekly stats
        recent_runs = [r for r in runs if r.get("start_date_local")]
        recent_runs.sort(key=lambda x: x["start_date_local"], reverse=True)

        runs_7d = [r for r in recent_runs
                   if datetime.fromisoformat(r["start_date_local"]) >= week_ago]

        total_km_7d = sum(r.get("distance", 0) for r in runs_7d) / 1000
        total_km_30d = sum(r.get("distance", 0) for r in runs) / 1000

        # Last run
        last_run_date = None
        if recent_runs:
            last_run_date = datetime.fromisoformat(recent_runs[0]["start_date_local"])
            days_since = (now - last_run_date).days
        else:
            days_since = None

        # Classify recent workout types based on distance/speed
        workout_types = self._classify_runs(recent_runs[:14])

        return {
            "runs_last_7d": len(runs_7d),
            "runs_last_30d": len(runs),
            "total_km_7d": round(total_km_7d, 1),
            "total_km_30d": round(total_km_30d, 1),
            "last_run_days_ago": days_since,
            "workout_types": workout_types,
        }

    def _classify_runs(self, runs: list) -> dict:
        """Classify recent runs into workout types based on patterns."""
        if not runs:
            return {}

        types = {
            "easy": 0,
            "long": 0,
            "tempo": 0,
            "intervals": 0,
            "short": 0,
        }

        distances = [r.get("distance", 0) for r in runs]
        avg_dist = sum(distances) / len(distances) if distances else 0

        for r in runs:
            dist = r.get("distance", 0) or 0
            moving_time = r.get("moving_time", 0) or 0
            avg_speed = r.get("average_speed", 0) or 0

            if moving_time > 0:
                pace_kmh = avg_speed * 3.6  # m/s to km/h
            else:
                pace_kmh = 0

            # Classify
            if dist >= avg_dist * 1.8 and dist > 10000:
                types["long"] += 1
            elif pace_kmh and pace_kmh > 13.0:  # faster than ~4:36/km
                types["intervals"] += 1
            elif pace_kmh and pace_kmh > 11.5:  # faster than ~5:13/km
                types["tempo"] += 1
            elif dist < 5000:
                types["short"] += 1
            else:
                types["easy"] += 1

        # Determine if any type is missing
        total = sum(types.values())
        if total == 0:
            return {}

        missing = [k for k, v in types.items() if v == 0]
        dominant = max(types, key=types.get)

        return {
            "counts": types,
            "dominant": dominant,
            "missing": missing,
            "balance_score": self._balance_score(types),
        }

    def _balance_score(self, types: dict) -> str:
        """Rate training balance."""
        total = sum(types.values())
        if total < 5:
            return "not_enough_data"

        easy_pct = types.get("easy", 0) / total
        hard_pct = (types.get("tempo", 0) + types.get("intervals", 0)) / total
        long_pct = types.get("long", 0) / total

        if easy_pct < 0.5:
            return "too_much_intensity"
        if easy_pct > 0.9:
            return "all_easy"
        if long_pct < 0.05 and total > 10:
            return "missing_long_runs"
        if hard_pct < 0.05 and total > 10:
            return "missing_quality"
        return "good_balance"

    def _wellness_trend(self, wellness_data: list) -> dict:
        """Analyze wellness trends."""
        if len(wellness_data) < 7:
            return {"trend": "insufficient_data", "days": len(wellness_data)}

        recent = sorted(wellness_data, key=lambda x: x.get("id", ""), reverse=True)

        # HRV trend (higher is better)
        hrv_values = [w.get("hrv") for w in recent[:14] if w.get("hrv")]
        resting_hr_values = [w.get("restingHR") for w in recent[:14] if w.get("restingHR")]

        result = {"days_analyzed": len(wellness_data)}

        if hrv_values:
            half = len(hrv_values) // 2
            recent_hrv = sum(hrv_values[:half]) / max(1, half)
            older_hrv = sum(hrv_values[half:]) / max(1, len(hrv_values[half:]))
            result["hrv"] = {
                "current": hrv_values[0],
                "avg_recent": round(recent_hrv, 1),
                "trend": "up" if recent_hrv > older_hrv * 1.05 else (
                    "down" if recent_hrv < older_hrv * 0.95 else "stable"
                ),
            }

        if resting_hr_values:
            half = len(resting_hr_values) // 2
            recent_rhr = sum(resting_hr_values[:half]) / max(1, half)
            older_rhr = sum(resting_hr_values[half:]) / max(1, len(resting_hr_values[half:]))
            result["resting_hr"] = {
                "current": resting_hr_values[0],
                "avg_recent": round(recent_rhr, 1),
                "trend": "up" if recent_rhr > older_rhr * 1.03 else (
                    "down" if recent_rhr < older_rhr * 0.97 else "stable"
                ),
            }

        # Fatigue/stress trend
        fatigue_values = [w.get("fatigue") for w in recent[:14] if w.get("fatigue") is not None]
        if fatigue_values:
            result["subjective_fatigue"] = {
                "current": fatigue_values[0],
                "avg": round(sum(fatigue_values) / len(fatigue_values), 1),
            }

        return result

    def _recommend(self, state: dict) -> dict:
        """
        Generate workout recommendation based on all analyzed data.

        Decision tree:
        1. If very low TSB (< -25) → recovery or rest
        2. If low TSB (-25 to -10) → easy run or short quality
        3. If moderate TSB (-10 to 5) → normal training
        4. If high TSB (> 5) → hard workout opportunity
        5. Consider workout type balance (what haven't you done?)
        """
        fitness = state.get("fitness", {})
        recent = state.get("recent", {})
        tsb = fitness.get("tsb")
        ctl = fitness.get("ctl", 0)
        hrv_trend = state.get("wellness_trend", {}).get("hrv", {}).get("trend")
        rhr_trend = state.get("wellness_trend", {}).get("resting_hr", {}).get("trend")
        balance = recent.get("workout_types", {}).get("balance_score", "unknown")
        missing_types = recent.get("workout_types", {}).get("missing", [])

        # Override: no runs in 7+ days → just go run
        if recent.get("last_run_days_ago", 0) and recent["last_run_days_ago"] >= 7:
            return {
                "decision": "easy_run",
                "urgency": "important",
                "title": "🟢 Lace Up — It's Been a While!",
                "description": f"No run in {recent['last_run_days_ago']} days. Start with an easy 5-8km at conversational pace. Don't try to make up for lost time — ease back in.",
                "intensity": "Zone 1-2 (easy/conversational)",
                "suggested_duration": "30-50 min",
                "suggested_distance": "5-8 km",
                "rationale": ["Extended break from running", "Need to ease back in"],
            }

        # Decision logic
        if tsb is not None:
            if tsb < -30:
                decision, urgency, title = "rest", "critical", "🔴 Rest Day — Deep Fatigue Detected"
                description = (
                    f"TSB ({tsb:.0f}) is very low, indicating significant accumulated fatigue. "
                    "Prioritize sleep (8+ hours), hydration, and nutrition. "
                    "If you must move, a 20-minute walk or light stretching only."
                )
                intensity = "N/A"
                duration = "0 min, active recovery only"

            elif tsb < -20:
                decision, urgency, title = "easy", "recommended", "🟡 Recovery Run — TSB Low"
                description = (
                    f"TSB ({tsb:.0f}) indicates fatigue accumulation. "
                    "Today calls for a recovery run: 4-6km very easy (Zone 1 only). "
                    "Focus on form and relaxation over pace. Better to rest than push through."
                )
                intensity = "Zone 1 (recovery pace, very easy)"
                duration = "25-40 min"
                suggested_km = "4-6 km"

                return {
                    "decision": decision,
                    "urgency": urgency,
                    "title": title,
                    "description": description,
                    "intensity": intensity,
                    "suggested_duration": duration,
                    "suggested_distance": suggested_km,
                    "rationale": [f"TSB very low at {tsb:.0f}", "Recovery needed before next quality session"],
                }

            elif tsb < -10:
                decision, urgency, title = "easy_or_short_quality", "suggested", "🟢 Easy Day — Moderate Fatigue"
                description = (
                    f"TSB ({tsb:.0f}) is moderately low. "
                    "An easy run (7-10km, Zone 2) is appropriate. "
                    "If feeling good, you could add 4-6 strides after the run."
                )
                intensity = "Zone 2 (easy/aerobic)"
                duration = "40-60 min"

            elif tsb > 10:
                decision, urgency, title = "hard_workout", "opportunity", "🟣 PRIME TIME — Hit a Quality Session!"
                description = (
                    f"TSB ({tsb:.0f}) is high — you're fit and rested. "
                    "This is the best time for a breakthrough workout."
                )
                intensity = "Depends on workout type"

                # What quality session is needed?
                if "intervals" in missing_types or "tempo" in missing_types:
                    decision = "intervals_or_tempo"
                    description += (
                        " You haven't done quality work recently. "
                        "Suggestion: 5×800m @VO2max pace with 400m jog recovery, "
                        "or a 20-min tempo run at threshold pace."
                    )
                    suggested_wod = {
                        "name": "VO2max Intervals or Tempo",
                        "structure": [
                            "15 min warmup (Zone 1-2)",
                            "5×800m @5K pace (Zone 5) with 400m jog recovery",
                            "OR 20 min continuous @threshold (Zone 4)",
                            "10 min cooldown (Zone 1)",
                        ],
                        "total_km": "10-12 km",
                        "duration": "60-70 min",
                    }
                elif "long" in missing_types:
                    decision = "long_run"
                    description += (
                        " Time for a long run! "
                        "Aim for 25-30% of weekly mileage at Zone 2. "
                        "Practice race-day nutrition and hydration strategy."
                    )
                    suggested_wod = {
                        "name": "Endurance Long Run",
                        "structure": [
                            "Start at easy pace, settle into Zone 2",
                            "Maintain steady effort for full duration",
                            "Last 2-3km at goal race effort (optional)",
                        ],
                        "total_km": "15-25 km (25-30% of weekly volume)",
                        "duration": "90-150 min",
                    }
                else:
                    decision = "race_specific"
                    description += (
                        " Training is well-balanced. Option: race-specific session "
                        "(e.g., marathon pace blocks) or a progression run."
                    )
                    suggested_wod = {
                        "name": "Race-Specific Session",
                        "structure": [
                            "15 min warmup (Zone 1-2)",
                            "3×3km @goal race pace with 1km easy recovery",
                            "10 min cooldown (Zone 1)",
                        ],
                        "total_km": "14-16 km",
                        "duration": "70-80 min",
                    }

                return {
                    "decision": decision,
                    "urgency": urgency,
                    "title": title,
                    "description": description,
                    "intensity": intensity,
                    "suggested_workout": suggested_wod,
                    "rationale": [
                        f"TSB high at {tsb:.0f} — primed for quality",
                        f"Training balance: {balance}, missing: {missing_types}",
                    ],
                }

            else:
                decision, urgency, title = "normal", "suggested", "🔵 Normal Training Day"
                description = (
                    f"TSB ({tsb:.0f}) is in the normal range. "
                    "Follow your regular training schedule. "
                    "Priority: consistency over intensity today."
                )
                intensity = "Zone 2 (easy/aerobic) — add strides if feeling snappy"

        else:
            decision, urgency, title = "normal", "suggested", "🔵 Train as Planned"
            description = "TSB data unavailable. Follow your regular schedule."
            intensity = "Zone 2 (easy/aerobic)"

        # Add HRV/RHR context
        rationale = [f"TSB: {tsb:.0f}" if tsb is not None else "TSB: unavailable"]
        if hrv_trend == "down":
            rationale.append("HRV trending down — body may be stressed")
            if decision not in ("rest", "easy"):
                description += " ⚠️ HRV is trending down — consider reducing intensity."
        if rhr_trend == "up":
            rationale.append("Resting HR trending up — possible fatigue signal")

        # Add balance context
        if balance == "too_much_intensity":
            rationale.append("Too much intensity recently — need more easy runs")
            if decision != "rest":
                description += " Note: recent training has been intensity-heavy. Prioritize easy runs."
        elif balance == "all_easy":
            rationale.append("Only easy runs recently — time to add quality")
            description += " Note: all recent runs have been easy. Consider adding a tempo or interval session soon."

        return {
            "decision": decision,
            "urgency": urgency,
            "title": title,
            "description": description,
            "intensity": intensity,
            "suggested_duration": "45-60 min",
            "suggested_distance": "8-12 km",
            "rationale": rationale,
        }


# ── CLI ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Workout Advisor")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--days", type=int, default=30,
                        help="Lookback days for analysis (default: 30)")
    args = parser.parse_args()

    client = IntervalsClient()
    advisor = WorkoutAdvisor(client)

    try:
        result = advisor.advisor(lookback_days=args.days)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # Friendly text output
            rec = result.get("recommendation", {})
            fitness = result.get("fitness", {})
            recent = result.get("recent", {})

            print(rec.get("title", "Workout Recommendation"))
            print("=" * 60)
            print(f"\n📊 Fitness: CTL {fitness.get('ctl', '?'):.0f} | "
                  f"ATL {fitness.get('atl', '?'):.0f} | "
                  f"TSB {fitness.get('tsb', '?') or 'N/A'}")
            if fitness.get("hrv"):
                print(f"   HRV: {fitness['hrv']}ms | Resting HR: {fitness.get('resting_hr', '?') or 'N/A'}")

            print(f"\n📅 Recent: {recent.get('runs_last_7d', 0)} runs / "
                  f"{recent.get('total_km_7d', 0)}km in last 7 days")
            last = recent.get("last_run_days_ago")
            if last is not None:
                print(f"   Last run: {last} day(s) ago")

            print(f"\n💡 Recommendation:")
            print(f"   {rec.get('description', 'Follow your regular schedule.')}")
            print(f"   Intensity: {rec.get('intensity', 'Zone 2')}")

            if rec.get("suggested_workout"):
                wod = rec["suggested_workout"]
                print(f"\n🏋️ Suggested Workout: {wod['name']}")
                print(f"   Duration: {wod['duration']} | Distance: {wod['total_km']}")
                print("   Structure:")
                for step in wod["structure"]:
                    print(f"     • {step}")

            print(f"\n🔍 Rationale:")
            for r in rec.get("rationale", []):
                print(f"   • {r}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
