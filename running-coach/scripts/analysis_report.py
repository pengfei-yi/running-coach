#!/usr/bin/env python3
"""
Training Analysis Report Generator

Generates an interactive HTML report with Chart.js visualizations:
- CTL/ATL/TSB fitness trend chart
- Weekly mileage bar chart
- Pace trend over time
- HR zone distribution pie chart
- Training load composition

Usage:
  python analysis_report.py                          # generate and open report
  python analysis_report.py --output report.html     # save to file
  python analysis_report.py --days 90                # 90-day analysis
"""

import json
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervals_client import IntervalsClient, format_seconds, format_pace


class AnalysisReport:
    """Generate comprehensive training analysis report."""

    def __init__(self, client: IntervalsClient):
        self.client = client

    def analyze(self, days_back: int = 90) -> dict:
        """Collect all analysis data."""
        oldest = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        newest = datetime.now().strftime("%Y-%m-%d")

        # Fetch all data
        activities = self.client.get_all_activities("Run", days_back=days_back)
        wellness = self.client.get_wellness(oldest=oldest, newest=newest)
        fitness = self.client.get_current_fitness()
        sport_settings = self.client.get_sport_settings("Run")
        athlete = self.client.get_athlete()

        return {
            "meta": {
                "athlete_name": f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                "generated_at": datetime.now().isoformat(),
                "analysis_period_days": days_back,
                "date_range": f"{oldest} → {newest}",
            },
            "fitness": fitness,
            "sport_zones": sport_settings,
            "activities": activities,
            "wellness": wellness,
            "stats": self._calculate_stats(activities, wellness),
        }

    def _calculate_stats(self, activities: list, wellness: list) -> dict:
        """Calculate aggregate statistics."""
        runs = [a for a in activities if a.get("type") == "Run"]

        if not runs:
            return {"error": "No running activities found"}

        # Basic stats
        total_distance = sum(a.get("distance", 0) for a in runs) / 1000
        total_time_h = sum(a.get("moving_time", 0) for a in runs) / 3600
        total_runs = len(runs)

        # Weekly breakdown
        weekly_data = self._weekly_breakdown(runs)

        # Pace trend
        pace_trend = self._pace_trend(runs)

        # HR zone distribution
        hr_zone_data = self._hr_zone_analysis(runs)

        # Training load analysis
        load_analysis = self._training_load_analysis(runs, wellness)

        # Best efforts
        from race_predictor import RacePredictor
        predictor = RacePredictor(self.client)
        bests = predictor.predict_benchmark()

        return {
            "total_distance_km": round(total_distance, 1),
            "total_time_h": round(total_time_h, 1),
            "total_runs": total_runs,
            "avg_distance_km": round(total_distance / total_runs, 1) if total_runs else 0,
            "avg_pace": self._avg_pace(runs),
            "weekly_breakdown": weekly_data,
            "pace_trend": pace_trend,
            "hr_zone_distribution": hr_zone_data,
            "training_load": load_analysis,
            "race_predictions": bests.get("benchmarks", {}),
        }

    def _weekly_breakdown(self, runs: list) -> list:
        """Calculate weekly mileage and time."""
        weeks = defaultdict(lambda: {"km": 0, "time_s": 0, "runs": 0,
                                      "avg_pace": None, "elevation_gain": 0})

        for r in runs:
            date_str = r.get("start_date_local", "")
            if not date_str:
                continue
            date = datetime.fromisoformat(date_str)
            week_key = date.strftime("%Y-W%U")

            weeks[week_key]["km"] += r.get("distance", 0) / 1000
            weeks[week_key]["time_s"] += r.get("moving_time", 0)
            weeks[week_key]["runs"] += 1
            weeks[week_key]["elevation_gain"] += r.get("total_elevation_gain", 0) or 0

        result = []
        for week_key in sorted(weeks.keys()):
            w = weeks[week_key]
            km = w["km"]
            time_s = w["time_s"]
            w["avg_pace"] = format_pace(time_s / (km * 1000)) if km > 0 else "N/A"
            w["km"] = round(km, 1)
            w["week"] = week_key
            result.append(w)

        return result

    def _pace_trend(self, runs: list) -> list:
        """Calculate pace trend over time (average pace per run)."""
        trend = []
        for r in sorted(runs, key=lambda x: x.get("start_date_local", "")):
            dist = r.get("distance", 0)
            time_s = r.get("moving_time", 0)
            if dist > 0 and time_s > 0:
                pace = time_s / (dist / 1000)  # seconds per km
                trend.append({
                    "date": r.get("start_date_local", "")[:10],
                    "distance_km": round(dist / 1000, 1),
                    "pace_sec_per_km": round(pace),
                    "pace_str": format_pace(pace),
                    "name": r.get("name", ""),
                })

        return trend[-30:]  # last 30 runs

    def _hr_zone_analysis(self, runs: list) -> dict:
        """Analyze time spent in HR zones."""
        zone_times = {f"Zone {i+1}": 0 for i in range(5)}
        total_hr_time = 0

        for r in runs:
            hr_zones = r.get("icu_hr_zone_times")
            if hr_zones:
                # hr_zone_times is an array of seconds per zone
                for i, seconds in enumerate(hr_zones):
                    if i < 5 and seconds:
                        zone_times[f"Zone {i+1}"] += seconds
                        total_hr_time += seconds

        if total_hr_time > 0:
            return {
                "zones": [
                    {"zone": "Zone 1 (Recovery)", "seconds": zone_times["Zone 1"],
                     "pct": round(zone_times["Zone 1"] / total_hr_time * 100)},
                    {"zone": "Zone 2 (Aerobic)", "seconds": zone_times["Zone 2"],
                     "pct": round(zone_times["Zone 2"] / total_hr_time * 100)},
                    {"zone": "Zone 3 (Tempo)", "seconds": zone_times["Zone 3"],
                     "pct": round(zone_times["Zone 3"] / total_hr_time * 100)},
                    {"zone": "Zone 4 (Threshold)", "seconds": zone_times["Zone 4"],
                     "pct": round(zone_times["Zone 4"] / total_hr_time * 100)},
                    {"zone": "Zone 5 (VO2max)", "seconds": zone_times["Zone 5"],
                     "pct": round(zone_times["Zone 5"] / total_hr_time * 100)},
                ],
                "total_h": round(total_hr_time / 3600, 1),
            }
        return {"zones": [], "total_h": 0, "note": "No HR zone data available"}

    def _training_load_analysis(self, runs: list, wellness: list) -> dict:
        """Analyze training load composition."""
        total_load = sum(r.get("icu_training_load", 0) or 0 for r in runs)

        # Classifies by distance to guess workout type
        easy_load = 0
        quality_load = 0
        long_run_load = 0

        distances = [
            r.get("distance", 0) for r in runs if r.get("distance", 0) and r.get("distance", 0) > 1000
        ]
        if distances:
            avg_km = sum(distances) / len(distances) / 1000

            for r in runs:
                dist = r.get("distance", 0)
                load = r.get("icu_training_load", 0) or 0
                if not dist or dist <= 0:
                    continue
                dist_km = dist / 1000

                if dist_km > avg_km * 2:
                    long_run_load += load
                elif dist_km > avg_km * 1.3:
                    quality_load += load
                else:
                    easy_load += load

        return {
            "total_load": total_load,
            "avg_load_per_run": round(total_load / max(1, len(runs))),
            "composition": {
                "easy": easy_load,
                "quality": quality_load,
                "long_run": long_run_load,
            },
        }

    def _avg_pace(self, runs: list) -> str:
        total_time = sum(a.get("moving_time", 0) for a in runs)
        total_dist = sum(a.get("distance", 0) for a in runs)
        if total_dist > 0:
            return format_pace(total_time / (total_dist / 1000))
        return "N/A"

    # ── HTML Report Generation ──────────────────────────────

    def generate_html(self, data: dict, output_path: str = None) -> str:
        """Generate interactive HTML report with Chart.js."""
        meta = data.get("meta", {})
        stats = data.get("stats", {})
        fitness = data.get("fitness", {})
        wellness_list = data.get("wellness", [])

        # Prepare chart data
        ctl_data, atl_data, tsb_data, dates = self._prepare_fitness_data(wellness_list)
        weekly_labels, weekly_km = self._prepare_weekly_data(stats)
        race_preds = stats.get("race_predictions", {})

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🏃 跑步训练分析报告 | {meta.get('athlete_name', 'Runner')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: #f5f7fa; color: #2d3748; line-height: 1.6;
}}
.container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
.header {{
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white; padding: 32px 24px; border-radius: 16px; margin-bottom: 24px;
}}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header p {{ opacity: 0.9; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.stat-card {{
  background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
.stat-card .label {{ font-size: 13px; color: #718096; margin-bottom: 4px; }}
.stat-card .value {{ font-size: 28px; font-weight: 700; color: #2d3748; }}
.stat-card .sub {{ font-size: 13px; color: #a0aec0; margin-top: 4px; }}
.chart-card {{
  background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  margin-bottom: 20px;
}}
.chart-card h3 {{ font-size: 16px; margin-bottom: 16px; color: #4a5568; }}
.chart-card canvas {{ width: 100%; max-height: 360px; }}
.prediction-table {{
  width: 100%; border-collapse: collapse; margin-top: 12px;
}}
.prediction-table th, .prediction-table td {{
  padding: 10px 12px; text-align: left; border-bottom: 1px solid #e2e8f0;
}}
.prediction-table th {{ font-size: 12px; color: #718096; text-transform: uppercase; letter-spacing: 0.5px; }}
.prediction-table td {{ font-size: 15px; }}
.highlight {{ color: #667eea; font-weight: 600; }}
.footer {{
  text-align: center; padding: 24px; color: #a0aec0; font-size: 13px;
}}
.summary-text {{
  background: white; border-radius: 12px; padding: 20px 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  margin-bottom: 20px; line-height: 1.8;
}}
.summary-text strong {{ color: #667eea; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>🏃 跑步训练分析报告</h1>
  <p>{meta.get('athlete_name', 'Runner')}  ·  训练周期: {meta.get('date_range', '')}  ·  报告生成: {meta.get('generated_at', '')[:16]} </p>
</div>

<div class="grid">
  <div class="stat-card">
    <div class="label">总跑量</div>
    <div class="value">{stats.get('total_distance_km', 0):.0f} <span style="font-size:16px">km</span></div>
    <div class="sub">{stats.get('total_time_h', 0):.0f} 小时 · {stats.get('total_runs', 0)} 次</div>
  </div>
  <div class="stat-card">
    <div class="label">平均配速</div>
    <div class="value">{stats.get('avg_pace', 'N/A')}</div>
    <div class="sub">平均每次 {stats.get('avg_distance_km', 0):.1f} km</div>
  </div>
  <div class="stat-card">
    <div class="label">CTL 训练体能</div>
    <div class="value">{fitness.get('ctl', 0):.0f}</div>
    <div class="sub">ATL {fitness.get('atl', 0):.0f} · TSB {fitness.get('tsb', 0) or 'N/A'}</div>
  </div>
  <div class="stat-card">
    <div class="label">HRV / 静息心率</div>
    <div class="value">{fitness.get('hrv', 'N/A') or 'N/A'}<span style="font-size:16px">ms</span> <span style="font-size:16px;color:#718096">/ {fitness.get('resting_hr', 'N/A') or 'N/A'}</span></div>
    <div class="sub">当前数值</div>
  </div>
</div>

<div class="chart-card">
  <h3>📈 体能趋势 (CTL / ATL / TSB)</h3>
  <canvas id="fitnessChart"></canvas>
</div>

<div class="chart-card">
  <h3>📊 周跑量统计</h3>
  <canvas id="weeklyChart"></canvas>
</div>

<div class="chart-card">
  <h3>🏁 比赛成绩预测</h3>
  <table class="prediction-table">
    <thead><tr><th>距离</th><th>预测完赛时间</th><th>预测配速</th></tr></thead>
    <tbody>
"""
        for name, pred in race_preds.items():
            html += f"<tr><td>{name.upper()}</td><td class='highlight'>{pred.get('predicted', '-')}</td><td>{pred.get('pace', '-')}</td></tr>\n"

        html += """
    </tbody>
  </table>
</div>

<div class="chart-card">
  <h3>🫀 心率区间分布</h3>
  <canvas id="hrChart"></canvas>
</div>

<div class="chart-card">
  <h3>🏃 配速趋势 (最近30次跑步)</h3>
  <canvas id="paceChart"></canvas>
</div>

<div class="summary-text">
  <h3 style="margin-bottom:12px">📝 训练概要</h3>
"""
        tl = stats.get('training_load', {})
        html += f"""  <p>总训练负荷: <strong>{tl.get('total_load', 0)}</strong> (平均每次 {tl.get('avg_load_per_run', 0)})</p>
  <p>训练构成 — 轻松跑: <strong>{tl.get('composition', {}).get('easy', 0)}</strong> · 质量课: <strong>{tl.get('composition', {}).get('quality', 0)}</strong> · 长距离: <strong>{tl.get('composition', {}).get('long_run', 0)}</strong></p>
"""

        hr_data = stats.get('hr_zone_distribution', {})
        if hr_data.get('total_h', 0) > 0:
            html += f"  <p>心率区间训练时间: {hr_data['total_h']:.1f} 小时</p>\n"

        html += """</div>

<div class="footer">
  由 Running Coach Skill 自动生成 · 数据来源: intervals.icu
</div>
</div>

<script>
// ── Fitness Chart ──
const fitnessCtx = document.getElementById('fitnessChart').getContext('2d');
new Chart(fitnessCtx, {
  type: 'line',
  data: {
    labels: """ + json.dumps(dates) + """,
    datasets: [
      {
        label: 'CTL (长期体能)',
        data: """ + json.dumps(ctl_data) + """,
        borderColor: '#667eea',
        backgroundColor: 'rgba(102,126,234,0.1)',
        fill: false,
        tension: 0.3,
        pointRadius: 0,
      },
      {
        label: 'ATL (短期疲劳)',
        data: """ + json.dumps(atl_data) + """,
        borderColor: '#f56565',
        backgroundColor: 'rgba(245,101,101,0.1)',
        fill: false,
        tension: 0.3,
        pointRadius: 0,
      },
      {
        label: 'TSB (状态)',
        data: """ + json.dumps(tsb_data) + """,
        borderColor: '#48bb78',
        backgroundColor: 'rgba(72,187,120,0.1)',
        fill: false,
        tension: 0.3,
        pointRadius: 0,
        borderDash: [5, 5],
      },
    ]
  },
  options: {
    responsive: true,
    plugins: { legend: { position: 'bottom' } },
    scales: {
      x: { ticks: { maxTicksLimit: 15 } },
      y: { title: { display: true, text: 'TSS/d' } },
    },
  },
});

// ── Weekly Mileage Chart ──
const weeklyCtx = document.getElementById('weeklyChart').getContext('2d');
new Chart(weeklyCtx, {
  type: 'bar',
  data: {
    labels: """ + json.dumps(weekly_labels) + """,
    datasets: [{
      label: '周跑量 (km)',
      data: """ + json.dumps(weekly_km) + """,
      backgroundColor: '#667eea',
      borderRadius: 4,
    }],
  },
  options: {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      y: { title: { display: true, text: 'km' } },
    },
  },
});

// ── HR Zone Chart ──
const hrCtx = document.getElementById('hrChart').getContext('2d');
const hrZones = """ + json.dumps(hr_data.get('zones', [])) + """;
if (hrZones.length > 0) {
  new Chart(hrCtx, {
    type: 'doughnut',
    data: {
      labels: hrZones.map(z => z.zone),
      datasets: [{
        data: hrZones.map(z => z.pct),
        backgroundColor: ['#48bb78', '#4299e1', '#ecc94b', '#ed8936', '#f56565'],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'right' },
        tooltip: { callbacks: { label: function(c) { return c.label + ': ' + c.raw + '%'; } } },
      },
    },
  });
} else {
  hrCtx.canvas.parentElement.style.display = 'none';
}

// ── Pace Trend Chart ──
const paceCtx = document.getElementById('paceChart').getContext('2d');
const paceData = """ + json.dumps(stats.get('pace_trend', [])) + """;
if (paceData.length > 0) {
  new Chart(paceCtx, {
    type: 'scatter',
    data: {
      datasets: [{
        label: '配速 (秒/公里)',
        data: paceData.map(p => ({ x: p.date, y: p.pace_sec_per_km })),
        borderColor: '#ed8936',
        backgroundColor: 'rgba(237,137,54,0.6)',
        pointRadius: 4,
        showLine: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          callbacks: {
            label: function(c) {
              const d = paceData[c.dataIndex];
              const m = Math.floor(c.raw.y / 60);
              const s = Math.floor(c.raw.y % 60);
              return d.name + ': ' + m + ':' + String(s).padStart(2,'0') + '/km (' + d.distance_km + 'km)';
            }
          }
        },
        legend: { display: false },
      },
      scales: {
        x: { type: 'category', ticks: { maxTicksLimit: 12 }, title: { display: true, text: '日期' } },
        y: {
          reverse: true,
          title: { display: true, text: '秒/公里 (越低越快)' },
          ticks: {
            callback: function(v) {
              const m = Math.floor(v / 60);
              const s = Math.floor(v % 60);
              return m + ':' + String(s).padStart(2,'0');
            }
          }
        },
      },
    },
  });
}
</script>
</body>
</html>"""
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)

        return html

    def _prepare_fitness_data(self, wellness_list: list):
        """Extract CTL/ATL/TSB arrays for charting."""
        sorted_data = sorted(wellness_list, key=lambda x: x.get("id", ""))
        dates = [w.get("id", "") for w in sorted_data]
        ctl = [w.get("ctl") for w in sorted_data]
        atl = [w.get("atl") for w in sorted_data]
        tsb = [(w.get("ctl", 0) or 0) - (w.get("atl", 0) or 0)
               if w.get("ctl") and w.get("atl") else None for w in sorted_data]
        return ctl, atl, tsb, dates

    def _prepare_weekly_data(self, stats: dict):
        weekly = stats.get("weekly_breakdown", [])
        labels = [w.get("week", "") for w in weekly]
        km = [w.get("km", 0) for w in weekly]
        return labels, km


# ── CLI ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Training Analysis Report")
    parser.add_argument("--output", default=None, help="Output HTML file path")
    parser.add_argument("--days", type=int, default=90,
                        help="Analysis period in days (default: 90)")
    parser.add_argument("--json", action="store_true", help="Output JSON data instead of HTML")
    args = parser.parse_args()

    client = IntervalsClient()
    reporter = AnalysisReport(client)

    try:
        data = reporter.analyze(days_back=args.days)

        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            output_path = args.output
            if not output_path:
                output_dir = os.path.expanduser("~/.running_coach/reports")
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(
                    output_dir,
                    f"running_report_{datetime.now().strftime('%Y%m%d')}.html"
                )

            reporter.generate_html(data, output_path)
            print(json.dumps({
                "status": "ok",
                "file": output_path,
                "message": f"Report saved to: {output_path}"
            }))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
