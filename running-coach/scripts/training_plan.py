#!/usr/bin/env python3
"""
Training Plan Generator

Generates periodized running training plans based on:
- Target race distance
- Race date
- Current weekly mileage / fitness level
- Available training days per week
- Goal time (optional)

Plan follows traditional periodization:
  Base → Build → Peak → Taper

Output: structured JSON plan + optional MRC format for intervals.icu import.

Usage:
  python training_plan.py marathon --date 2026-12-01          # marathon plan
  python training_plan.py half --date 2026-10-15 --days 5     # half marathon, 5 days/week
  python training_plan.py 10k --date 2026-09-20 --level intermediate
  python training_plan.py marathon --date 2026-12-01 --push   # push to intervals.icu
"""

import json
import sys
import os
import math
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervals_client import (
    IntervalsClient, format_seconds, format_pace
)
from race_predictor import RACE_DISTANCES, RACE_NAMES


# ── Training Plan Templates ─────────────────────────────────

# Key workout types
WORKOUT_TYPES = {
    "E": "Easy Run",      # recovery/easy
    "L": "Long Run",       # endurance long run
    "T": "Tempo Run",      # lactate threshold (comfortably hard)
    "I": "Intervals",      # VO2max intervals
    "R": "Repetitions",    # speed/form work
    "M": "Marathon Pace",  # race-specific at goal MP
    "F": "Fartlek",        # speed play
    "H": "Hills",          # hill repeats
    "S": "Strides",        # short sprints after easy run
    "X": "Cross Training", # non-running
    "OFF": "Rest Day",
}

# Plan templates by distance: {phase: (weeks, weekly_mileage_% of peak, key_workouts_per_week)}
PLAN_TEMPLATES = {
    "5k": {
        "base":    (4, 0.70, {"E": 3, "S": 1}),
        "build":   (4, 0.85, {"E": 2, "I": 1, "T": 1, "L": 1}),
        "peak":    (3, 1.00, {"E": 2, "I": 1, "R": 1, "L": 1}),
        "taper":   (1, 0.60, {"E": 2, "R": 1}),
    },
    "10k": {
        "base":    (4, 0.65, {"E": 3, "S": 1, "L": 1}),
        "build":   (5, 0.85, {"E": 2, "T": 1, "I": 1, "L": 1}),
        "peak":    (3, 1.00, {"E": 1, "T": 1, "I": 1, "L": 1}),
        "taper":   (1, 0.55, {"E": 3, "S": 1}),
    },
    "half": {
        "base":    (6, 0.60, {"E": 3, "L": 1, "S": 1}),
        "build":   (5, 0.80, {"E": 2, "T": 1, "L": 1, "I": 1}),
        "peak":    (4, 1.00, {"E": 1, "T": 1, "M": 1, "L": 1}),
        "taper":   (2, 0.50, {"E": 3, "S": 1}),
    },
    "marathon": {
        "base":    (8, 0.55, {"E": 3, "L": 1, "S": 1}),
        "build":   (6, 0.75, {"E": 2, "T": 1, "L": 1, "M": 1}),
        "peak":    (5, 1.00, {"E": 1, "M": 1, "L": 2, "T": 1}),
        "taper":   (3, 0.50, {"E": 3, "M": 1, "S": 1}),
    },
}


# ── Workout Descriptions Generator ──────────────────────────

def describe_workout(workout_type: str, weekly_mileage_km: float,
                     goal_pace: str = None, target_km: float = None) -> dict:
    """
    Generate a detailed workout description based on type and athlete level.

    Returns dict with name, description (plain text and MRC format),
    estimated duration and training load.
    """
    result = {"type": workout_type, "name": WORKOUT_TYPES.get(workout_type, "Run")}

    # Calculate workout distances based on weekly mileage
    daily_base = weekly_mileage_km / 5  # average daily distance

    if workout_type == "OFF":
        result.update({"distance_km": 0, "duration_min": 0, "description": "Rest day. Focus on recovery, hydration, and nutrition."})
        return result

    elif workout_type == "E":  # Easy/Recovery run
        dist = round(max(5, daily_base * 0.8), 1)
        duration = round(dist * 6.5)  # ~6:30/km easy pace assumption
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Easy run at conversational pace. Keep HR in Zone 1-2. "
                           f"Focus on form and breathing.",
            "mrc": f"- {dist:.1f}km Easy Run @Zone1-2",
        })

    elif workout_type == "L":  # Long run
        if target_km and target_km > 21:
            dist = round(max(10, weekly_mileage_km * 0.35), 1)  # 35% of weekly
        else:
            dist = round(max(8, weekly_mileage_km * 0.30), 1)
        duration = round(dist * 6.0)  # ~6:00/km
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Long run at easy to moderate effort. Build endurance. "
                           f"Keep HR mostly in Zone 2. Practice race-day nutrition strategy.",
            "mrc": f"- {dist:.1f}km Long Run @Zone2",
        })

    elif workout_type == "T":  # Tempo run
        warmup = round(max(3, daily_base * 0.4), 1)
        tempo = round(max(4, daily_base * 0.5), 1)
        cooldown = round(max(2, daily_base * 0.3), 1)
        dist = round(warmup + tempo + cooldown, 1)
        duration = round(warmup * 6.5 + tempo * 4.8 + cooldown * 7, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Warmup {warmup}km easy → {tempo}km at lactate threshold "
                           f"(comfortably hard, ~85% max HR) → Cooldown {cooldown}km easy.",
            "mrc": f"- {warmup:.1f}km Warmup @Zone1\n"
                   f"- {tempo:.1f}km Threshold @Zone4\n"
                   f"- {cooldown:.1f}km Cooldown @Zone1",
        })

    elif workout_type == "I":  # Intervals (VO2max)
        warmup = round(max(3, daily_base * 0.3), 1)
        cooldown = round(max(2, daily_base * 0.2), 1)
        repeats = 5
        interval_dist = 0.8  # 800m repeats
        recovery = 0.4  # 400m jog
        dist = round(warmup + (interval_dist + recovery) * repeats + cooldown, 1)
        duration = round(warmup * 6.5 + interval_dist * repeats * 4.2 + recovery * repeats * 7 + cooldown * 7, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Warmup {warmup}km → {repeats}×800m @VO2max pace "
                           f"with 400m jog recovery → Cooldown {cooldown}km.",
            "mrc": f"- {warmup:.1f}km Warmup @Zone1\n"
                   f"- {repeats}x(800m @Zone5, 400m recovery @Zone1)\n"
                   f"- {cooldown:.1f}km Cooldown @Zone1",
        })

    elif workout_type == "R":  # Repetitions (speed)
        warmup = round(max(3, daily_base * 0.3), 1)
        cooldown = round(max(2, daily_base * 0.2), 1)
        repeats = 8
        rep_dist = 0.2  # 200m
        recovery = 0.2  # 200m walk/jog
        dist = round(warmup + (rep_dist + recovery) * repeats + cooldown, 1)
        duration = round(warmup * 6.5 + 30, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Warmup {warmup}km → {repeats}×200m fast strides "
                           f"with 200m walk/jog recovery → Cooldown {cooldown}km. Focus on fast, relaxed form.",
            "mrc": f"- {warmup:.1f}km Warmup @Zone1\n"
                   f"- {repeats}x(200m @Sprint, 200m recovery)\n"
                   f"- {cooldown:.1f}km Cooldown @Zone1",
        })

    elif workout_type == "M":  # Marathon Pace
        if weekly_mileage_km > 60:
            mp_dist = round(max(10, daily_base * 1.2), 1)
        elif weekly_mileage_km > 40:
            mp_dist = round(max(8, daily_base * 1.0), 1)
        else:
            mp_dist = round(max(6, daily_base * 0.8), 1)
        dist = round(mp_dist, 1)
        duration = round(dist * 5.2, 1)  # ~5:12/km marathon pace
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Marathon pace run: {mp_dist}km at goal marathon pace. "
                           f"Practice race rhythm and fueling strategy.",
            "mrc": f"- {mp_dist:.1f}km Marathon Pace @Zone3-4",
        })

    elif workout_type == "F":  # Fartlek
        dist = round(daily_base * 1.1, 1)
        duration = round(dist * 5.5, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Fartlek run: Alternate fast and easy segments by feel. "
                           f"Suggested: 1min hard / 2min easy, repeat 8-10 times.",
            "mrc": f"- {dist:.1f}km Fartlek (1min hard / 2min easy)",
        })

    elif workout_type == "S":  # Strides
        dist = round(daily_base, 1)
        duration = round(dist * 6.2, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"{dist}km easy run with 4-6×100m strides at the end. "
                           f"Strides should be fast but relaxed — focus on good form.",
            "mrc": f"- {dist:.1f}km Easy Run @Zone2\n"
                   f"- 6x(100m Strides, 100m recovery)",
        })

    elif workout_type == "H":  # Hills
        warmup = round(max(3, daily_base * 0.3), 1)
        cooldown = round(max(2, daily_base * 0.2), 1)
        repeats = 6
        dist = round(warmup + 4 + cooldown, 1)  # hill repeats ~4km effective
        duration = round(dist * 5.5, 1)
        result.update({
            "distance_km": dist,
            "duration_min": duration,
            "description": f"Warmup {warmup}km → {repeats}×hill repeats "
                           f"(~200m, jog down recovery) → Cooldown {cooldown}km.",
            "mrc": f"- {warmup:.1f}km Warmup @Zone1\n"
                   f"- {repeats}x(200m Hill @Zone5, jog back recovery)\n"
                   f"- {cooldown:.1f}km Cooldown @Zone1",
        })

    else:
        result.update({"distance_km": 5, "duration_min": 33, "description": "Easy recovery run."})

    return result


# ── Plan Generator ──────────────────────────────────────────

class TrainingPlanGenerator:
    """Generate periodized training plans for running races."""

    def __init__(self, client: IntervalsClient):
        self.client = client

    def generate(self, target_distance_m: float, race_date: str,
                 days_per_week: int = 5, level: str = "auto",
                 weekly_km: float = None, goal_time_s: int = None) -> dict:
        """
        Generate a complete training plan.

        Params:
            target_distance_m: race distance in meters
            race_date: "YYYY-MM-DD" race day
            days_per_week: 3-7 training days per week
            level: "beginner", "intermediate", "advanced", or "auto" (detect from CTL)
            weekly_km: current weekly mileage (auto-detect if None)
            goal_time_s: goal finish time in seconds (auto-estimate if None)

        Returns: full plan dict with weeks, daily workouts, and summary
        """
        race_date = datetime.strptime(race_date, "%Y-%m-%d")
        today = datetime.now()
        total_days = (race_date - today).days

        if total_days < 14:
            return {"error": f"Only {total_days} days until race. Minimum 2 weeks needed for a meaningful plan."}

        # Determine the closest template
        template_key = self._select_template(target_distance_m)

        # Auto-detect level from fitness
        if level == "auto":
            fitness = self.client.get_current_fitness()
            ctl = fitness.get("ctl", 0)
            if ctl < 30:
                level = "beginner"
            elif ctl < 60:
                level = "intermediate"
            else:
                level = "advanced"

        # Auto-detect weekly mileage
        if weekly_km is None:
            weekly_km = self._detect_weekly_mileage()

        # Determine peak weekly mileage based on level and distance
        peak_km = self._peak_mileage(target_distance_m, level, weekly_km)

        # Calculate plan structure
        template = PLAN_TEMPLATES[template_key]
        plan_phases = self._calculate_phases(template, total_days)

        # Generate the plan
        plan = {
            "meta": {
                "target_distance_m": target_distance_m,
                "target_name": RACE_NAMES.get(target_distance_m),  # no format() needed
                "target_distance_km": round(target_distance_m / 1000, 1),
                "race_date": race_date.strftime("%Y-%m-%d"),
                "total_weeks": plan_phases["total_weeks"],
                "level": level,
                "peak_weekly_km": peak_km,
                "current_weekly_km": round(weekly_km, 1) if weekly_km else None,
                "goal_time": format_seconds(goal_time_s) if goal_time_s else None,
            },
            "phases": [],
            "weeks": [],
        }

        # Generate each phase
        current_date = today
        week_num = 1

        for phase_name, phase_info in plan_phases["phases"]:
            phase_weeks = phase_info["weeks"]
            phase_mileage_pct = phase_info["mileage_pct"]
            phase_key_workouts = phase_info["key_workouts"]

            phase_data = {
                "name": phase_name,
                "description": self._phase_description(phase_name, template_key),
                "weeks": phase_weeks,
                "start_date": current_date.strftime("%Y-%m-%d"),
            }

            week_plan = []
            for _ in range(phase_weeks):
                week_mileage = round(peak_km * phase_mileage_pct, 1)

                # Progressive mileage within phase
                if phase_name == "base":
                    ramp = min(1.0, 0.7 + 0.3 * (week_num / plan_phases["total_weeks"]))
                    week_mileage = round(week_mileage * ramp, 1)

                week = self._generate_week(
                    week_num=week_num,
                    phase=phase_name,
                    weekly_km=week_mileage,
                    days=days_per_week,
                    key_workouts=phase_key_workouts,
                    start_date=current_date,
                    template_key=template_key,
                    target_km=target_distance_m / 1000,
                )

                week_plan.append(week)
                current_date += timedelta(days=7)
                week_num += 1

            phase_data["end_date"] = current_date.strftime("%Y-%m-%d")
            plan["phases"].append(phase_data)
            plan["weeks"].extend(week_plan)

        # Summary stats
        plan["summary"] = self._plan_summary(plan)

        return plan

    def _select_template(self, distance_m: float) -> str:
        """Select the best template for the target distance."""
        if distance_m <= 8000:
            return "5k"
        elif distance_m <= 16000:
            return "10k"
        elif distance_m <= 30000:
            return "half"
        else:
            return "marathon"

    def _detect_weekly_mileage(self) -> float:
        """Detect current weekly mileage from recent activities."""
        try:
            oldest = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
            activities = self.client.get_activities(oldest=oldest)
            runs = [a for a in activities if a.get("type") == "Run"]
            if runs:
                total_km = sum(a.get("distance", 0) for a in runs) / 1000
                return round(total_km / 4, 1)  # average over 4 weeks
        except Exception:
            pass
        return 20.0  # default

    def _peak_mileage(self, distance_m: float, level: str,
                      current_km: float) -> float:
        """Determine peak weekly mileage."""
        dist_km = distance_m / 1000
        level_peaks = {
            "beginner": {"5k": 30, "10k": 40, "half": 50, "marathon": 60},
            "intermediate": {"5k": 50, "10k": 60, "half": 80, "marathon": 100},
            "advanced": {"5k": 80, "10k": 100, "half": 120, "marathon": 140},
        }
        template = self._select_template(distance_m)
        base_peak = level_peaks.get(level, {}).get(template, 50)

        # Don't exceed current mileage by more than 40%
        return min(base_peak, current_km * 1.4)

    def _calculate_phases(self, template: dict, total_days: int) -> dict:
        """Calculate phase distribution based on available weeks."""
        total_template_weeks = sum(v[0] for v in template.values())
        total_available_weeks = max(4, total_days // 7)

        if total_available_weeks >= total_template_weeks:
            # Full plan
            phases = [
                (name, {"weeks": info[0], "mileage_pct": info[1],
                        "key_workouts": info[2]})
                for name, info in template.items()
            ]
            total_weeks = total_template_weeks
        else:
            # Compressed plan: scale proportionally
            scale = total_available_weeks / total_template_weeks
            phases = []
            for name, info in template.items():
                weeks = max(1, round(info[0] * scale))
                phases.append((name, {
                    "weeks": weeks,
                    "mileage_pct": info[1] * (0.9 if name == "peak" else 1.0),
                    "key_workouts": info[2],
                }))
            total_weeks = total_available_weeks

        return {"phases": phases, "total_weeks": total_weeks}

    def _phase_description(self, phase: str, template: str) -> str:
        """Get human-readable phase description."""
        descriptions = {
            "base": "Base Phase — Build aerobic foundation with easy runs and steady mileage increase. "
                    "Focus on consistency and form. Introduce strides for neuromuscular fitness.",
            "build": "Build Phase — Introduce quality workouts: tempo runs, intervals, and race-pace segments. "
                     "Long run becomes a key weekly session. Focus on specific race demands.",
            "peak": "Peak Phase — Highest volume and intensity. Race-specific workouts simulate race conditions. "
                    "Long runs at race effort. Critical phase for confidence and fitness.",
            "taper": "Taper Phase — Reduce volume while maintaining intensity. "
                     "Goal: arrive at the start line fresh, fit, and ready to race.",
        }
        return descriptions.get(phase, f"{phase} phase of training.")

    def _generate_week(self, week_num: int, phase: str, weekly_km: float,
                       days: int, key_workouts: dict, start_date: datetime,
                       template_key: str, target_km: float) -> dict:
        """Generate a single week of training."""
        week = {
            "week": week_num,
            "phase": phase,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "total_km": round(weekly_km, 1),
            "days": [],
        }

        # Assign workout types to each day
        workout_schedule = self._assign_workouts(days, key_workouts, phase)
        daily_km = weekly_km / days

        for day_offset, workout_type in enumerate(workout_schedule):
            day_date = start_date + timedelta(days=day_offset)
            day_name = day_date.strftime("%A")

            workout = describe_workout(workout_type, weekly_km,
                                       target_km=target_km)

            week["days"].append({
                "day": day_offset + 1,
                "date": day_date.strftime("%Y-%m-%d"),
                "day_name": day_name,
                "type": workout_type,
                "name": workout["name"],
                "distance_km": workout["distance_km"],
                "duration_min": workout["duration_min"],
                "description": workout["description"],
            })

        return week

    def _assign_workouts(self, days: int, key_workouts: dict,
                         phase: str) -> list:
        """
        Assign workout types to days of the week.

        Rules:
        - Long run on Saturday or Sunday
        - Hard workouts never back-to-back
        - Rest days before/after long run when possible
        - Monday is default rest day for 5-day schedules
        """
        # Count how many of each workout type we need
        workout_counts = dict(key_workouts)
        total = sum(workout_counts.values())

        # If more workouts than days, scale down
        if total > days:
            scale = days / total
            workout_counts = {k: max(1, round(v * scale))
                            for k, v in workout_counts.items()}

        # Build schedule
        schedule = []

        if days == 3:
            schedule = self._assign_3day(workout_counts)
        elif days == 4:
            schedule = self._assign_4day(workout_counts)
        elif days == 5:
            schedule = self._assign_5day(workout_counts, phase)
        elif days == 6:
            schedule = self._assign_6day(workout_counts)
        else:
            schedule = self._assign_5day(workout_counts, phase)

        return schedule[:days]

    def _assign_3day(self, counts: dict) -> list:
        schedule = []
        for wtype, count in counts.items():
            schedule.extend([wtype] * count)
        # Sort: E first, L middle, hard last
        return sorted(schedule, key=lambda x: {"OFF": 0, "E": 1, "L": 2, "M": 3, "T": 4, "I": 5, "R": 6}.get(x, 7))

    def _assign_4day(self, counts: dict) -> list:
        out = []
        for wtype, count in counts.items():
            out.extend([wtype] * count)
        # Typical 4-day: E, (T/I), E, L
        easy = [x for x in out if x == "E"]
        hard = [x for x in out if x in ("T", "I", "R", "M")]
        long_runs = [x for x in out if x == "L"]
        other = [x for x in out if x not in ("E", "T", "I", "R", "M", "L")]

        result = easy[:1] + hard + other + easy[1:] + long_runs
        return result[:4]

    def _assign_5day(self, counts: dict, phase: str) -> list:
        out = []
        for wtype, count in counts.items():
            out.extend([wtype] * count)

        easy = [x for x in out if x == "E"]
        hard = [x for x in out if x in ("T", "I", "R")]
        marathon = [x for x in out if x == "M"]
        long_runs = [x for x in out if x == "L"]
        rest = [x for x in out if x == "OFF"]

        # Monday rest → Tue easy → Wed hard → Thu easy → Fri easy → Sat long → Sun off
        schedule = (rest[:1] + easy[:1] + hard[:1] + easy[1:2] +
                    marathon[:1] + long_runs[:1])
        # Pad with easy runs
        while len(schedule) < 7:
            schedule.insert(-1, "E")

        return schedule[:7]

    def _assign_6day(self, counts: dict) -> list:
        out = []
        for wtype, count in counts.items():
            out.extend([wtype] * count)

        easy = [x for x in out if x == "E"]
        hard = [x for x in out if x in ("T", "I", "R", "M")]
        long_runs = [x for x in out if x == "L"]
        rest = [x for x in out if x == "OFF"]

        # Mon easy → Tue hard → Wed easy → Thu hard → Fri easy → Sat long → Sun off
        schedule = (rest[:1] + easy[:1] + hard[:1] + easy[1:2] +
                    hard[1:2] + easy[2:3] + long_runs[:1])
        while len(schedule) < 7:
            schedule.insert(len(schedule) - 1, "E")

        return schedule[:7]

    def _plan_summary(self, plan: dict) -> dict:
        """Generate summary statistics for the plan."""
        total_km = 0
        total_runs = 0
        total_duration = 0

        for week in plan["weeks"]:
            total_km += week["total_km"]
            for day in week["days"]:
                if day["type"] != "OFF":
                    total_runs += 1
                    total_duration += day["duration_min"]

        return {
            "total_km": round(total_km, 1),
            "total_runs": total_runs,
            "total_duration_hours": round(total_duration / 60, 1),
            "avg_weekly_km": round(total_km / max(1, len(plan["weeks"])), 1),
            "total_weeks": len(plan["weeks"]),
        }

    def format_plan_text(self, plan: dict) -> str:
        """Format plan as human-readable text."""
        lines = []
        meta = plan["meta"]
        summary = plan["summary"]

        lines.append("=" * 70)
        target_label = meta['target_name'] or f"{meta['target_distance_km']:.0f}K"
        lines.append(f"  🏃 TRAINING PLAN: {target_label}  |  "
                     f"Race Day: {meta['race_date']}")
        lines.append(f"  Level: {meta['level']}  |  "
                     f"Peak: {meta['peak_weekly_km']:.0f} km/week  |  "
                     f"Total: {summary['total_weeks']} weeks")
        if meta.get("goal_time"):
            lines.append(f"  🎯 Goal: {meta['goal_time']}")
        lines.append("=" * 70)

        for phase in plan["phases"]:
            lines.append(f"\n── {phase['name'].upper()} ({phase['weeks']} weeks) ──")
            lines.append(f"   {phase['description'][:100]}...")
            lines.append(f"   {phase['start_date']} → {phase['end_date']}")

        lines.append(f"\n{'─' * 70}")

        for week in plan["weeks"]:
            lines.append(f"\n📅 Week {week['week']} ({week['phase']}) — "
                         f"{week['start_date']} — {week['total_km']:.0f} km")
            for day in week["days"]:
                icon = "🔵" if day["type"] == "E" else \
                       "🟢" if day["type"] == "L" else \
                       "🟡" if day["type"] in ("T", "M") else \
                       "🟠" if day["type"] in ("I", "H") else \
                       "🔴" if day["type"] in ("R", "F") else \
                       "⚫" if day["type"] == "OFF" else "⚪"
                lines.append(f"  {icon} {day['day_name'][:3]} {day['date']} | {day['name']:12s} | "
                             f"{day['distance_km']:5.1f}km | {day['duration_min']:3.0f}min")
                if day["type"] != "OFF":
                    lines.append(f"     {day['description'][:80]}")

        lines.append(f"\n{'=' * 70}")
        lines.append(f"  📊 Total: {summary['total_km']:.0f} km over {summary['total_runs']} runs "
                     f"({summary['total_duration_hours']:.1f}h)")
        lines.append(f"  📈 Average: {summary['avg_weekly_km']:.0f} km/week")
        lines.append("=" * 70)

        return "\n".join(lines)


# ── Helpers for pushing to intervals.icu ────────────────────

def plan_to_events(plan: dict) -> list:
    """Convert a plan to intervals.icu event format for bulk push."""
    events = []
    for week in plan["weeks"]:
        for day in week["days"]:
            if day["type"] == "OFF":
                continue

            event = {
                "name": f"{week['phase'].title()} W{week['week']}D{day['day']}: {day['name']}",
                "start_date_local": day["date"] + "T06:00:00",
                "category": "WORKOUT",
                "type": "Run",
                "description": (
                    f"[{week['phase'].upper()} Week {week['week']}]\n\n"
                    f"{day['description']}\n\n"
                    f"Distance: {day['distance_km']:.1f}km\n"
                    f"Duration: ~{day['duration_min']:.0f}min"
                ),
            }
            events.append(event)
    return events


# ── CLI ─────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Training Plan Generator")
    parser.add_argument("distance", help="Race distance (5k, 10k, half, marathon, or meters)")
    parser.add_argument("--date", required=True, help="Race date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=5, help="Training days per week (3-7)")
    parser.add_argument("--level", default="auto",
                        choices=["auto", "beginner", "intermediate", "advanced"])
    parser.add_argument("--weekly-km", type=float, help="Current weekly mileage")
    parser.add_argument("--goal-time", help="Goal finish time (HH:MM:SS or MM:SS)")
    parser.add_argument("--push", action="store_true",
                        help="Push plan to intervals.icu calendar")
    parser.add_argument("--text", action="store_true", help="Output as formatted text")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    client = IntervalsClient()
    generator = TrainingPlanGenerator(client)

    # Parse distance
    if args.distance.lower() in RACE_DISTANCES:
        target_m = RACE_DISTANCES[args.distance.lower()]
    else:
        try:
            target_m = float(args.distance)
        except ValueError:
            print(json.dumps({"error": f"Unknown distance: {args.distance}"}))
            sys.exit(1)

    # Parse goal time
    goal_time_s = None
    if args.goal_time:
        parts = args.goal_time.split(":")
        if len(parts) == 2:
            goal_time_s = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            goal_time_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

    try:
        plan = generator.generate(
            target_distance_m=target_m,
            race_date=args.date,
            days_per_week=args.days,
            level=args.level,
            weekly_km=args.weekly_km,
            goal_time_s=goal_time_s,
        )

        if "error" in plan:
            print(json.dumps(plan))
            sys.exit(1)

        if args.push:
            events = plan_to_events(plan)
            client.push_events(events)
            print(json.dumps({
                "status": "ok",
                "pushed": len(events),
                "message": f"Pushed {len(events)} workouts to intervals.icu calendar"
            }))
        elif args.text:
            print(generator.format_plan_text(plan))
        elif args.json:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        else:
            # Default: print text + JSON summary
            print(generator.format_plan_text(plan))

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
