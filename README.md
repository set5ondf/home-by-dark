# HomeByDark

**Every ride planner works forwards. This one works backwards from your curfew.**

In winter the sun sets early, and some riders have a hard rule about when they have to be home. Mine is 5:15 PM, no arguments, and having good lights does not extend it. So the real question before a ride is never "when do I want to leave," it is "what is the *latest* I can leave and still make it back?"

HomeByDark answers that. Give it a distance, climbing, and your curfew. It computes sunset from scratch (the NOAA solar equations, no API, no internet), estimates your ride time, and tells you the latest possible start, or gives a verdict on a start time you already have in mind.

**New in v2:** hand it a GPX file instead (any Strava or Garmin export) and it reads the distance, climbing, date, and your actual start time out of the file. Run it on a past ride and it grades the ride you really did.

Zero dependencies. Just Python 3.9+.

## Usage

```bash
# The basics: how late can I start this ride?
python3 home_by_dark.py --distance 15 --gain 1150

# Verdict mode: I want to leave at 4:10, am I good?
python3 home_by_dark.py --distance 15 --gain 1150 --leave 16:10

# Planning mode: latest start for this ride, every day this week
python3 home_by_dark.py --distance 22 --gain 1600 --week

# Different curfew, faster rider, coffee stop included
python3 home_by_dark.py --distance 30 --gain 2000 --curfew 18:30 --speed 16 --stops 10

# GPX mode: no typing, it reads the ride from the file
python3 home_by_dark.py --gpx my_ride.gpx

# GPX mode on a past ride: grades your actual start time against the curfew
python3 home_by_dark.py --gpx tuesdays_ride.gpx
```

GPX example output:

```
From GPX:    0.27 mi, 11 ft gain, started 4:37 PM
Ride:        0.3 mi, 11 ft climbing
Ride time:   ~1m (est, slightly conservative)
Sunset:      6:16 PM on Tue Oct 27
Curfew:      5:15 PM
Latest start: 5:13 PM

If you leave at 4:37 PM: home about 4:38 PM
Verdict: OK, 36 min to spare before curfew.
You beat sunset by 98 min.
```

Example output:

```
Ride:        15 mi, 1150 ft climbing
Ride time:   ~1h 12m (est, slightly conservative)
Sunset:      5:08 PM on Wed Nov 4
Curfew:      5:15 PM
Latest start: 4:03 PM

If you leave at 4:10 PM: home about 5:21 PM
Verdict: TOO LATE. That puts you home 6 min after curfew.
You finish 13 min after sunset. Lights on, no detours.
```

(That example is a real ride I cut six minutes too close. The tool would have caught it.)

## How it works

- **Sunset** is computed with the standard NOAA solar calculation: fractional year, equation of time, solar declination, and the sunset hour angle at 90.833 degrees (accounting for atmospheric refraction). Checked against official times for Berkeley, CA: it lands within about a minute.
- **Ride time** is a deliberately slightly conservative model: distance over your average flat speed, plus 1 extra minute per 100 ft of climbing (tunable with `--climb-rate`), plus whatever stop time you admit to.
- **GPX parsing** sums haversine distances between track points, and sums elevation gain from a 5-point moving average of the elevation track so GPS noise does not inflate it. If the file has timestamps, the date and your start time default to the ride's real ones; any flag you pass still wins. Validated against a known route file: computed 22.09 mi against the file's known 22.09 mi.
- **Defaults** are Berkeley, CA (`37.8715, -122.2730`, `America/Los_Angeles`) and a 5:15 PM curfew. Override with `--lat`, `--lon`, `--tz`, and `--curfew` to use it anywhere.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--distance` | from `--gpx` | Ride distance in miles |
| `--gain` | from `--gpx` | Elevation gain in feet |
| `--gpx` | none | GPX file to read distance, gain, date, and start time from |
| `--speed` | 15 | Average flat speed in mph |
| `--climb-rate` | 1.0 | Extra minutes per 100 ft climbed |
| `--stops` | 0 | Minutes of stopped time |
| `--curfew` | 17:15 | Hard home-by time (HH:MM, 24h) |
| `--date` | today | Date, YYYY-MM-DD |
| `--leave` | none | Planned start HH:MM, for a verdict |
| `--week` | off | Table of the next 7 days |
| `--lat` / `--lon` / `--tz` | Berkeley | Location and timezone |

## Why not just check a weather app?

A weather app tells you when the sun sets. It does not know your route, your climbing, your pace, or your curfew, and it will not do the subtraction for you at 3:45 PM when you are deciding whether the long way home is a good idea. This does the whole calculation in one command.

## License

MIT
