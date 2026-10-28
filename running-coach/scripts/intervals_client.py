#!/usr/bin/env python3
"""
Intervals.icu REST API Client

Wraps all endpoints needed for running data analysis.
Auth: personal API key (Basic auth: -u API_KEY:api_key) or Bearer token.
Base URL: https://intervals.icu/api/v1
Date format: YYYY-MM-DD
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


BASE_URL = "https://intervals.icu/api/v1"
CONFIG_DIR = os.path.expanduser("~/.running_coach")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
REQUEST_DELAY = 0.5  # seconds between API calls to avoid rate limiting


class IntervalsClient:
    """Client for intervals.icu REST API."""

    def __init__(self, api_key: str = None, athlete_id: str = None,
                 config_name: str = "default"):
        """
        Initialize with API credentials.

        Priority: explicit args > config.json > environment variables.
        config_name allows multiple athlete profiles in config.json.
        """
        if api_key and athlete_id:
            self.api_key = api_key
            self.athlete_id = athlete_id
        else:
            config = self._load_config()
            profile = config.get(config_name, {})
            self.api_key = api_key or profile.get("api_key") or os.environ.get("INTERVALS_ICU_API_KEY")
            self.athlete_id = athlete_id or profile.get("athlete_id") or os.environ.get("INTERVALS_ICU_ATHLETE_ID")

        if not self.api_key:
            raise ValueError(
                "API key not found. Set it via:\n"
                "  1. intervals_client.py --init  (interactive setup)\n"
                "  2. ~/.running_coach/config.json\n"
                "  3. INTERVALS_ICU_API_KEY env var\n"
            )

    # ── Config ──────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def init_config(athlete_id: str, api_key: str, name: str = "default"):
        """Create or update config file interactively."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    pass
        config[name] = {"athlete_id": athlete_id, "api_key": api_key}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(json.dumps({"status": "ok", "message": f"Config saved for profile '{name}'"}))

    # ── HTTP Helpers ────────────────────────────────────────

    def _auth_headers(self) -> dict:
        """Basic auth with API key (personal API key method)."""
        import base64
        raw = f"API_KEY:{self.api_key}"
        encoded = base64.b64encode(raw.encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
        }

    def _request(self, path: str, method: str = "GET",
                 params: dict = None, body: dict = None,
                 athlete_specific: bool = True) -> dict:
        """Make an API request with error handling."""
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urlencode(params, doseq=True)

        data = None
        if body:
            data = json.dumps(body).encode("utf-8")

        req = Request(url, data=data, method=method)
        headers = self._auth_headers()
        for k, v in headers.items():
            req.add_header(k, v)
        if body:
            req.add_header("Content-Type", "application/json")

        time.sleep(REQUEST_DELAY)  # rate limiting

        try:
            with urlopen(req, timeout=30) as resp:
                content = resp.read()
                if not content:
                    return {}
                return json.loads(content)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {error_body[:500]}") from e
        except URLError as e:
            raise RuntimeError(f"Connection error: {e.reason}") from e

    # ── Athlete ─────────────────────────────────────────────

    def get_athlete(self) -> dict:
        """Get authenticated athlete profile."""
        return self._request("/athlete/0")

    def get_sport_settings(self, sport: str = "Run") -> dict:
        """Get sport-specific settings (HR zones, FTP, etc.)."""
        return self._request(f"/athlete/0/sport-settings/{sport}")

    # ── Activities (completed workouts) ─────────────────────

    def get_activities(self, oldest: str = None, newest: str = None,
                       limit: int = None, activity_type: str = None) -> list:
        """
        Get completed activities.

        Params:
            oldest/newest: YYYY-MM-DD date strings
            limit: max results (default: all available)
            activity_type: filter by type (e.g. "Run", "Ride")
        """
        params = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        if limit:
            params["limit"] = limit

        # Request key running fields explicitly
        params["fields"] = (
            "id,name,type,start_date_local,distance,moving_time,"
            "average_speed,average_heartrate,max_heartrate,"
            "icu_training_load,icu_ctl,icu_atl,"
            "total_elevation_gain,icu_hr_zone_times,"
            "perceived_exertion,feel,description,"
            "average_temp,calories"
        )

        activities = self._request("/athlete/0/activities", params=params)

        # Filter by type if specified
        if activity_type and isinstance(activities, list):
            activities = [a for a in activities if a.get("type") == activity_type]

        return activities if isinstance(activities, list) else []

    def get_all_activities(self, activity_type: str = "Run",
                           days_back: int = 180) -> list:
        """
        Fetch all activities going back N days, handling pagination.

        Since the API may limit result counts, this makes multiple
        requests in chunks to get full history.
        """
        all_activities = []
        newest = datetime.now().strftime("%Y-%m-%d")
        chunk_size = 90  # days per request

        for i in range(0, days_back, chunk_size):
            chunk_oldest = (datetime.now() - timedelta(days=min(i + chunk_size, days_back)))
            chunk_newest = (datetime.now() - timedelta(days=i))

            batch = self.get_activities(
                oldest=chunk_oldest.strftime("%Y-%m-%d"),
                newest=chunk_newest.strftime("%Y-%m-%d"),
                activity_type=activity_type,
            )
            all_activities.extend(batch)

        return all_activities

    def get_best_efforts(self, distances_m: list = None) -> dict:
        """
        Find personal bests from activity history.

        Params:
            distances_m: list of distances in meters to check
                        (e.g. [5000, 10000, 21097, 42195])
        Returns:
            {5000: {"time": 1200, "date": "2024-01-15", "activity_id": "i123"}, ...}
        """
        if distances_m is None:
            distances_m = [1000, 5000, 10000, 21097, 42195]

        activities = self.get_all_activities("Run", days_back=730)  # 2 years
        bests = {}

        for dist in distances_m:
            best = None
            for a in activities:
                distance = a.get("distance", 0)
                # Check if this activity covers the distance
                if distance and distance >= dist * 0.95:  # within 5%
                    # Estimate time for exact distance
                    moving_time = a.get("moving_time", 0)
                    avg_speed = a.get("average_speed", 0)
                    if moving_time and avg_speed:
                        # Estimate time for the exact distance
                        est_time = dist / avg_speed
                        if best is None or est_time < best["time"]:
                            best = {
                                "time": round(est_time),
                                "date": a.get("start_date_local", ""),
                                "activity_id": a.get("id", ""),
                                "distance_actual": distance,
                                "moving_time_actual": moving_time,
                            }

            if best:
                best["time_str"] = format_seconds(best["time"])
                bests[dist] = best

        return bests

    # ── Wellness (CTL/ATL/HRV/etc.) ─────────────────────────

    def get_wellness(self, oldest: str = None, newest: str = None) -> list:
        """
        Get wellness data: CTL, ATL, HRV, resting HR, sleep, weight, etc.

        Returns list of daily records.
        """
        params = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        params["fields"] = (
            "id,ctl,atl,rampRate,"
            "restingHR,hrv,"
            "sleepTime,sleepScore,"
            "weight,"
            "fatigue,soreness,stress,mood,motivation,"
            "icu_training_load"
        )

        data = self._request("/athlete/0/wellness", params=params)
        return data if isinstance(data, list) else []

    def get_current_fitness(self) -> dict:
        """Get latest fitness snapshot: CTL, ATL, TSB (form)."""
        newest = datetime.now().strftime("%Y-%m-%d")
        oldest = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        wellness = self.get_wellness(oldest=oldest, newest=newest)

        if not wellness:
            return {}

        # Get latest record with CTL
        latest = None
        for w in sorted(wellness, key=lambda x: x.get("id", ""), reverse=True):
            if w.get("ctl") is not None:
                latest = w
                break

        if not latest:
            return {}
        if latest is wellness[-1]:
            latest = wellness[-1]

        ctl = latest.get("ctl", 0)
        atl = latest.get("atl", 0)
        tsb = ctl - atl if ctl and atl else None

        return {
            "date": latest.get("id"),
            "ctl": ctl,
            "atl": atl,
            "tsb": tsb,
            "ramp_rate": latest.get("rampRate"),
            "hrv": latest.get("hrv"),
            "resting_hr": latest.get("restingHR"),
        }

    # ── Events (planned workouts / calendar) ────────────────

    def get_events(self, oldest: str = None, newest: str = None,
                   category: str = None) -> list:
        """Get calendar events (planned workouts)."""
        params = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        if category:
            params["category"] = category

        # Request useful fields
        params["fields"] = (
            "id,name,category,start_date_local,description,"
            "icu_training_load,type,"
            "athlete_cannot_edit,hide_from_athlete"
        )

        data = self._request("/athlete/0/events", params=params)
        return data if isinstance(data, list) else []

    def push_events(self, events: list, upsert: bool = True) -> dict:
        """
        Push planned workouts to the calendar.

        Params:
            events: list of event dicts with keys:
                - name: workout name
                - description: MRC/ZWO formatted workout content
                - start_date_local: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS"
                - category: "WORKOUT" (default)
                - icu_training_load: optional TSS estimate
            upsert: use upsertOnUid to avoid duplicates
        Returns: API response
        """
        params = {"upsertOnUid": "true"} if upsert else {}
        body = [{
            "name": e.get("name", "Running Workout"),
            "description": e.get("description", ""),
            "start_date_local": e.get("start_date_local"),
            "category": e.get("category", "WORKOUT"),
            "type": e.get("type", "Run"),
            "icu_training_load": e.get("icu_training_load"),
        } for e in events]

        return self._request("/athlete/0/events/bulk", method="POST",
                             params=params, body=body)

    def delete_events_in_range(self, oldest: str, newest: str) -> int:
        """
        Delete all events in a date range. Use with caution!

        Returns count of deleted events.
        """
        events = self.get_events(oldest=oldest, newest=newest)
        count = 0
        for e in events:
            try:
                eid = e.get("id")
                if eid:
                    self._request(f"/athlete/0/events/{eid}", method="DELETE")
                    count += 1
            except RuntimeError:
                pass
        return count


# ── Utility Functions ───────────────────────────────────────

def format_seconds(seconds: int) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_pace(seconds_per_km: float) -> str:
    """Format pace as mm:ss/km."""
    m = int(seconds_per_km // 60)
    s = int(seconds_per_km % 60)
    return f"{m}:{s:02d}/km"


def seconds_to_pace_str(total_seconds: int, distance_m: float) -> str:
    """Convert total time + distance to pace string."""
    if distance_m <= 0:
        return "N/A"
    pace_s = total_seconds / (distance_m / 1000)
    return format_pace(pace_s)


def km_to_mile(km: float) -> float:
    return km * 0.621371


# ── CLI Entry Point ─────────────────────────────────────────

def main():
    """CLI for testing and standalone use."""
    import argparse

    parser = argparse.ArgumentParser(description="Intervals.icu API Client")
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Setup API credentials")
    init_p.add_argument("--athlete-id", required=True)
    init_p.add_argument("--api-key", required=True)
    init_p.add_argument("--name", default="default")

    # athlete
    sub.add_parser("athlete", help="Get athlete profile")
    sub.add_parser("fitness", help="Get current fitness snapshot")
    sub.add_parser("zones", help="Get running HR/power zones")

    # activities
    act_p = sub.add_parser("activities", help="Get recent activities")
    act_p.add_argument("--days", type=int, default=30)
    act_p.add_argument("--type", default="Run")

    # best efforts
    be_p = sub.add_parser("bests", help="Get personal bests")
    be_p.add_argument("--distances", nargs="+", type=int,
                      default=[1000, 5000, 10000, 21097, 42195])

    # wellness
    well_p = sub.add_parser("wellness", help="Get wellness data")
    well_p.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.command == "init":
        IntervalsClient.init_config(args.athlete_id, args.api_key, args.name)
        return

    client = IntervalsClient()

    try:
        if args.command == "athlete":
            print(json.dumps(client.get_athlete(), indent=2, ensure_ascii=False))
        elif args.command == "fitness":
            print(json.dumps(client.get_current_fitness(), indent=2, ensure_ascii=False))
        elif args.command == "zones":
            print(json.dumps(client.get_sport_settings("Run"), indent=2, ensure_ascii=False))
        elif args.command == "activities":
            activities = client.get_activities(
                oldest=(datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
            )
            # Filter by type
            if args.type:
                activities = [a for a in activities if a.get("type") == args.type]
            print(json.dumps(activities, indent=2, ensure_ascii=False))
        elif args.command == "bests":
            bests = client.get_best_efforts(args.distances)
            print(json.dumps(bests, indent=2, ensure_ascii=False))
        elif args.command == "wellness":
            wellness = client.get_wellness(
                oldest=(datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
            )
            print(json.dumps(wellness, indent=2, ensure_ascii=False))
        else:
            # Default: show fitness snapshot
            fitness = client.get_current_fitness()
            print(json.dumps({"fitness": fitness}, indent=2, ensure_ascii=False))
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
