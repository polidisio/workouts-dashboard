#!/usr/bin/env python3
"""
Workouts Dashboard Builder v3
- Reads SyncSalud snapshots, computes KPIs, PRs, ACWR, weekday dist, cumulative km
- Generates index.html (links styles.css) + data.json
"""
import json
import glob
import os
from datetime import datetime, timedelta
from collections import defaultdict

VAULT_DIR = "/Users/jmaudisio/Library/Mobile Documents/com~apple~CloudDocs/Vault/snapshots"
OUTPUT_DIR = "/Users/jmaudisio/.openclaw/workspace/workouts-dashboard"
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")
OUTPUT_DATA = os.path.join(OUTPUT_DIR, "data.json")

HR_MAX_CREDIBLE = 220
HR_MIN_CREDIBLE = 40
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_all_workouts():
    workouts = []
    for path in sorted(glob.glob(os.path.join(VAULT_DIR, "*.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
            for w in d.get("workouts", []):
                w["_month"] = d.get("month")
                workouts.append(w)
        except Exception as e:
            print(f"Error reading {path}: {e}")
    return workouts


def compute_stats(workouts):
    valid = [w for w in workouts if w.get("startDate") and w.get("endDate")]
    valid.sort(key=lambda w: w["startDate"])

    hr_credible = [w for w in valid
                   if w.get("avgHeartRate")
                   and HR_MIN_CREDIBLE <= w["avgHeartRate"] <= HR_MAX_CREDIBLE]

    by_type = defaultdict(lambda: {
        "count": 0, "distance": 0, "duration": 0,
        "calories": 0, "hr_sum": 0, "hr_n": 0
    })
    by_month = defaultdict(lambda: {
        "count": 0, "distance": 0, "duration": 0, "calories": 0,
        "types": defaultdict(int)
    })
    by_year = defaultdict(lambda: {"count": 0, "distance": 0, "calories": 0, "duration": 0})
    by_day = defaultdict(int)
    by_day_type = defaultdict(lambda: defaultdict(int))
    weekday_dist = {d: {"count": 0, "distance_km": 0.0} for d in DAYS}

    for w in valid:
        t = w.get("type", "unknown")
        by_type[t]["count"] += 1
        by_type[t]["distance"] += w.get("distance", 0) or 0
        by_type[t]["duration"] += w.get("duration", 0) or 0
        by_type[t]["calories"] += w.get("calories", 0) or 0
        if w.get("avgHeartRate") and HR_MIN_CREDIBLE <= w["avgHeartRate"] <= HR_MAX_CREDIBLE:
            by_type[t]["hr_sum"] += w["avgHeartRate"]
            by_type[t]["hr_n"] += 1

        m = w["startDate"][:7]
        by_month[m]["count"] += 1
        by_month[m]["distance"] += w.get("distance", 0) or 0
        by_month[m]["duration"] += w.get("duration", 0) or 0
        by_month[m]["calories"] += w.get("calories", 0) or 0
        by_month[m]["types"][t] += 1

        y = w["startDate"][:4]
        by_year[y]["count"] += 1
        by_year[y]["distance"] += w.get("distance", 0) or 0
        by_year[y]["calories"] += w.get("calories", 0) or 0
        by_year[y]["duration"] += w.get("duration", 0) or 0

        day_str = w["startDate"][:10]
        by_day[day_str] += 1
        by_day_type[day_str][t] += 1

        try:
            wd = datetime.fromisoformat(day_str).weekday()
            weekday_dist[DAYS[wd]]["count"] += 1
            weekday_dist[DAYS[wd]]["distance_km"] += round((w.get("distance", 0) or 0) / 1000, 3)
        except Exception:
            pass

    by_day_type_out = {d: dict(t) for d, t in by_day_type.items()}

    # HR monthly by type
    hr_by_month_type = defaultdict(lambda: defaultdict(list))
    for w in hr_credible:
        m = w["startDate"][:7]
        hr_by_month_type[m][w.get("type", "unknown")].append(w["avgHeartRate"])
    hr_monthly = {
        m: {t: round(sum(vals) / len(vals), 0) for t, vals in types.items() if vals}
        for m, types in sorted(hr_by_month_type.items())
    }

    # HR distribution by type
    hr_by_type = defaultdict(list)
    for w in hr_credible:
        hr_by_type[w.get("type", "unknown")].append(w["avgHeartRate"])
    hr_dist = {
        t: {
            "values": [round(v, 0) for v in vs],
            "min": round(min(vs), 0), "max": round(max(vs), 0),
            "median": round(sorted(vs)[len(vs) // 2], 0),
            "q1": round(sorted(vs)[len(vs) // 4], 0),
            "q3": round(sorted(vs)[3 * len(vs) // 4], 0),
            "n": len(vs)
        }
        for t, vs in hr_by_type.items() if vs
    }

    # ACWR
    daily_load = defaultdict(float)
    for w in valid:
        day = w["startDate"][:10]
        duration_h = (w.get("duration") or 0) / 3600
        hr = w.get("avgHeartRate") or 130
        intensity = max(0.5, (hr / 130) ** 2)
        daily_load[day] += duration_h * intensity

    all_days = sorted(daily_load.keys())
    acwr_series = []
    for day in all_days:
        day_dt = datetime.fromisoformat(day)
        acute_start = day_dt - timedelta(days=6)
        chronic_start = day_dt - timedelta(days=27)
        acute = sum(daily_load[d] for d in all_days
                    if acute_start <= datetime.fromisoformat(d) <= day_dt) / 7
        chronic = sum(daily_load[d] for d in all_days
                      if chronic_start <= datetime.fromisoformat(d) <= day_dt) / 28
        ratio = acute / chronic if chronic > 0.01 else 0
        acwr_series.append({"date": day, "acute": round(acute, 2),
                            "chronic": round(chronic, 2), "ratio": round(ratio, 2)})

    # Load trend 30/60/90
    trend = []
    for day in all_days:
        day_dt = datetime.fromisoformat(day)
        l30 = sum(daily_load[d] for d in all_days
                  if (day_dt - timedelta(days=29)) <= datetime.fromisoformat(d) <= day_dt)
        l60 = sum(daily_load[d] for d in all_days
                  if (day_dt - timedelta(days=59)) <= datetime.fromisoformat(d) <= day_dt)
        l90 = sum(daily_load[d] for d in all_days
                  if (day_dt - timedelta(days=89)) <= datetime.fromisoformat(d) <= day_dt)
        trend.append({"date": day, "l30": round(l30, 1),
                      "l60": round(l60, 1), "l90": round(l90, 1)})

    last_acwr = acwr_series[-1] if acwr_series else None

    def acwr_status(ratio):
        if ratio == 0: return "rest"
        if ratio < 0.8: return "detraining"
        if ratio <= 1.3: return "sweet"
        if ratio <= 1.5: return "warning"
        return "overtraining"

    current_status = acwr_status(last_acwr["ratio"]) if last_acwr else "no_data"
    last30_acwr = acwr_series[-30:] if len(acwr_series) >= 30 else acwr_series
    pct_sweet = round(100 * sum(1 for x in last30_acwr if 0.8 <= x["ratio"] <= 1.3) / len(last30_acwr), 0) if last30_acwr else 0
    pct_over = round(100 * sum(1 for x in last30_acwr if x["ratio"] > 1.5) / len(last30_acwr), 0) if last30_acwr else 0
    pct_under = round(100 * sum(1 for x in last30_acwr if 0 < x["ratio"] < 0.8) / len(last30_acwr), 0) if last30_acwr else 0

    if len(acwr_series) >= 8:
        chronic_now = last_acwr["chronic"]
        chronic_7d_ago = acwr_series[-8]["chronic"]
        weekly_pct = round((chronic_now / chronic_7d_ago - 1) * 100, 1) if chronic_7d_ago > 0 else 0
    else:
        weekly_pct = None

    load_health = {
        "current_ratio": last_acwr["ratio"] if last_acwr else 0,
        "current_acute": last_acwr["acute"] if last_acwr else 0,
        "current_chronic": last_acwr["chronic"] if last_acwr else 0,
        "status": current_status,
        "weekly_pct_change": weekly_pct,
        "last30_pct_sweet": pct_sweet,
        "last30_pct_over": pct_over,
        "last30_pct_under": pct_under,
        "last_date": all_days[-1] if all_days else None,
    }

    # Max streak + current streak
    dates_sorted = sorted(set(w["startDate"][:10] for w in valid))
    max_streak = current_streak = 0
    prev = None
    for d in dates_sorted:
        if prev:
            diff = (datetime.fromisoformat(d) - datetime.fromisoformat(prev)).days
            current_streak = current_streak + 1 if diff == 1 else 1
        else:
            current_streak = 1
        max_streak = max(max_streak, current_streak)
        prev = d

    # Current streak (from today backward)
    today = datetime.now().date()
    cur_streak = 0
    check_day = today
    days_set = set(dates_sorted)
    while str(check_day) in days_set:
        cur_streak += 1
        check_day = check_day - timedelta(days=1)
    if cur_streak == 0 and str(today - timedelta(days=1)) in days_set:
        check_day = today - timedelta(days=1)
        while str(check_day) in days_set:
            cur_streak += 1
            check_day = check_day - timedelta(days=1)

    # Top 5 months by distance
    top5 = sorted(by_month.items(), key=lambda x: x[1]["distance"], reverse=True)[:5]

    # PRs by type
    def pace_min_per_km(distance_m, duration_s):
        if not distance_m or not duration_s or distance_m == 0:
            return None
        return (duration_s / 60) / (distance_m / 1000)

    prs_by_type = {}
    for t in by_type:
        max_dist_w = max((w for w in valid if w.get("type") == t and (w.get("distance") or 0) > 0),
                         key=lambda w: w["distance"], default=None)
        max_dur_w = max((w for w in valid if w.get("type") == t and (w.get("duration") or 0) > 0),
                        key=lambda w: w["duration"], default=None)
        max_hr_ws = [w for w in valid if w.get("type") == t
                     and w.get("avgHeartRate")
                     and HR_MIN_CREDIBLE <= w["avgHeartRate"] <= HR_MAX_CREDIBLE]
        max_hr_w = max(max_hr_ws, key=lambda w: w["avgHeartRate"], default=None)
        pace_ws = [w for w in valid if w.get("type") == t
                   and (w.get("distance") or 0) > 1000
                   and (w.get("duration") or 0) > 60]
        best_pace_w = min(pace_ws, key=lambda w: pace_min_per_km(w["distance"], w["duration"]), default=None) if pace_ws else None

        prs_by_type[t] = {
            "count": by_type[t]["count"],
            "max_distance": {
                "date": max_dist_w["startDate"][:10],
                "value_km": round(max_dist_w["distance"] / 1000, 2)
            } if max_dist_w else None,
            "max_duration": {
                "date": max_dur_w["startDate"][:10],
                "value_hours": round(max_dur_w["duration"] / 3600, 2)
            } if max_dur_w else None,
            "max_avg_hr": {
                "date": max_hr_w["startDate"][:10],
                "value_bpm": round(max_hr_w["avgHeartRate"], 0)
            } if max_hr_w else None,
            "best_pace": {
                "date": best_pace_w["startDate"][:10],
                "value_min_km": round(pace_min_per_km(best_pace_w["distance"], best_pace_w["duration"]), 2),
                "distance_km": round(best_pace_w["distance"] / 1000, 2)
            } if best_pace_w else None,
            "avg_hr": round(sum(w["avgHeartRate"] for w in max_hr_ws) / len(max_hr_ws), 0) if max_hr_ws else None,
        }

    # Scatter HR vs distance
    scatter = [
        {
            "x": round(w["distance"] / 1000, 2),
            "y": round(w["avgHeartRate"], 0),
            "type": w.get("type", "unknown"),
            "date": w["startDate"][:10]
        }
        for w in hr_credible if w.get("distance") and w["distance"] > 500
    ]

    # Cumulative km (monthly)
    cumulative = 0.0
    cumulative_km = []
    for m in sorted(by_month.keys()):
        monthly_km = round(by_month[m]["distance"] / 1000, 1)
        cumulative += monthly_km
        cumulative_km.append({"month": m, "km": monthly_km, "cumulative": round(cumulative, 1)})

    # YoY comparison
    now_year = str(datetime.now().year)
    prev_year = str(datetime.now().year - 1)
    yoy_cur = round((by_year.get(now_year, {}).get("distance") or 0) / 1000, 1)
    yoy_prev = round((by_year.get(prev_year, {}).get("distance") or 0) / 1000, 1)
    yoy_pct = round((yoy_cur / yoy_prev - 1) * 100, 1) if yoy_prev > 0 else None

    # Favorite type (most workouts)
    fav_type = max(by_type.items(), key=lambda x: x[1]["count"], default=(None, {}))[0] if by_type else None

    return {
        "kpi": {
            "total_workouts": len(valid),
            "total_distance_km": round(sum(w.get("distance", 0) or 0 for w in valid) / 1000, 1),
            "total_calories": round(sum(w.get("calories", 0) or 0 for w in valid), 0),
            "total_duration_hours": round(sum(w.get("duration", 0) or 0 for w in valid) / 3600, 1),
            "first_date": valid[0]["startDate"] if valid else None,
            "last_date": valid[-1]["startDate"] if valid else None,
            "unique_days": len(by_day),
            "max_streak_days": max_streak,
            "current_streak_days": cur_streak,
            "years_active": len(set(w["startDate"][:4] for w in valid)),
            "avg_hr_global": round(sum(w["avgHeartRate"] for w in hr_credible) / len(hr_credible), 0) if hr_credible else None,
            "fav_type": fav_type,
            "yoy_current_km": yoy_cur,
            "yoy_prev_km": yoy_prev,
            "yoy_pct_change": yoy_pct,
            "current_year": now_year,
            "prev_year": prev_year,
        },
        "by_type": {
            t: {
                "count": v["count"],
                "distance_km": round(v["distance"] / 1000, 1),
                "duration_hours": round(v["duration"] / 3600, 1),
                "calories": round(v["calories"], 0),
                "avg_hr": round(v["hr_sum"] / v["hr_n"], 0) if v["hr_n"] else None
            }
            for t, v in by_type.items()
        },
        "by_month": {
            m: {
                "count": v["count"],
                "distance_km": round(v["distance"] / 1000, 1),
                "duration_hours": round(v["duration"] / 3600, 1),
                "calories": round(v["calories"], 0),
                "types": dict(v["types"])
            }
            for m, v in sorted(by_month.items())
        },
        "by_year": {
            y: {
                "count": v["count"],
                "distance_km": round(v["distance"] / 1000, 1),
                "calories": round(v["calories"], 0),
                "duration_hours": round(v["duration"] / 3600, 1)
            }
            for y, v in sorted(by_year.items())
        },
        "by_day": dict(by_day),
        "by_day_type": by_day_type_out,
        "hr_monthly": hr_monthly,
        "hr_distribution": hr_dist,
        "acwr": acwr_series[-730:],
        "trend": trend[-730:],
        "load_health": load_health,
        "top5_months": [
            {"month": m, "distance_km": round(v["distance"] / 1000, 1), "count": v["count"]}
            for m, v in top5
        ],
        "prs": prs_by_type,
        "scatter": scatter,
        "weekday_dist": weekday_dist,
        "cumulative_km": cumulative_km,
        "types": sorted(by_type.keys()),
        "years": sorted(by_year.keys()),
    }


def render_dashboard(stats):
    kpi = stats["kpi"]
    first = kpi["first_date"][:10] if kpi["first_date"] else "—"
    last = kpi["last_date"][:10] if kpi["last_date"] else "—"

    type_emojis = {
        "running": "🏃", "cycling": "🚴", "walking": "🚶",
        "swimming": "🏊", "hiking": "🥾", "rowing": "🚣",
        "elliptical": "⭕", "strength": "💪", "functional": "🤸",
        "yoga": "🧘", "pilates": "🤸", "hiit": "⚡", "other": "📦"
    }

    prs_cards = ""
    for t in sorted(stats["prs"].keys(), key=lambda x: -stats["prs"][x]["count"]):
        p = stats["prs"][t]
        if not p["count"]:
            continue
        emoji = type_emojis.get(t, "📦")
        rows = ""
        if p["max_distance"]:
            rows += f'<tr><td>Max distance</td><td><b>{p["max_distance"]["value_km"]} km</b></td><td>{p["max_distance"]["date"]}</td></tr>'
        if p["max_duration"]:
            rows += f'<tr><td>Max duration</td><td><b>{p["max_duration"]["value_hours"]} h</b></td><td>{p["max_duration"]["date"]}</td></tr>'
        if p["best_pace"] and p["best_pace"]["value_min_km"]:
            pace = p["best_pace"]
            m_p = int(pace["value_min_km"])
            s_p = int((pace["value_min_km"] - m_p) * 60)
            rows += f'<tr><td>Best pace</td><td><b>{m_p}:{s_p:02d} /km</b></td><td>{pace["date"]} · {pace["distance_km"]} km</td></tr>'
        if p["max_avg_hr"]:
            rows += f'<tr><td>Peak avg HR</td><td><b>{int(p["max_avg_hr"]["value_bpm"])} bpm</b></td><td>{p["max_avg_hr"]["date"]}</td></tr>'
        if p["avg_hr"]:
            rows += f'<tr><td>Avg HR</td><td><b>{int(p["avg_hr"])} bpm</b></td><td>—</td></tr>'

        prs_cards += f"""
        <div class="pr-card">
          <div class="pr-card-header">{emoji} <span>{t}</span> <span class="badge">{p["count"]}</span></div>
          <table class="pr-table">{rows}</table>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="format-detection" content="telephone=no">
<title>Workouts Dashboard — Jose 2015-2026</title>
<link rel="stylesheet" href="styles.css">
<script src="chart.min.js"></script>
</head>
<body>

<div id="newBanner" class="new-banner" aria-live="polite"></div>

<header class="site-header">
  <div class="header-left">
    <h1 class="site-title">Workouts</h1>
    <div class="site-meta">{first} → {last} · {kpi["years_active"]} years · <span id="filterInfo">{kpi["total_workouts"]:,} workouts</span></div>
  </div>
  <div class="header-right">
    <div class="conn-status"><span class="conn-dot" id="connDot"></span><span id="connText">—</span></div>
    <button class="btn-icon" id="refreshBtn" onclick="manualRefresh()" title="Refresh data">↻</button>
  </div>
</header>

<!-- ── Hero strip ─────────────────────────────────────── -->
<section class="hero-strip" id="heroStrip">
  <div class="hero-card" id="heroStreak">
    <div class="hero-label">Longest streak</div>
    <div class="hero-value"><span id="heroStreakVal">{kpi["max_streak_days"]}</span><span class="hero-unit">days</span></div>
    <div class="hero-sub" id="heroStreakSub">Current: {kpi["current_streak_days"]}d</div>
  </div>
  <div class="hero-card" id="heroType">
    <div class="hero-label">Favorite type</div>
    <div class="hero-value" id="heroTypeVal">{type_emojis.get(kpi["fav_type"] or "", "📦")} {kpi["fav_type"] or "—"}</div>
    <div class="hero-sub" id="heroTypeSub"></div>
  </div>
  <div class="hero-card" id="heroYoy">
    <div class="hero-label">This year vs last</div>
    <div class="hero-value"><span id="heroYoyVal">{kpi["yoy_current_km"]:,.0f}</span><span class="hero-unit">km</span></div>
    <div class="hero-sub" id="heroYoySub"></div>
  </div>
  <div class="hero-card" id="heroAcwr">
    <div class="hero-label">Training load</div>
    <div class="hero-value" id="heroAcwrVal">—</div>
    <div class="hero-sub" id="heroAcwrSub"></div>
  </div>
  <div class="hero-card" id="heroPR">
    <div class="hero-label">Top distance PR</div>
    <div class="hero-value" id="heroPRVal">—</div>
    <div class="hero-sub" id="heroPRSub"></div>
  </div>
</section>

<!-- ── KPI bar ─────────────────────────────────────────── -->
<section class="kpi-grid">
  <div class="kpi"><div class="kpi-label">Workouts</div><div class="kpi-value" id="kpiCount">{kpi["total_workouts"]:,}</div></div>
  <div class="kpi"><div class="kpi-label">Distance</div><div class="kpi-value"><span id="kpiDist">{kpi["total_distance_km"]:,.1f}</span><span class="kpi-unit">km</span></div></div>
  <div class="kpi"><div class="kpi-label">Active time</div><div class="kpi-value"><span id="kpiDur">{kpi["total_duration_hours"]:,.0f}</span><span class="kpi-unit">h</span></div></div>
  <div class="kpi"><div class="kpi-label">Calories</div><div class="kpi-value"><span id="kpiCal">{kpi["total_calories"]:,.0f}</span><span class="kpi-unit">kcal</span></div></div>
  <div class="kpi"><div class="kpi-label">Active days</div><div class="kpi-value" id="kpiDays">{kpi["unique_days"]:,}</div></div>
  <div class="kpi"><div class="kpi-label">Max streak</div><div class="kpi-value"><span id="kpiStreak">{kpi["max_streak_days"]}</span><span class="kpi-unit">days</span></div></div>
  <div class="kpi"><div class="kpi-label">ACWR ratio</div><div class="kpi-value" id="kpiAcwr">—</div></div>
  <div class="kpi"><div class="kpi-label">Avg HR</div><div class="kpi-value"><span>{kpi["avg_hr_global"] or "—"}</span><span class="kpi-unit">{" bpm" if kpi["avg_hr_global"] else ""}</span></div></div>
</section>

<!-- ── Filters ─────────────────────────────────────────── -->
<section class="filters-bar">
  <div class="filter-group">
    <span class="filter-label">Type</span>
    <div id="typeFilters" class="chip-group"></div>
  </div>
  <div class="filter-group">
    <span class="filter-label">Year</span>
    <input type="number" class="year-input" id="yearFrom" placeholder="from" min="2015" max="2026">
    <span class="filter-sep">→</span>
    <input type="number" class="year-input" id="yearTo" placeholder="to" min="2015" max="2026">
  </div>
  <div class="filter-group">
    <label class="toggle-label">
      <input type="checkbox" id="compareToggle" class="toggle-input">
      <span class="toggle-track"></span>
      Compare last year
    </label>
  </div>
  <button class="btn-reset" onclick="resetFilters()">Reset</button>
</section>

<!-- ── Charts grid ─────────────────────────────────────── -->
<section class="chart-grid">

  <div class="chart-card" data-lazy="monthlyDist">
    <div class="chart-header"><h3>Monthly distance</h3></div>
    <div class="chart-body"><canvas id="monthlyDistChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="typeDist">
    <div class="chart-header"><h3>Type distribution</h3></div>
    <div class="chart-body"><canvas id="typeDistChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="weekdayBar">
    <div class="chart-header"><h3>Activity by weekday</h3></div>
    <div class="chart-body"><canvas id="weekdayChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="cumulative">
    <div class="chart-header"><h3>Cumulative distance</h3></div>
    <div class="chart-body"><canvas id="cumulativeChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="scatter">
    <div class="chart-header"><h3>HR vs distance</h3></div>
    <div class="chart-body"><canvas id="scatterChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="hrMonthly">
    <div class="chart-header"><h3>Monthly HR by type</h3></div>
    <div class="chart-body"><canvas id="hrMonthlyChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="hrBox">
    <div class="chart-header"><h3>HR distribution by type</h3></div>
    <div class="chart-body"><canvas id="hrBoxChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="acwr">
    <div class="chart-header"><h3>ACWR — Acute:Chronic Workload</h3></div>
    <div class="chart-body"><canvas id="acwrChart"></canvas></div>
  </div>

  <div class="chart-card" data-lazy="loadTrend">
    <div class="chart-header"><h3>Load trend 30 / 60 / 90 days</h3></div>
    <div class="chart-body"><canvas id="trendChart"></canvas></div>
  </div>

  <div class="chart-card chart-full" data-lazy="heatmap">
    <div class="chart-header"><h3>Activity heatmap</h3></div>
    <div class="heatmap-wrap" id="heatmap"></div>
    <div class="heatmap-legend">
      Less <span data-l="0"></span><span data-l="1"></span><span data-l="2"></span><span data-l="3"></span><span data-l="4"></span> More
    </div>
  </div>

</section>

<!-- ── Personal Records ───────────────────────────────── -->
<section class="section-block">
  <h2 class="section-title">Personal Records</h2>
  <div class="prs-grid">{prs_cards}</div>
</section>

<!-- ── Annual Goals ───────────────────────────────────── -->
<section class="section-block">
  <div class="goals-header">
    <h2 class="section-title">Annual Goals</h2>
    <button class="btn-add" onclick="addGoal()">+ Add goal</button>
  </div>
  <div id="goalsContainer" class="goals-grid"></div>
  <div id="goalsEmpty" class="goals-empty" style="display:none">
    No goals set. Add one to track your progress.
  </div>
</section>

<!-- ── Top 5 months ───────────────────────────────────── -->
<section class="section-block">
  <h2 class="section-title">Top 5 months by distance</h2>
  <table class="data-table" id="top5Table">
    <thead><tr><th>Month</th><th>Workouts</th><th>Distance</th></tr></thead>
    <tbody id="top5Body"></tbody>
  </table>
</section>

<script>
let data = null;

async function bootstrap() {{
  try {{
    const r = await fetch('data.json');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    data = await r.json();
    initApp();
  }} catch(e) {{
    console.error('bootstrap error', e);
    document.body.innerHTML = '<div style="padding:40px;color:#f85149;font-family:monospace">Failed to load data: ' + e.message + '</div>';
  }}
}}

function initApp() {{
  readURL();
  buildTypeChips();
  document.getElementById('yearFrom').value = yearFrom;
  document.getElementById('yearTo').value = yearTo;
  document.getElementById('compareToggle').checked = compareMode;
  document.getElementById('yearFrom').onchange = e => {{ yearFrom = parseInt(e.target.value) || yearFrom; renderAll(); }};
  document.getElementById('yearTo').onchange = e => {{ yearTo = parseInt(e.target.value) || yearTo; renderAll(); }};
  document.getElementById('compareToggle').onchange = e => {{ compareMode = e.target.checked; renderAll(); }};
  renderHero();
  renderTop5();
  renderGoals();
  reloadVisibleCharts();
  setupLazyCharts();
  lastSeenTs = data.kpi.last_date || '0';
  setStatus('ok', 'connected');
  pollNewWorkouts();
  setInterval(pollNewWorkouts, POLL_MS);
}}

// ── State ─────────────────────────────────────────────────
let activeTypes = new Set();
let yearFrom = {kpi["first_date"][:4] if kpi["first_date"] else 2015};
let yearTo = {kpi["last_date"][:4] if kpi["last_date"] else 2026};
let compareMode = false;

// ── Chart registry ────────────────────────────────────────
const charts = {{}};
const loaded = new Set();

// ── URL persistence ───────────────────────────────────────
function readURL() {{
  const p = new URLSearchParams(window.location.search);
  const types = p.get('types');
  if (types) types.split(',').filter(Boolean).forEach(t => activeTypes.add(t));
  const from = parseInt(p.get('from'));
  const to = parseInt(p.get('to'));
  if (from && from >= 2015 && from <= 2026) yearFrom = from;
  if (to && to >= 2015 && to <= 2026) yearTo = to;
  if (to < from) yearTo = yearFrom;
  compareMode = p.get('compare') === '1';
}}

function writeURL() {{
  const p = new URLSearchParams();
  if (activeTypes.size > 0) p.set('types', [...activeTypes].sort().join(','));
  const minYear = parseInt(data.years[0]);
  const maxYear = parseInt(data.years[data.years.length - 1]);
  if (yearFrom !== minYear) p.set('from', yearFrom);
  if (yearTo !== maxYear) p.set('to', yearTo);
  if (compareMode) p.set('compare', '1');
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : window.location.pathname);
}}

// ── Filter helpers ────────────────────────────────────────
function filteredMonths() {{
  return Object.keys(data.by_month).filter(m => {{
    const y = parseInt(m.slice(0, 4));
    return y >= yearFrom && y <= yearTo;
  }});
}}

function prevYearMonths() {{
  return Object.keys(data.by_month).filter(m => {{
    const y = parseInt(m.slice(0, 4));
    return y >= (yearFrom - 1) && y <= (yearTo - 1);
  }});
}}

function monthTypeWeight(m) {{
  if (activeTypes.size === 0) return 1;
  const v = data.by_month[m];
  if (!v) return 0;
  const total = Object.values(v.types).reduce((a, b) => a + b, 0);
  const sel = Object.entries(v.types)
    .filter(([t]) => activeTypes.has(t))
    .reduce((a, [, c]) => a + c, 0);
  return total > 0 ? sel / total : 0;
}}

// ── KPI recompute ─────────────────────────────────────────
function recomputeKPIs() {{
  const months = filteredMonths();
  let count = 0, dist = 0, cal = 0, dur = 0;
  months.forEach(m => {{
    const v = data.by_month[m];
    const w = monthTypeWeight(m);
    if (w === 0) return;
    count += Math.round(v.count * w);
    dist += v.distance_km * w;
    cal += v.calories * w;
    dur += v.duration_hours * w;
  }});

  const filteredDays = Object.keys(data.by_day).filter(d => {{
    const y = parseInt(d.slice(0, 4));
    return y >= yearFrom && y <= yearTo;
  }});
  const maxStr = computeMaxStreak(filteredDays);

  setEl('kpiCount', count.toLocaleString());
  setEl('kpiDist', dist.toFixed(1));
  setEl('kpiCal', cal.toFixed(0));
  setEl('kpiDur', dur.toFixed(0));
  setEl('kpiDays', filteredDays.length.toLocaleString());
  setEl('kpiStreak', maxStr);

  const parts = [];
  if (activeTypes.size) parts.push([...activeTypes].join(', '));
  const minY = parseInt(data.years[0]), maxY = parseInt(data.years[data.years.length - 1]);
  if (yearFrom !== minY || yearTo !== maxY) parts.push(`${{yearFrom}}-${{yearTo}}`);
  setEl('filterInfo', count.toLocaleString() + ' workouts' + (parts.length ? ' · ' + parts.join(' · ') : ''));
}}

function computeMaxStreak(dates) {{
  const sorted = [...dates].sort();
  let max = 0, cur = 0, prev = null;
  for (const d of sorted) {{
    if (prev) {{
      const diff = (new Date(d) - new Date(prev)) / 86400000;
      cur = diff === 1 ? cur + 1 : 1;
    }} else cur = 1;
    max = Math.max(max, cur);
    prev = d;
  }}
  return max;
}}

function setEl(id, val) {{
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}}

// ── Hero strip ────────────────────────────────────────────
function renderHero() {{
  // YoY sub
  const yoy = data.kpi.yoy_pct_change;
  const yoyDir = yoy == null ? '' : yoy >= 0 ? '↑' : '↓';
  const yoyColor = yoy == null ? '' : yoy >= 0 ? 'var(--accent)' : 'var(--danger)';
  const yoySub = yoy != null
    ? `<span style="color:${{yoyColor}}">${{yoyDir}} ${{Math.abs(yoy)}}%</span> vs ${{data.kpi.prev_year}} (${{data.kpi.yoy_prev_km.toLocaleString()}} km)`
    : `prev year: ${{data.kpi.yoy_prev_km.toLocaleString()}} km`;
  setEl('heroYoySub', '');
  document.getElementById('heroYoySub').innerHTML = yoySub;

  // Fav type sub
  const ft = data.kpi.fav_type;
  if (ft && data.by_type[ft]) {{
    setEl('heroTypeSub', data.by_type[ft].count + ' sessions');
  }}

  // ACWR hero
  const h = data.load_health;
  const acwrLabels = {{
    sweet: '🟢 In the zone', warning: '🟠 Elevated', overtraining: '🔴 Overreaching',
    detraining: '🟡 Detraining', rest: '⚪ Rest', no_data: '— No data'
  }};
  const acwrColors = {{
    sweet: 'var(--accent)', warning: 'var(--warning)', overtraining: 'var(--danger)',
    detraining: 'var(--warning)', rest: 'var(--text-muted)', no_data: 'var(--text-muted)'
  }};
  const acwrEl = document.getElementById('heroAcwrVal');
  acwrEl.textContent = acwrLabels[h.status] || '—';
  acwrEl.style.color = acwrColors[h.status] || '';
  acwrEl.style.fontSize = '18px';
  setEl('heroAcwrSub', `ratio: ${{h.current_ratio}} · 30d: ${{h.last30_pct_sweet}}% sweet`);
  setEl('kpiAcwr', h.current_ratio || '—');
  document.getElementById('kpiAcwr').style.color = acwrColors[h.status] || '';

  // Top PR (running max distance or first type with max dist)
  const prTypes = Object.entries(data.prs).sort((a, b) => b[1].count - a[1].count);
  const topPR = prTypes.find(([, p]) => p.max_distance);
  if (topPR) {{
    const [type, p] = topPR;
    document.getElementById('heroPRVal').textContent = p.max_distance.value_km + ' km';
    setEl('heroPRSub', type + ' · ' + p.max_distance.date);
  }}
}}

// ── Type filter chips ─────────────────────────────────────
function buildTypeChips() {{
  const container = document.getElementById('typeFilters');
  container.innerHTML = '';
  data.types.forEach(t => {{
    const chip = document.createElement('button');
    chip.className = 'chip' + (activeTypes.size === 0 || activeTypes.has(t) ? ' active' : '');
    chip.textContent = t;
    chip.dataset.type = t;
    chip.onclick = () => toggleType(t);
    container.appendChild(chip);
  }});
}}

function toggleType(t) {{
  if (activeTypes.has(t)) activeTypes.delete(t);
  else activeTypes.add(t);
  syncChips();
  renderAll();
  writeURL();
}}

function syncChips() {{
  document.querySelectorAll('.chip[data-type]').forEach(c => {{
    const isActive = activeTypes.size === 0 || activeTypes.has(c.dataset.type);
    c.className = 'chip' + (isActive ? ' active' : '');
  }});
}}

function resetFilters() {{
  activeTypes.clear();
  yearFrom = parseInt(data.years[0]);
  yearTo = parseInt(data.years[data.years.length - 1]);
  compareMode = false;
  document.getElementById('yearFrom').value = yearFrom;
  document.getElementById('yearTo').value = yearTo;
  document.getElementById('compareToggle').checked = false;
  syncChips();
  renderAll();
  writeURL();
}}

// ── Charts ────────────────────────────────────────────────
const COLORS = ['#58a6ff','#3fb950','#f0883e','#ff6b6b','#a371f7','#39d353','#ffa657','#79c0ff','#56d364','#ff7b72'];

function chartDefaults() {{
  return {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: 'var(--text-muted)', maxTicksLimit: 18 }}, grid: {{ color: 'var(--border)' }} }},
      y: {{ ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
    }}
  }};
}}

function mkChart(id, config) {{
  const el = document.getElementById(id);
  if (!el) return null;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el.getContext('2d'), config);
  return charts[id];
}}

function initMonthlyDist() {{
  const months = filteredMonths();
  const curData = months.map(m => data.by_month[m].distance_km * monthTypeWeight(m));
  const datasets = [{{
    label: 'Distance (km)', data: curData,
    borderColor: COLORS[0], backgroundColor: COLORS[0] + '22',
    fill: true, tension: 0.35, pointRadius: 1, pointHoverRadius: 4, borderWidth: 2
  }}];
  if (compareMode) {{
    const prevM = prevYearMonths();
    datasets.push({{
      label: 'Prev year', data: prevM.map(m => data.by_month[m].distance_km),
      borderColor: COLORS[2], backgroundColor: 'transparent',
      tension: 0.35, pointRadius: 1, pointHoverRadius: 4, borderWidth: 1.5,
      borderDash: [4, 3]
    }});
  }}
  const opts = chartDefaults();
  opts.plugins.legend = {{ display: compareMode, labels: {{ color: 'var(--text)' }} }};
  mkChart('monthlyDistChart', {{ type: 'line', data: {{ labels: months, datasets }}, options: opts }});
}}

function initTypeDist() {{
  const months = filteredMonths();
  const byT = {{}};
  months.forEach(m => {{
    const v = data.by_month[m];
    Object.entries(v.types).forEach(([t, c]) => {{
      if (activeTypes.size > 0 && !activeTypes.has(t)) return;
      byT[t] = (byT[t] || 0) + c;
    }});
  }});
  const sorted = Object.entries(byT).sort((a, b) => b[1] - a[1]);
  mkChart('typeDistChart', {{
    type: 'doughnut',
    data: {{
      labels: sorted.map(([t]) => t),
      datasets: [{{ data: sorted.map(([, c]) => c), backgroundColor: COLORS, borderWidth: 0 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'right', labels: {{ color: 'var(--text)', boxWidth: 12, padding: 12 }} }} }}
    }}
  }});
}}

function initWeekday() {{
  const labels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const dist = labels.map(d => +(data.weekday_dist[d]?.distance_km || 0).toFixed(1));
  mkChart('weekdayChart', {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: 'Distance (km)', data: dist, backgroundColor: COLORS[0] + 'cc', borderRadius: 4 }}] }},
    options: chartDefaults()
  }});
}}

function initCumulative() {{
  const items = data.cumulative_km.filter(x => {{
    const y = parseInt(x.month.slice(0, 4));
    return y >= yearFrom && y <= yearTo;
  }});
  mkChart('cumulativeChart', {{
    type: 'line',
    data: {{
      labels: items.map(x => x.month),
      datasets: [{{
        label: 'Cumulative km', data: items.map(x => x.cumulative),
        borderColor: COLORS[1], backgroundColor: COLORS[1] + '22',
        fill: true, tension: 0.2, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2
      }}]
    }},
    options: chartDefaults()
  }});
}}

function initScatter() {{
  const byT = {{}};
  data.scatter.forEach(p => {{
    if (activeTypes.size > 0 && !activeTypes.has(p.type)) return;
    const y = parseInt(p.date.slice(0, 4));
    if (y < yearFrom || y > yearTo) return;
    (byT[p.type] = byT[p.type] || []).push(p);
  }});
  const datasets = Object.entries(byT).map(([t, pts], i) => ({{
    label: t, data: pts, backgroundColor: COLORS[i % COLORS.length] + 'bb', pointRadius: 3
  }}));
  const opts = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'right', labels: {{ color: 'var(--text)', boxWidth: 10, padding: 10 }} }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Distance (km)', color: 'var(--text-muted)' }}, ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }},
      y: {{ title: {{ display: true, text: 'Avg HR (bpm)', color: 'var(--text-muted)' }}, ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
    }}
  }};
  mkChart('scatterChart', {{ type: 'scatter', data: {{ datasets }}, options: opts }});
}}

function initHrMonthly() {{
  const months = filteredMonths();
  const allT = [...new Set(months.flatMap(m => Object.keys(data.hr_monthly[m] || {{}})))].sort();
  const datasets = allT.map((t, i) => ({{
    label: t, data: months.map(m => data.hr_monthly[m]?.[t] ?? null),
    borderColor: COLORS[i % COLORS.length],
    tension: 0.3, spanGaps: true, pointRadius: 1, pointHoverRadius: 4
  }}));
  const opts = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'right', labels: {{ color: 'var(--text)', boxWidth: 10, padding: 8 }} }} }},
    scales: {{
      x: {{ ticks: {{ color: 'var(--text-muted)', maxTicksLimit: 16 }}, grid: {{ color: 'var(--border)' }} }},
      y: {{ title: {{ display: true, text: 'Avg HR (bpm)', color: 'var(--text-muted)' }}, ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
    }}
  }};
  mkChart('hrMonthlyChart', {{ type: 'line', data: {{ labels: months, datasets }}, options: opts }});
}}

function initHrBox() {{
  const months = filteredMonths();
  const activeT = activeTypes.size > 0
    ? [...activeTypes]
    : Object.keys(data.hr_distribution);
  const types = activeT.filter(t => data.hr_distribution[t]).sort();
  const c = ['#30363d','#58a6ff','#3fb950','#f0883e','#ff6b6b'];
  const lbls = ['Min','Q1','Median','Q3','Max'];
  const keys = ['min','q1','median','q3','max'];
  const datasets = keys.map((k, i) => ({{
    label: lbls[i], data: types.map(t => data.hr_distribution[t][k] || 0),
    backgroundColor: c[i]
  }}));
  const opts = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top', labels: {{ color: 'var(--text)', boxWidth: 10 }} }} }},
    scales: {{
      x: {{ ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }},
      y: {{ title: {{ display: true, text: 'HR (bpm)', color: 'var(--text-muted)' }}, ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
    }}
  }};
  mkChart('hrBoxChart', {{ type: 'bar', data: {{ labels: types, datasets }}, options: opts }});
}}

const acwrZonesPlugin = {{
  id: 'acwrZones',
  beforeDatasetsDraw(chart) {{
    const {{ ctx, chartArea: {{ left, right }}, scales: {{ y }} }} = chart;
    if (!y) return;
    [
      [0, 0.8, 'rgba(139,148,158,0.07)'],
      [0.8, 1.3, 'rgba(63,185,80,0.10)'],
      [1.3, 1.5, 'rgba(210,153,34,0.10)'],
      [1.5, 2.5, 'rgba(248,81,73,0.10)'],
    ].forEach(([y1, y2, color]) => {{
      const py1 = y.getPixelForValue(y1), py2 = y.getPixelForValue(y2);
      ctx.fillStyle = color;
      ctx.fillRect(left, Math.min(py1, py2), right - left, Math.abs(py2 - py1));
    }});
  }}
}};

function initAcwr() {{
  const recent = data.acwr.slice(-365);
  const opts = {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ afterLabel: ctx => {{
        const r = ctx.parsed.y;
        if (r === 0) return 'Rest';
        if (r < 0.8) return 'Detraining';
        if (r <= 1.3) return 'Sweet spot';
        if (r <= 1.5) return 'Elevated';
        return 'Overreaching';
      }}}}}}
    }},
    scales: {{
      x: {{ ticks: {{ color: 'var(--text-muted)', maxTicksLimit: 12 }}, grid: {{ color: 'var(--border)' }} }},
      y: {{ suggestedMin: 0, suggestedMax: 2, ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
    }}
  }};
  mkChart('acwrChart', {{
    type: 'line',
    data: {{ labels: recent.map(d => d.date), datasets: [{{
      data: recent.map(d => d.ratio),
      borderColor: COLORS[0], backgroundColor: COLORS[0] + '22',
      fill: true, tension: 0.2, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2
    }}] }},
    options: opts,
    plugins: [acwrZonesPlugin]
  }});
}}

function initTrend() {{
  const recent = data.trend.slice(-365);
  mkChart('trendChart', {{
    type: 'line',
    data: {{ labels: recent.map(d => d.date), datasets: [
      {{ label: '30d', data: recent.map(d => d.l30), borderColor: COLORS[0], tension: 0.3, pointRadius: 0, borderWidth: 2 }},
      {{ label: '60d', data: recent.map(d => d.l60), borderColor: COLORS[1], tension: 0.3, pointRadius: 0, borderWidth: 2 }},
      {{ label: '90d', data: recent.map(d => d.l90), borderColor: COLORS[2], tension: 0.3, pointRadius: 0, borderWidth: 2 }},
    ] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'top', labels: {{ color: 'var(--text)', boxWidth: 10 }} }} }},
      scales: {{
        x: {{ ticks: {{ color: 'var(--text-muted)', maxTicksLimit: 12 }}, grid: {{ color: 'var(--border)' }} }},
        y: {{ ticks: {{ color: 'var(--text-muted)' }}, grid: {{ color: 'var(--border)' }} }}
      }}
    }}
  }});
}}

// ── Heatmap ───────────────────────────────────────────────
function renderHeatmap() {{
  const hm = document.getElementById('heatmap');
  const byDay = data.by_day;
  const maxC = Math.max(1, ...Object.values(byDay));
  function level(c) {{ return !c ? 0 : c < maxC * 0.25 ? 1 : c < maxC * 0.5 ? 2 : c < maxC * 0.75 ? 3 : 4; }}
  let html = '';
  for (let y = yearFrom; y <= yearTo; y++) {{
    for (let wk = 0; wk < 53; wk++) {{
      const d = new Date(y, 0, 1 + wk * 7);
      if (d.getFullYear() !== y) continue;
      const ds = d.toISOString().slice(0, 10);
      const byDT = data.by_day_type[ds] || {{}};
      const c = activeTypes.size === 0
        ? (byDay[ds] || 0)
        : Object.entries(byDT).filter(([t]) => activeTypes.has(t)).reduce((a, [, n]) => a + n, 0);
      html += `<span data-l="${{level(c)}}" title="${{ds}}: ${{c}} workout${{c !== 1 ? 's' : ''}}"></span>`;
    }}
  }}
  hm.innerHTML = html;
}}

// ── Lazy loading ──────────────────────────────────────────
const chartInits = {{
  monthlyDist: initMonthlyDist,
  typeDist: initTypeDist,
  weekdayBar: initWeekday,
  cumulative: initCumulative,
  scatter: initScatter,
  hrMonthly: initHrMonthly,
  hrBox: initHrBox,
  acwr: initAcwr,
  loadTrend: initTrend,
  heatmap: renderHeatmap,
}};

let observer;
function setupLazyCharts() {{
  observer = new IntersectionObserver((entries) => {{
    entries.forEach(entry => {{
      if (!entry.isIntersecting) return;
      const key = entry.target.dataset.lazy;
      if (key && chartInits[key]) {{
        chartInits[key]();
        loaded.add(key);
      }}
      observer.unobserve(entry.target);
    }});
  }}, {{ threshold: 0.1 }});

  document.querySelectorAll('[data-lazy]').forEach(el => observer.observe(el));
}}

function reloadVisibleCharts() {{
  document.querySelectorAll('[data-lazy]').forEach(el => {{
    const key = el.dataset.lazy;
    if (key && chartInits[key]) chartInits[key]();
  }});
}}

// ── Goals (localStorage) ──────────────────────────────────
const GOALS_KEY = 'dashboard_goals_v1';

function loadGoals() {{ return JSON.parse(localStorage.getItem(GOALS_KEY) || '[]'); }}
function saveGoals(g) {{ localStorage.setItem(GOALS_KEY, JSON.stringify(g)); }}

function getActualKm(type, year) {{
  let km = 0;
  Object.entries(data.by_month).forEach(([m, v]) => {{
    if (m.startsWith(year)) {{
      const ratio = type === '__all__' ? 1 : (v.types[type] || 0) / Math.max(1, Object.values(v.types).reduce((a,b)=>a+b,0));
      km += v.distance_km * ratio;
    }}
  }});
  return Math.round(km);
}}

function renderGoals() {{
  const goals = loadGoals();
  const container = document.getElementById('goalsContainer');
  const empty = document.getElementById('goalsEmpty');
  if (!goals.length) {{ container.innerHTML = ''; empty.style.display = ''; return; }}
  empty.style.display = 'none';
  container.innerHTML = goals.map((g, i) => {{
    const actual = getActualKm(g.type, g.year);
    const pct = Math.min(100, Math.round(actual / g.target_km * 100));
    const remaining = Math.max(0, g.target_km - actual);
    const typeLabel = g.type === '__all__' ? 'All types' : g.type;
    return `<div class="goal-card">
      <div class="goal-top">
        <span class="goal-title">${{typeLabel}} ${{g.year}}</span>
        <span class="goal-pct">${{pct}}%</span>
        <button class="goal-del" onclick="deleteGoal(${{i}})" title="Delete">✕</button>
      </div>
      <div class="goal-progress"><div class="goal-bar" style="width:${{pct}}%"></div></div>
      <div class="goal-detail">${{actual.toLocaleString()}} / ${{g.target_km.toLocaleString()}} km · ${{remaining.toLocaleString()}} km remaining</div>
    </div>`;
  }}).join('');
}}

function addGoal() {{
  const types = ['__all__', ...data.types];
  const typeOpts = types.map(t => `<option value="${{t}}">${{t === '__all__' ? 'All types' : t}}</option>`).join('');
  const yearOpts = data.years.map(y => `<option value="${{y}}" ${{y === data.kpi.current_year ? 'selected' : ''}}>${{y}}</option>`).join('');
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal">
      <h3>Add Goal</h3>
      <label>Type <select id="gType">${{typeOpts}}</select></label>
      <label>Year <select id="gYear">${{yearOpts}}</select></label>
      <label>Target km <input type="number" id="gTarget" placeholder="e.g. 1000" min="1" max="100000"></label>
      <div class="modal-btns">
        <button class="btn-primary" onclick="saveGoalModal()">Save</button>
        <button class="btn-ghost" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  modal.onclick = e => {{ if (e.target === modal) modal.remove(); }};
}}

function saveGoalModal() {{
  const type = document.getElementById('gType').value;
  const year = document.getElementById('gYear').value;
  const target_km = parseInt(document.getElementById('gTarget').value);
  if (!target_km || target_km < 1) return;
  const goals = loadGoals();
  goals.push({{ type, year, target_km }});
  saveGoals(goals);
  document.querySelector('.modal-overlay')?.remove();
  renderGoals();
}}

function deleteGoal(i) {{
  const goals = loadGoals();
  goals.splice(i, 1);
  saveGoals(goals);
  renderGoals();
}}

// ── Top 5 table ───────────────────────────────────────────
function renderTop5() {{
  const tbody = document.getElementById('top5Body');
  tbody.innerHTML = data.top5_months.map((r, i) =>
    `<tr${{i === 0 ? ' class="top1"' : ''}}><td>${{r.month}}</td><td>${{r.count}}</td><td>${{r.distance_km.toLocaleString()}} km</td></tr>`
  ).join('');
}}

// ── Live polling ──────────────────────────────────────────
let lastSeenTs = '0';
const POLL_MS = 60000;
let isReloading = false;

async function pollNewWorkouts() {{
  try {{
    setStatus('stale', 'checking…');
    const r = await fetch(`/api/since?ts=${{encodeURIComponent(lastSeenTs)}}`);
    if (!r.ok) throw new Error(r.status);
    const payload = await r.json();
    setStatus('ok', new Date().toLocaleTimeString());
    if (payload.count > 0) {{
      const dist = payload.workouts.reduce((a, x) => a + (x.distance || 0), 0) / 1000;
      showBanner(`${{payload.count}} new workout${{payload.count > 1 ? 's' : ''}} · ${{dist.toFixed(1)}} km`);
      lastSeenTs = payload.workouts.at(-1).startDate;
    }}
  }} catch {{ setStatus('error', 'offline'); }}
}}

async function manualRefresh() {{
  if (isReloading) return;
  isReloading = true;
  document.getElementById('refreshBtn').textContent = '⟳';
  setStatus('stale', 'refreshing…');
  try {{
    const r = await fetch('/api/refresh', {{ method: 'POST' }});
    if (!r.ok) throw new Error(r.status);
    const payload = await r.json();
    Object.assign(data, payload.stats);
    reloadVisibleCharts();
    recomputeKPIs();
    renderHero();
    renderTop5();
    showBanner('Data updated · ' + new Date().toLocaleTimeString());
    setStatus('ok', new Date().toLocaleTimeString());
  }} catch {{ setStatus('error', 'error'); }}
  finally {{ document.getElementById('refreshBtn').textContent = '↻'; isReloading = false; }}
}}

function showBanner(text) {{
  const b = document.getElementById('newBanner');
  b.textContent = text;
  b.classList.add('visible');
  setTimeout(() => b.classList.remove('visible'), 5000);
}}

function setStatus(kind, text) {{
  const dot = document.getElementById('connDot');
  dot.className = 'conn-dot conn-' + kind;
  setEl('connText', text);
}}

// ── Init ──────────────────────────────────────────────────
function renderAll() {{
  syncChips();
  recomputeKPIs();
  reloadVisibleCharts();
  writeURL();
}}

bootstrap();
</script>
</body>
</html>
"""


def main():
    print("Loading workouts…")
    workouts = load_all_workouts()
    n_files = len(glob.glob(os.path.join(VAULT_DIR, "*.json")))
    print(f"  → {len(workouts)} workouts from {n_files} snapshots")

    print("Computing stats…")
    stats = compute_stats(workouts)
    kpi = stats["kpi"]
    print(f"  → {kpi['total_workouts']} valid workouts")
    print(f"  → {kpi['total_distance_km']:,} km total")
    print(f"  → {kpi['max_streak_days']} day max streak")
    print(f"  → Types: {stats['types']}")
    print(f"  → Weekday dist sample: {list(stats['weekday_dist'].items())[:3]}")
    print(f"  → Cumulative last: {stats['cumulative_km'][-1] if stats['cumulative_km'] else 'N/A'}")

    print("Generating HTML…")
    html = render_dashboard(stats)
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)
    with open(OUTPUT_DATA, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"✅ index.html: {os.path.getsize(OUTPUT_HTML) / 1024:.1f} KB")
    print(f"✅ data.json:  {os.path.getsize(OUTPUT_DATA) / 1024:.1f} KB")
    print(f"   Dashboard: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
