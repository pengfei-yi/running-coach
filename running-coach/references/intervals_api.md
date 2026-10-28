# Intervals.icu API Reference

## Auth

Personal API Key from `intervals.icu/settings` (bottom of page).

Authentication header: `Authorization: Basic <base64("API_KEY:<api_key>")>`

Athlete ID: use `0` for authenticated user's own data.

Base URL: `https://intervals.icu/api/v1`

Rate limit: ~0.5s delay between requests recommended.

## Key Endpoints

### Activities (completed workouts)

```
GET /athlete/{id}/activities?oldest=YYYY-MM-DD&newest=YYYY-MM-DD&fields=...
```

Key activity fields:
- `id`, `name`, `type` (Run/Ride/Swim), `start_date_local`
- `distance` (meters), `moving_time` (seconds)
- `average_speed` (m/s), `average_heartrate` (bpm), `max_heartrate`
- `icu_training_load` (TSS equivalent)
- `icu_ctl`, `icu_atl` (fitness/fatigue at time of activity)
- `icu_hr_zone_times` (array of seconds per HR zone)
- `total_elevation_gain`, `calories`, `average_temp`
- `perceived_exertion`, `feel`

### Wellness (daily CTL/ATL/HRV)

```
GET /athlete/{id}/wellness?oldest=YYYY-MM-DD&newest=YYYY-MM-DD
```

Wellness fields:
- `id` (date YYYY-MM-DD)
- `ctl` (Chronic Training Load — 42-day exponentially weighted TSS/d)
- `atl` (Acute Training Load — 7-day exponentially weighted TSS/d)
- `rampRate` (CTL ramp rate)
- `restingHR`, `hrv`
- `sleepTime` (seconds), `sleepScore`
- `weight` (kg)
- `fatigue`, `soreness`, `stress`, `mood`, `motivation` (subjective 1-5)

TSB (Training Stress Balance / Form) = CTL - ATL
- TSB > 0: rested/recovered
- TSB < -10: accumulating fatigue
- TSB < -30: overreaching / risk of overtraining

### Sport Settings

```
GET /athlete/{id}/sport-settings/{sport}
```

Returns:
- `ftp` / `lthr` (threshold values)
- `power_zones` (7 values: 6 zone boundaries)
- `hr_zones` (same structure)

### Events (calendar / planned workouts)

```
GET /athlete/{id}/events?oldest=...&newest=...&category=WORKOUT
POST /athlete/{id}/events/bulk?upsertOnUid=true
```

Event fields:
- `name`, `category` (WORKOUT/NOTE/TARGET), `start_date_local`
- `description` (plain text or MRC workout format)
- `type` (Run/Ride/Swim)
- `icu_training_load` (estimated TSS)

### Activity Streams

```
GET /activity/{ACTIVITY_ID}/streams?types=watts,heartrate,cadence
```

Available stream types: `time`, `watts`, `heartrate`, `cadence`, `distance`, `altitude`, `latlng`, `velocity_smooth`, `temp`
