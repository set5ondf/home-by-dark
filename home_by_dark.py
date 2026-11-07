#!/usr/bin/env python3
"""
HomeByDark -- plan a bike ride backwards from a hard curfew.

The problem: in winter the sun sets early, and some of us have a hard rule
about when we have to be home (5:15 PM, no arguments, lights do not count).
Every ride planner works forwards ("leave at 4, ride 15 miles, get home
whenever"). This one works backwards: give it the ride and your curfew and
it tells you the latest you can roll out, plus when the sun actually sets,
computed from scratch with the NOAA solar equations. No API, no internet,
no dependencies beyond the Python standard library.

Ride time model (deliberately a little conservative, because a curfew tool
should be):
    flat time  = distance / average speed
    climb time = 1 extra minute per 100 ft of climbing (tunable)
    plus       = your stop time (coffee, photos, KOM attempts)

Usage:
    python3 home_by_dark.py --distance 15 --gain 1150
    python3 home_by_dark.py --distance 15 --gain 1150 --leave 16:10
    python3 home_by_dark.py --distance 22 --gain 1600 --week
    python3 home_by_dark.py --distance 30 --curfew 18:30 --speed 16 --stops 10

Or hand it a GPX file (Strava / Garmin export) and skip the typing:
    python3 home_by_dark.py --gpx my_ride.gpx
Distance, climbing, the date, and even your actual start time are read
from the file, so running it on a past ride gives a verdict on the ride
you really did. --distance / --gain / --date / --leave still override
whatever the file says.
"""

import argparse
import math
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Berkeley, CA. Change with --lat / --lon / --tz for anywhere else.
DEFAULT_LAT = 37.8715
DEFAULT_LON = -122.2730
DEFAULT_TZ = "America/Los_Angeles"
DEFAULT_CURFEW = "17:15"


def sunset_utc_minutes(day: date, lat: float, lon: float) -> float:
    """Minutes after 00:00 UTC when the sun sets, per the NOAA solar calc."""
    n = day.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1 + 0.5)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    lat_r = math.radians(lat)
    cos_ha = math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl)) - (
        math.tan(lat_r) * math.tan(decl)
    )
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha_deg = math.degrees(math.acos(cos_ha))
    # Sunset: the sun reaches the hour angle on the evening side.
    return 720 - 4 * (lon - ha_deg) - eqtime


def sunset_local(day: date, lat: float, lon: float, tz: ZoneInfo) -> datetime:
    mins = sunset_utc_minutes(day, lat, lon)
    utc_dt = datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(
        minutes=mins
    )
    return utc_dt.astimezone(tz)


def ride_minutes(distance_mi, gain_ft, speed_mph, climb_min_per_100ft, stops_min):
    flat = distance_mi / speed_mph * 60
    climb = gain_ft / 100 * climb_min_per_100ft
    return flat + climb + stops_min


def haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.8  # Earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_gpx(path, tz):
    """Read distance (mi), elevation gain (ft) and start time from a GPX file.

    Gain is summed from a 5-point moving average of the elevation track so
    GPS noise does not inflate it. Returns a dict; start may be None if the
    file has no timestamps.
    """
    root = ET.parse(path).getroot()
    pts = []  # (lat, lon, ele_m, time)
    for el in root.iter():
        if local_name(el.tag) != "trkpt":
            continue
        lat, lon = float(el.get("lat")), float(el.get("lon"))
        ele, tstamp = None, None
        for child in el:
            name = local_name(child.tag)
            if name == "ele":
                ele = float(child.text)
            elif name == "time":
                tstamp = child.text
        pts.append((lat, lon, ele, tstamp))
    if len(pts) < 2:
        raise SystemExit(f"GPX file has fewer than 2 track points: {path}")

    distance = sum(
        haversine_mi(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])
    )

    eles = [p[2] for p in pts if p[2] is not None]
    gain_ft = 0.0
    if len(eles) >= 2:
        win = 5
        smooth = [
            sum(eles[max(0, i - win // 2): i + win // 2 + 1])
            / len(eles[max(0, i - win // 2): i + win // 2 + 1])
            for i in range(len(eles))
        ]
        gain_m = sum(max(0.0, b - a) for a, b in zip(smooth, smooth[1:]))
        gain_ft = gain_m * 3.28084

    start = None
    for p in pts:
        if p[3]:
            start = datetime.fromisoformat(p[3].replace("Z", "+00:00")).astimezone(tz)
            break
    return {"distance_mi": distance, "gain_ft": gain_ft, "start": start}


def parse_hhmm(text):
    hh, mm = text.split(":")
    return time(int(hh), int(mm))


def fmt(dt):
    return dt.strftime("%-I:%M %p")


def fmt_duration(minutes):
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def plan_for_day(day, args, tz):
    curfew = datetime.combine(day, parse_hhmm(args.curfew), tzinfo=tz)
    sunset = sunset_local(day, args.lat, args.lon, tz)
    dur = ride_minutes(
        args.distance, args.gain, args.speed, args.climb_rate, args.stops
    )
    latest_start = curfew - timedelta(minutes=dur)
    return curfew, sunset, dur, latest_start


def main():
    p = argparse.ArgumentParser(
        description="Work out the latest you can start a ride and still be home by curfew."
    )
    p.add_argument("--distance", type=float, default=None, help="Ride distance in miles (or use --gpx)")
    p.add_argument("--gain", type=float, default=None, help="Elevation gain in feet (or use --gpx)")
    p.add_argument("--gpx", default=None, help="GPX file to read distance, gain, date and start time from")
    p.add_argument("--speed", type=float, default=15.0, help="Average flat speed in mph (default 15)")
    p.add_argument("--climb-rate", type=float, default=1.0, help="Extra minutes per 100 ft of climbing (default 1.0)")
    p.add_argument("--stops", type=float, default=0, help="Minutes of stopped time (default 0)")
    p.add_argument("--curfew", default=DEFAULT_CURFEW, help="Hard home-by time, HH:MM 24h (default 17:15)")
    p.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    p.add_argument("--leave", default=None, help="Planned start HH:MM, to get a verdict on it")
    p.add_argument("--week", action="store_true", help="Show the next 7 days as a table")
    p.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p.add_argument("--lon", type=float, default=DEFAULT_LON)
    p.add_argument("--tz", default=DEFAULT_TZ)
    args = p.parse_args()

    tz = ZoneInfo(args.tz)

    gpx_info = None
    if args.gpx:
        gpx_info = parse_gpx(args.gpx, tz)
        if args.distance is None:
            args.distance = gpx_info["distance_mi"]
        if args.gain is None:
            args.gain = gpx_info["gain_ft"]
        if args.date is None and gpx_info["start"] is not None:
            args.date = gpx_info["start"].strftime("%Y-%m-%d")
        if args.leave is None and gpx_info["start"] is not None:
            args.leave = gpx_info["start"].strftime("%H:%M")
    if args.distance is None:
        p.error("give a --distance, or a --gpx file to read it from")
    if args.gain is None:
        args.gain = 0

    start_day = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now(tz).date()
    )

    if args.week:
        print(f"Ride: {args.distance:.1f} mi, {args.gain:.0f} ft, curfew {args.curfew}")
        print(f"{'Date':<14}{'Sunset':<10}{'Latest start':<14}Ride time")
        for i in range(7):
            day = start_day + timedelta(days=i)
            _, sunset, dur, latest = plan_for_day(day, args, tz)
            print(
                f"{day.strftime('%a %b %-d'):<14}{fmt(sunset):<10}"
                f"{fmt(latest):<14}{fmt_duration(dur)}"
            )
        return

    curfew, sunset, dur, latest = plan_for_day(start_day, args, tz)
    if gpx_info is not None:
        gpx_line = (
            f"From GPX:    {gpx_info['distance_mi']:.2f} mi, "
            f"{gpx_info['gain_ft']:.0f} ft gain"
        )
        if gpx_info["start"] is not None:
            gpx_line += f", started {fmt(gpx_info['start'])}"
        print(gpx_line)
    print(f"Ride:        {args.distance:.1f} mi, {args.gain:.0f} ft climbing")
    print(f"Ride time:   ~{fmt_duration(dur)} (est, slightly conservative)")
    print(f"Sunset:      {fmt(sunset)} on {start_day.strftime('%a %b %-d')}")
    print(f"Curfew:      {fmt(curfew)}")
    print(f"Latest start: {fmt(latest)}")

    if args.leave:
        leave = datetime.combine(start_day, parse_hhmm(args.leave), tzinfo=tz)
        home = leave + timedelta(minutes=dur)
        margin = (curfew - home).total_seconds() / 60
        dark_by = (home - sunset).total_seconds() / 60
        print()
        print(f"If you leave at {fmt(leave)}: home about {fmt(home)}")
        if margin >= 0:
            print(f"Verdict: OK, {int(margin)} min to spare before curfew.")
        else:
            print(f"Verdict: TOO LATE. That puts you home {int(-margin)} min after curfew.")
        if dark_by > 0:
            print(f"You finish {int(dark_by)} min after sunset. Lights on, no detours.")
        else:
            print(f"You beat sunset by {int(-dark_by)} min.")


if __name__ == "__main__":
    main()
