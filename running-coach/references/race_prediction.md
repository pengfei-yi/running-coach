# Race Prediction Formulas

## 1. Riegel Formula (Standard)

```
T2 = T1 × (D2/D1)^β
```

- β = 1.06 for distances ≤ marathon
- β = 1.05 for very short (< 3km)
- β = 1.07 for ultra (> marathon)

Reference: Peter Riegel, "Athletics Records and Human Endurance" (1977)

**Confidence**: Good for 5K→10K→half→marathon extrapolation, less accurate for cross-distances (e.g. 400m→marathon).

## 2. Daniels' VDOT / Running Formula

Converts race performance to VDOT (pseudo-VO2max), then predicts other distances.

**Key reference points** (from Daniels' tables):

| VDOT | 5K | 10K | Half | Marathon |
|------|----|-----|------|----------|
| 30 | 28:36 | 59:00 | 2:11:00 | 4:34:00 |
| 35 | 25:02 | 51:42 | 1:54:56 | 3:59:16 |
| 40 | 22:18 | 46:05 | 1:42:05 | 3:32:13 |
| 45 | 20:08 | 41:38 | 1:32:04 | 3:10:47 |
| 50 | 18:22 | 38:01 | 1:23:58 | 2:54:55 |
| 55 | 16:55 | 35:01 | 1:17:13 | 2:41:29 |
| 60 | 15:42 | 32:30 | 1:11:32 | 2:29:59 |
| 65 | 14:39 | 30:21 | 1:06:39 | 2:20:13 |
| 70 | 13:45 | 28:30 | 1:02:24 | 2:11:48 |
| 75 | 12:58 | 26:51 | 0:58:39 | 2:04:21 |
| 80 | 12:16 | 25:24 | 0:55:22 | 1:57:37 |

Reference: Jack Daniels, "Daniels' Running Formula" (4th ed.)

## 3. CTL-Based Adjustment

Chronic Training Load (CTL) indicates fitness level and impacts marathon prediction reliability.

**CTL benchmarks for marathon**:
- CTL < 40: insufficient for confident marathon prediction → add 10-25% penalty
- CTL 40-60: adequate for marathon → add 5-15% penalty
- CTL 60-80: well-prepared → prediction is reliable
- CTL 80+: highly trained → prediction may be conservative

**CTL benchmarks for half marathon**:
- CTL < 30: add 10-20% penalty
- CTL 30-50: add 5-10% penalty
- CTL 50+: well-prepared

**CTL benchmarks for 5K/10K**:
- CTL < 20: low
- CTL 20-40: adequate
- CTL 40+: strong

## 4. TSS-Based Marathon Equivalent

Equivalent finish time = Recent marathon × (TSS_at_race / TSS_at_current_CTL)

This adjusts for the fact that a runner with higher CTL can sustain pace longer.

## When to Use Each Method

1. **Riegel**: Quick, based on recent performances. Best single-point predictor.
2. **Daniels**: Better for comparing across different-level athletes. Good for goal setting.
3. **CTL-adjusted**: Best when CTL doesn't match performance level (e.g. just started training block).
4. **Combined**: Use Riegel as base, adjust with CTL, validate against Daniels' VDOT.
