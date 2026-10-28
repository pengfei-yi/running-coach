#!/usr/bin/env python3
"""
Segment-by-segment analysis for a single activity.
Breaks the run into 1km segments and reports pace, cadence, stride length, HR.
"""
import json, sys
sys.path.insert(0, '.')
from intervals_client import IntervalsClient


def analyze_activity(activity_id: str):
    client = IntervalsClient()

    # Fetch stream data
    streams = client._request(
        f'/activity/{activity_id}/streams?types=time,cadence,heartrate,velocity_smooth,distance'
    )

    # Parse streams into dict by type
    stream_data = {}
    for s in streams:
        stream_data[s['type']] = s['data']

    times = stream_data.get('time', [])
    cadences = stream_data.get('cadence', [])
    hrs = stream_data.get('heartrate', [])
    velocities = stream_data.get('velocity_smooth', [])
    distances = stream_data.get('distance', [])

    n = len(times)
    print(f"Total data points: {n}")
    print(f"Time range: {times[0]}s - {times[-1]}s ({times[-1]-times[0]}s)")
    print(f"Distance range: {distances[0]:.0f}m - {distances[-1]:.0f}m")
    print()

    # Break into 1km segments
    segment_size = 1000  # meters
    total_distance = distances[-1]
    num_segments = int(total_distance // segment_size)

    print(f"{'='*90}")
    print(f"{'分段':^6} {'距离(m)':^10} {'时间':^8} {'配速':^10} {'步频(spm)':^10} {'步幅(cm)':^10} {'平均心率':^8} {'最大心率':^8}")
    print(f"{'='*90}")

    all_segments = []
    seg_start_idx = 0
    for seg in range(num_segments):
        target_dist = (seg + 1) * segment_size

        # Find the index where distance crosses target_dist
        seg_end_idx = seg_start_idx
        for j in range(seg_start_idx, n):
            if distances[j] is not None and distances[j] >= target_dist:
                seg_end_idx = j
                break
        else:
            seg_end_idx = n - 1

        # Collect stats for this segment
        seg_times = []
        seg_cad = []
        seg_hr = []
        seg_vel = []

        for j in range(seg_start_idx, seg_end_idx + 1):
            t = times[j] if j < n and times[j] is not None else None
            c = cadences[j] if j < n and cadences[j] is not None else None
            h = hrs[j] if j < n and hrs[j] is not None else None
            v = velocities[j] if j < n and velocities[j] is not None else None
            if c is not None: seg_cad.append(c)
            if h is not None: seg_hr.append(h)
            if v is not None: seg_vel.append(v)
        seg_times = times[seg_start_idx:seg_end_idx+1]

        seg_duration = seg_times[-1] - seg_times[0] if seg_times else 0

        # Distance in this segment
        seg_start_dist = distances[seg_start_idx] if distances[seg_start_idx] is not None else seg * segment_size
        seg_end_dist = distances[seg_end_idx] if distances[seg_end_idx] is not None else target_dist
        seg_dist = seg_end_dist - seg_start_dist

        # Pace
        if seg_dist > 0:
            pace_sec_per_km = seg_duration / (seg_dist / 1000)
        else:
            pace_sec_per_km = 9999

        # Cadence (steps per minute)
        avg_cadence = sum(seg_cad) / len(seg_cad) if seg_cad else 0

        # Stride length = speed(m/s) * 60 / cadence(spm) * 100 to get cm
        # speed = distance/time
        if seg_duration > 0 and seg_dist > 0:
            avg_speed_ms = seg_dist / seg_duration
            avg_stride_cm = (avg_speed_ms * 60 / avg_cadence * 100) if avg_cadence > 0 else 0
        else:
            avg_speed_ms = 0
            avg_stride_cm = 0

        # HR
        avg_hr = sum(seg_hr) / len(seg_hr) if seg_hr else 0
        max_hr = max(seg_hr) if seg_hr else 0

        pace_str = f"{int(pace_sec_per_km//60)}:{int(pace_sec_per_km%60):02d}"

        print(f"  {seg+1:^4}  {seg_dist:^8.0f}  {seg_duration:^6.0f}s  {pace_str:^8}  {avg_cadence:^8.0f}  {avg_stride_cm:^8.0f}  {avg_hr:^6.0f}  {max_hr:^6.0f}")

        all_segments.append({
            'seg': seg + 1,
            'dist': seg_dist,
            'duration': seg_duration,
            'pace_str': pace_str,
            'pace_sec': pace_sec_per_km,
            'cadence': avg_cadence,
            'stride_cm': avg_stride_cm,
            'avg_hr': avg_hr,
            'max_hr': max_hr,
        })

        seg_start_idx = seg_end_idx + 1

    # Remaining distance
    remaining_dist = total_distance - num_segments * segment_size
    if remaining_dist > 50:  # more than 50m
        seg_times = times[seg_start_idx:]
        seg_duration = seg_times[-1] - seg_times[0] if len(seg_times) > 1 else 0
        seg_hr = [hrs[j] for j in range(seg_start_idx, n) if hrs[j] is not None]
        seg_cad = [cadences[j] for j in range(seg_start_idx, n) if cadences[j] is not None]

        avg_cadence = sum(seg_cad) / len(seg_cad) if seg_cad else 0
        avg_hr = sum(seg_hr) / len(seg_hr) if seg_hr else 0
        max_hr = max(seg_hr) if seg_hr else 0

        if remaining_dist > 0 and seg_duration > 0:
            pace_sec_per_km = seg_duration / (remaining_dist / 1000)
            avg_speed_ms = remaining_dist / seg_duration
            avg_stride_cm = (avg_speed_ms * 60 / avg_cadence * 100) if avg_cadence > 0 else 0
        else:
            pace_sec_per_km = 0
            avg_stride_cm = 0

        pace_str = f"{int(pace_sec_per_km//60)}:{int(pace_sec_per_km%60):02d}"
        print(f"  尾    {remaining_dist:^8.0f}  {seg_duration:^6.0f}s  {pace_str:^8}  {avg_cadence:^8.0f}  {avg_stride_cm:^8.0f}  {avg_hr:^6.0f}  {max_hr:^6.0f}")

    # Totals
    print(f"{'='*90}")
    total_time = times[-1] - times[0]
    total_pace = total_time / (total_distance / 1000)
    all_cad = [cadences[j] for j in range(n) if cadences[j] is not None]
    all_hr = [hrs[j] for j in range(n) if hrs[j] is not None]
    avg_cad = sum(all_cad) / len(all_cad) if all_cad else 0
    avg_hr = sum(all_hr) / len(all_hr) if all_hr else 0
    max_hr = max(all_hr) if all_hr else 0
    avg_speed = total_distance / total_time
    avg_stride = (avg_speed * 60 / avg_cad * 100) if avg_cad > 0 else 0
    pace_str = f"{int(total_pace//60)}:{int(total_pace%60):02d}"
    print(f"  总计  {total_distance:^8.0f}  {total_time:^6.0f}s  {pace_str:^8}  {avg_cad:^8.0f}  {avg_stride:^8.0f}  {avg_hr:^6.0f}  {max_hr:^6.0f}")
    print()

    # Pace analysis
    print("=" * 70)
    print("📊 配速分析")
    print("=" * 70)
    paces = [s['pace_sec'] for s in all_segments]
    print(f"  最快分段: 第{min(range(len(paces)), key=lambda i: paces[i])+1}km — {all_segments[min(range(len(paces)), key=lambda i: paces[i])]['pace_str']}")
    print(f"  最慢分段: 第{max(range(len(paces)), key=lambda i: paces[i])+1}km — {all_segments[max(range(len(paces)), key=lambda i: paces[i])]['pace_str']}")
    print(f"  配速波动: {min(paces):.0f}s → {max(paces):.0f}s (差值 {max(paces)-min(paces):.0f}s/km)")

    # Negative split check
    first_half_pace = sum(s['pace_sec'] for s in all_segments[:len(all_segments)//2]) / max(len(all_segments)//2, 1)
    second_half_pace = sum(s['pace_sec'] for s in all_segments[len(all_segments)//2:]) / max(len(all_segments) - len(all_segments)//2, 1)
    print(f"  前半程配速: {int(first_half_pace//60)}:{int(first_half_pace%60):02d}")
    print(f"  后半程配速: {int(second_half_pace//60)}:{int(second_half_pace%60):02d}")
    diff = second_half_pace - first_half_pace
    if diff < -5:
        print(f"  🏃 Negative Split! 后半程快 {abs(diff):.0f}s/km")
    elif diff > 5:
        print(f"  ⚠️ Positive Split — 后半程慢了 {diff:.0f}s/km")
    else:
        print(f"  ✅ 匀速跑，前后半程差异仅 {abs(diff):.0f}s/km")

    print()

    # Cadence and stride analysis
    print("=" * 70)
    print("👣 步频 & 步幅分析")
    print("=" * 70)
    cad_vals = [s['cadence'] for s in all_segments]
    strd_vals = [s['stride_cm'] for s in all_segments]
    print(f"  平均步频: {avg_cad:.0f} spm (范围 {min(cad_vals):.0f}-{max(cad_vals):.0f})")
    print(f"  平均步幅: {avg_stride:.0f} cm (范围 {min(strd_vals):.0f}-{max(strd_vals):.0f})")
    # Analysis
    if avg_cad < 165:
        print(f"  ⚠️ 步频偏低(<165)，可能增加触地时间和受伤风险")
    elif avg_cad < 175:
        print(f"  📝 步频中等(165-175)，正常范围")
    else:
        print(f"  ✅ 步频优秀(>175)")

    # Find the surge - check for a segment where pace drops significantly
    # Look for any segment with max HR > 175
    surge_segs = [s for s in all_segments if s['max_hr'] > 170]
    if surge_segs:
        print()
        print("=" * 70)
        print("🔥 冲刺/加速段检测")
        print("=" * 70)
        for s in surge_segs:
            print(f"  第{s['seg']}km: 配速 {s['pace_str']} 心率峰值 {s['max_hr']:.0f}bpm 步频 {s['cadence']:.0f}spm 步幅 {s['stride_cm']:.0f}cm")


if __name__ == '__main__':
    activity_id = sys.argv[1] if len(sys.argv) > 1 else 'i170367534'
    analyze_activity(activity_id)
