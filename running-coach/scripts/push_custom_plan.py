"""
Push custom half-marathon training plan (target 1:35) to intervals.icu.
Weather-adapted for Dongguan summer (hot, humid, frequent thunderstorms).
"""
import sys, os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervals_client import IntervalsClient

client = IntervalsClient()

# ── Helper ──────────────────────────────────────────────────
def ev(name, dt, desc="", load=None):
    """Create an event dict."""
    e = {
        "name": name,
        "start_date_local": dt.isoformat() + "T06:00:00",
        "category": "WORKOUT",
        "type": "Run" if "力量" not in name and "休息" not in name and "拉伸" not in name else "Other",
    }
    if desc:
        e["description"] = desc
    if load:
        e["icu_training_load"] = load
    return e

def rest(dt):
    return ev("🟢 休息日", dt, "泡沫轴放松 + 拉伸 20min。让身体吸收训练。")

def strength(dt):
    return ev("💪 力量训练", dt,
        "核心+下肢力量（在家/健身房）:\n"
        "深蹲 3x15, 弓步走 3x12/side, 臀桥 3x20, 单腿硬拉 3x10/side\n"
        "平板支撑 3x45s, 侧平板 3x30s/side, 死虫式 3x20\n"
        "弹力带髋外展 3x15/side, 弹力带侧走 3x20步/side",
        load=15)

def easy(km, dt, note=""):
    desc = f"轻松跑 {km}km @ 5:20-5:50/km，心率 ≤153（Zone 2）。\n"
    desc += "🏖️ 夏天注意：用心率控强度，配速慢10-20s正常。"
    if note:
        desc += f"\n📌 {note}"
    return ev(f"🔵 轻松跑 {km}K", dt, desc, load=int(km * 4))

def long(km, dt, note=""):
    desc = f"长距离 {km}km @ 5:20-5:40/km，心率 Zone 2（≤153）。\n"
    desc += "🏖️ 早起跑，避开高温。带水或规划补水点。"
    if note:
        desc += f"\n📌 {note}"
    return ev(f"🟣 长距离 {km}K", dt, desc, load=int(km * 5))

def intervals_workout(dt, reps, dist, pace, rest_m, note=""):
    total = reps * dist / 1000 + reps * rest_m / 1000 + 4  # warmup + cooldown
    desc = (f"热身 2km 轻松跑 → {reps}×{dist}m @ {pace}/km"
            f"（组间慢跑 {rest_m}m 恢复）→ 冷身 2km。\n"
            f"目标心率 Zone 4-5a（171-181）。\n"
            f"🏖️ 建议跑步机执行，精准控速，不受天气影响。")
    if note:
        desc += f"\n📌 {note}"
    return ev(f"🔴 间歇 {reps}×{dist}m", dt, desc, load=int(total * 7))

def threshold_workout(dt, reps, dist_km, pace, note=""):
    total = reps * dist_km + 4
    desc = (f"热身 2km 轻松跑 → {reps}×{dist_km}km @ {pace}/km 阈值跑"
            f"（组间慢跑 3min 恢复）→ 冷身 2km。\n"
            f"目标心率 Zone 4（171-176），体感「舒适地吃力」。\n"
            f"🏖️ 建议跑步机或清晨凉爽时执行。")
    if note:
        desc += f"\n📌 {note}"
    return ev(f"🟠 阈值 {reps}×{dist_km}K", dt, desc, load=int(total * 7))

def race_pace(dt, reps, dist_km, pace, note=""):
    total = reps * dist_km + 4
    desc = (f"热身 2km → {reps}×{dist_km}km @ {pace}/km 比赛配速"
            f"（组间慢跑 3min 恢复）→ 冷身 2km。\n"
            f"🎯 这就是 1:35 半马的目标配速！让身体记住这个节奏。")
    if note:
        desc += f"\n📌 {note}"
    return ev(f"🎯 比赛配速 {reps}×{dist_km}K", dt, desc, load=int(total * 7))

def strides_note():
    return "跑后加 6×100m strides（渐加速到85%最大速度），走回起点恢复。"

# ── Plan Definition ─────────────────────────────────────────
# Week structure: Mon=Rest, Tue=Easy, Wed=Quality/Strength,
#                 Thu=Easy, Fri=Strength/Rest, Sat=Easy, Sun=Long
events = []
start = date(2026, 7, 29)

def wd(week_start, day_offset):
    """Return date for a given week's day (Mon=0 ... Sun=6)."""
    return week_start + timedelta(days=day_offset)

# ============================================================
# WEATHER WEEK: Jul 29 - Aug 3 (rain adaptation)
# ============================================================
ws = start  # Jul 29 is Wednesday
events.append(ev("💪 力量训练（雷暴天室内）", wd(ws, 0),
    "核心+下肢：深蹲 3x15, 弓步走 3x12/side, 臀桥 3x20, 平板支撑 3x45s, "
    "弹力带髋外展 3x15/side\n"
    "🌧️ 雷暴天，安全第一，室内训练。",
    load=15))
events.append(ev("🔴 跑步机间歇 6×800m", wd(ws, 1),
    "热身 2km → 6×800m @ 4:05/km（组间慢跑 400m）→ 冷身 1.5km。总计约 10km。\n"
    "目标心率 Zone 4-5a（171-181）。\n"
    "🌧️ 健身房跑步机，雷暴天精准训练不受影响。",
    load=70))
events.append(easy(8, wd(ws, 2), "看雷达图，趁雨停窗口出去。雷暴就改跑步机。心率 ≤153。"))
events.append(strength(wd(ws, 3)))
events.append(ev("🟣 长距离 14-16K（跑步机/见缝插针）", wd(ws, 4),
    "14-16km @ 5:20-5:40/km，心率 Zone 2（≤153）。\n"
    "🌧️ 户外不行就跑步机。太枯燥就拆成 2×8km（上午+下午）。",
    load=75))
events.append(rest(wd(ws, 5)))

# ============================================================
# PHASE 1: BASE (W1-W4) — Aug 4 - Aug 31
# ============================================================
# W1: Aug 4-10 (~50km) — Build consistency
ws = date(2026, 8, 3)  # Monday Aug 3 → adjust to Aug 4
ws = date(2026, 8, 3) + timedelta(days=1)  # Actually Aug 4 is Monday

ws = date(2026, 8, 3)  # This is Monday? 
# Aug 3 2026 is Monday. Let me use proper dates.

# W1: Aug 3 (Mon) - Aug 9 (Sun)
ws = date(2026, 8, 3)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1), strides_note()))
events.append(strength(wd(ws, 2)))
events.append(easy(10, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(16, wd(ws, 6)))

# W2: Aug 10-16 (~52km)
ws = date(2026, 8, 10)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1), strides_note()))
events.append(strength(wd(ws, 2)))
events.append(easy(10, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(18, wd(ws, 6)))

# W3: Aug 17-23 (~56km)
ws = date(2026, 8, 17)
events.append(rest(wd(ws, 0)))
events.append(easy(10, wd(ws, 1), strides_note()))
events.append(strength(wd(ws, 2)))
events.append(easy(10, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(20, wd(ws, 6)))

# W4: Aug 24-30 (~50km, recovery week)
ws = date(2026, 8, 24)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1)))
events.append(strength(wd(ws, 2)))
events.append(easy(10, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(16, wd(ws, 6)))

# ============================================================
# PHASE 2: BUILD (W5-W8) — Sep 1 - Sep 28
# ============================================================
# W5: Sep 1-7 (~56km)
ws = date(2026, 8, 31)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1)))
events.append(threshold_workout(wd(ws, 2), 3, 2, "4:15", "阈值入门，稳住配速即可。"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(20, wd(ws, 6)))

# W6: Sep 7-13 (~58km)
ws = date(2026, 9, 7)
events.append(rest(wd(ws, 0)))
events.append(easy(10, wd(ws, 1)))
events.append(threshold_workout(wd(ws, 2), 4, 1.5, "4:10", "阈值提速，间歇更短更快。"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(22, wd(ws, 6), "后 5km 加速到 4:45/km。模拟比赛后半程。"))

# W7: Sep 14-20 (~60km)
ws = date(2026, 9, 14)
events.append(rest(wd(ws, 0)))
events.append(easy(10, wd(ws, 1)))
events.append(threshold_workout(wd(ws, 2), 2, 3, "4:15", "长段阈值，练耐乳酸能力。"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(24, wd(ws, 6)))

# W8: Sep 21-27 (~48km, recovery week)
ws = date(2026, 9, 21)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1)))
events.append(strength(wd(ws, 2)))
events.append(easy(10, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(18, wd(ws, 6)))

# ============================================================
# PHASE 3: PEAK (W9-W11) — Sep 28 - Oct 18
# ============================================================
# W9: Sep 28 - Oct 4 (~58km)
ws = date(2026, 9, 28)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1)))
events.append(intervals_workout(wd(ws, 2), 5, 1000, "3:55", 400, "VO2max 刺激！"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(22, wd(ws, 6), "中间 10km @ 4:30/km 比赛配速段！核心课！"))

# W10: Oct 5-11 (~62km)
ws = date(2026, 10, 5)
events.append(rest(wd(ws, 0)))
events.append(easy(10, wd(ws, 1)))
events.append(race_pace(wd(ws, 2), 3, 3, "4:30", "比赛配速专项！"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(8, wd(ws, 5)))
events.append(long(25, wd(ws, 6), "最长距离！配速 5:20-5:40，稳住心率。"))

# W11: Oct 12-18 (~56km)
ws = date(2026, 10, 12)
events.append(rest(wd(ws, 0)))
events.append(easy(8, wd(ws, 1)))
events.append(race_pace(wd(ws, 2), 2, 5, "4:30", "比赛配速长段，信心课！"))
events.append(easy(10, wd(ws, 3)))
events.append(strength(wd(ws, 4)))
events.append(easy(6, wd(ws, 5)))
events.append(long(20, wd(ws, 6), "后 8km @ 4:30/km。最后一次比赛配速长距离。"))

# ============================================================
# PHASE 4: TAPER (W12) — Oct 19-25
# ============================================================
ws = date(2026, 10, 19)
events.append(rest(wd(ws, 0)))
events.append(easy(6, wd(ws, 1), "加 4×100m strides。保持腿部速度感。"))
events.append(threshold_workout(wd(ws, 2), 2, 1.5, "4:15", "减量不减强度。"))
events.append(easy(6, wd(ws, 3)))
events.append(rest(wd(ws, 4)))
events.append(easy(4, wd(ws, 5), "加 3×100m strides。轻松，找节奏。"))
events.append(ev("🏁 比赛日！", date(2026, 11, 1),
    "🎯 目标：1:35:00（配速 4:30/km）\n\n"
    "策略：前 5km @ 4:35 稳住 → 5-15km @ 4:30 巡航 → "
    "15-21km @ 4:25 加速完结。\n\n"
    "补给：赛前 30min 能量胶1根，10km 第2根，15km 第3根。\n"
    "每 5km 补水站必喝水。\n\n"
    "💪 你准备好了！12周的汗水和雷暴天的坚持，都为了这一天！",
    load=120))

# ============================================================
# RACE DAY mark (Nov 1)
# ============================================================

# ── Push ────────────────────────────────────────────────────
print(f"准备推送 {len(events)} 个训练事件...")
print(f"日期范围: {events[0]['start_date_local']} → {events[-1]['start_date_local']}")

# First delete existing events in the range
oldest = events[0]["start_date_local"]
newest = events[-1]["start_date_local"]
try:
    deleted = client.delete_events_in_range(oldest, newest)
    print(f"清理了 {deleted} 个旧事件")
except Exception as e:
    print(f"清理旧事件时出现问题（可能没有旧事件）: {e}")

# Push in batches of 50
batch_size = 50
total_pushed = 0
for i in range(0, len(events), batch_size):
    batch = events[i:i+batch_size]
    try:
        resp = client.push_events(batch, upsert=True)
        total_pushed += len(batch)
        print(f"  批次 {i//batch_size + 1}: 推送 {len(batch)} 个 ✓")
    except Exception as e:
        print(f"  批次 {i//batch_size + 1}: 失败 - {e}")

print(f"\n✅ 完成！共推送 {total_pushed} 个训练事件到 intervals.icu")
print("打开 https://intervals.icu/calendar 查看课表")
