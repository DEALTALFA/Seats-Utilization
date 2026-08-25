"""Server-rendered landing page: what the service is, plus a live snapshot.

Rendered as a plain string rather than through a template engine: it is one page
with no user-supplied content, so a dependency on Jinja would buy nothing. If a
second page ever appears, that trade flips.
"""

from datetime import date, timedelta
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app import __version__
from app.api.deps import SettingsDep, StoreDep
from app.models import DailyUtilization, DateRange, UtilizationSummary

router = APIRouter()

# Trailing window the snapshot covers, matching the default seeded history.
WINDOW_DAYS = 14

# Chart geometry, in viewBox units. The SVG scales to its container.
VIEW_W, VIEW_H = 760, 240
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 40, 60, 18, 28
PLOT_W = VIEW_W - PAD_LEFT - PAD_RIGHT
PLOT_H = VIEW_H - PAD_TOP - PAD_BOTTOM
BAR_MAX_W = 24  # cap the mark; the band's leftover is air
BAR_RADIUS = 4  # rounded data-end, square at the baseline

ENDPOINTS = (
    ("GET", "/api/v1/seats", "Floor plan; optional <code>floor</code> filter"),
    ("GET", "/api/v1/seats/{seat_id}", "One seat, 404 when unknown"),
    ("POST", "/api/v1/occupancy", "Upsert a single seat-day"),
    ("GET", "/api/v1/utilization", "Aggregate over a date range"),
    ("GET", "/api/v1/utilization/daily", "Same range, one row per day"),
    ("GET", "/health", "Liveness probe"),
)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def homepage(store: StoreDep, settings: SettingsDep) -> HTMLResponse:
    """Landing page: a utilization snapshot over the trailing window."""
    end = date.today()
    period = DateRange(start=end - timedelta(days=WINDOW_DAYS - 1), end=end)
    summary = store.summarize(period)
    daily = store.daily_breakdown(period)
    return HTMLResponse(_page(summary, daily, env=settings.env))


def _page(summary: UtilizationSummary, daily: list[DailyUtilization], env: str) -> str:
    target = summary.target_utilization
    met = summary.meets_target
    status_role = "good" if met else "warning"
    status_text = "Meets target" if met else "Below target"
    status_icon = "✓" if met else "!"
    span = f"{_short_date(summary.start)} &ndash; {_short_date(summary.end)}, {summary.end.year}"
    # `span` is built purely from dates, so it carries an HTML entity unescaped.

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seat Utilization</title>
<style>{_CSS}</style>
</head>
<body>
<main class="viz-root">
  <header class="masthead">
    <div>
      <h1>Seat utilization</h1>
      <p class="lede">Office seat occupancy, reported against a target.</p>
    </div>
    <div class="tags">
      <span class="tag">v{escape(__version__)}</span>
      <span class="tag">{escape(env)}</span>
    </div>
  </header>

  <section class="panel hero-panel">
    <div class="hero">
      <p class="label">Utilization, last {WINDOW_DAYS} days</p>
      <p class="hero-figure">{_pct(summary.utilization_rate, 1)}</p>
      <p class="status status-{status_role}">
        <span class="status-icon" aria-hidden="true">{status_icon}</span>
        {status_text} of {_pct(target, 0)}
      </p>
      <p class="muted">{span}</p>
    </div>
    <div class="tiles">
      {_tile("Seats tracked", f"{summary.seat_count:,}", "3 floors, 3 zones, 8 seats")}
      {_tile("Occupied seat-days", f"{summary.occupied_seat_days:,}", f"of {summary.seat_days:,}")}
      {_tile("Target", _pct(target, 0), "APP_TARGET_UTILIZATION")}
    </div>
  </section>

  <section class="panel">
    <h2>Daily utilization</h2>
    <p class="muted">Share of seats occupied per day. Weekends sit at zero in seeded data.</p>
    {_chart(daily, target)}
    <details>
      <summary>Table view</summary>
      {_table(daily)}
    </details>
  </section>

  <section class="panel">
    <h2>API</h2>
    <table class="routes">
      <tbody>
        {_routes()}
      </tbody>
    </table>
    <p class="links">
      <a href="/docs">Swagger UI</a>
      <a href="/redoc">ReDoc</a>
      <a href="/openapi.json">OpenAPI schema</a>
      <a href="/health">Health</a>
    </p>
  </section>
</main>
</body>
</html>
"""


def _tile(label: str, value: str, note: str) -> str:
    return (
        '<div class="tile">'
        f'<p class="label">{escape(label)}</p>'
        f'<p class="tile-value">{escape(value)}</p>'
        f'<p class="muted">{escape(note)}</p>'
        "</div>"
    )


def _routes() -> str:
    return "\n".join(
        f'<tr><td class="verb">{verb}</td><td><code>{escape(path)}</code></td>'
        f'<td class="muted">{note}</td></tr>'
        for verb, path, note in ENDPOINTS
    )


def _chart(daily: list[DailyUtilization], target: float) -> str:
    """A single-series column chart: one column per day, plus a target line."""
    if not daily:
        return '<p class="muted">No days in range.</p>'

    band = PLOT_W / len(daily)
    bar_w = min(BAR_MAX_W, band - 2)  # 2px surface gap between adjacent bars
    baseline = PAD_TOP + PLOT_H

    gridlines = "".join(
        f'<line class="grid" x1="{PAD_LEFT}" x2="{PAD_LEFT + PLOT_W}" '
        f'y1="{_y(frac):.1f}" y2="{_y(frac):.1f}" />'
        f'<text class="tick" x="{PAD_LEFT - 8}" y="{_y(frac) + 4:.1f}" '
        f'text-anchor="end">{_pct(frac, 0)}</text>'
        for frac in (0.0, 0.5, 1.0)
    )

    bars = []
    for index, row in enumerate(daily):
        centre = PAD_LEFT + band * (index + 0.5)
        height = min(row.utilization_rate, 1.0) * PLOT_H
        label = f"{_short_date(row.day)} · {_pct(row.utilization_rate, 0)}"
        detail = f"{row.occupied} of {row.seat_count} seats"
        bars.append(
            f'<g class="bar"><title>{escape(label)} — {escape(detail)}</title>'
            f'<rect class="hit" x="{centre - band / 2:.1f}" y="{PAD_TOP}" '
            f'width="{band:.1f}" height="{PLOT_H}" />'
            f'<path class="mark" d="{_bar_path(centre - bar_w / 2, baseline, bar_w, height)}" />'
            "</g>"
            f'<text class="tick" x="{centre:.1f}" y="{baseline + 18}" '
            f'text-anchor="middle">{row.day.day}</text>'
        )

    # Direct-label the latest column only; the tooltip and table carry the rest.
    last = daily[-1]
    last_centre = PAD_LEFT + band * (len(daily) - 0.5)
    last_top = baseline - min(last.utilization_rate, 1.0) * PLOT_H
    cap_label = (
        f'<text class="cap" x="{last_centre:.1f}" y="{last_top - 7:.1f}" '
        f'text-anchor="middle">{_pct(last.utilization_rate, 0)}</text>'
    )

    target_y = _y(min(target, 1.0))
    target_line = (
        f'<line class="target" x1="{PAD_LEFT}" x2="{PAD_LEFT + PLOT_W}" '
        f'y1="{target_y:.1f}" y2="{target_y:.1f}" />'
        f'<text class="target-label" x="{PAD_LEFT + PLOT_W + 8}" y="{target_y + 4:.1f}">'
        f"Target {_pct(target, 0)}</text>"
    )

    return (
        f'<svg class="chart" viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" '
        f'aria-label="Daily seat utilization for the last {len(daily)} days">'
        f"{gridlines}{''.join(bars)}{cap_label}{target_line}"
        f'<line class="axis" x1="{PAD_LEFT}" x2="{PAD_LEFT + PLOT_W}" '
        f'y1="{baseline}" y2="{baseline}" /></svg>'
    )


def _table(daily: list[DailyUtilization]) -> str:
    rows = "\n".join(
        f"<tr><td>{row.day.isoformat()}</td><td>{row.occupied}</td>"
        f"<td>{row.seat_count}</td><td>{_pct(row.utilization_rate, 1)}</td></tr>"
        for row in daily
    )
    return (
        '<table class="data"><thead><tr><th>Day</th><th>Occupied</th>'
        f"<th>Seats</th><th>Rate</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _bar_path(x: float, baseline: float, width: float, height: float) -> str:
    """Column with a rounded cap and square feet, grown from the baseline."""
    if height <= 0:
        return ""
    radius = min(BAR_RADIUS, height, width / 2)
    top = baseline - height
    return (
        f"M{x:.1f} {baseline:.1f} V{top + radius:.1f} "
        f"Q{x:.1f} {top:.1f} {x + radius:.1f} {top:.1f} "
        f"H{x + width - radius:.1f} "
        f"Q{x + width:.1f} {top:.1f} {x + width:.1f} {top + radius:.1f} "
        f"V{baseline:.1f} Z"
    )


def _y(fraction: float) -> float:
    return PAD_TOP + PLOT_H * (1 - fraction)


def _pct(fraction: float, places: int) -> str:
    return f"{fraction * 100:.{places}f}%"


def _short_date(day: date) -> str:
    return f"{day:%b} {day.day}"


_CSS = """
.viz-root {
  color-scheme: light;
  --plane: #f9f9f7;
  --surface: #fcfcfb;
  --ink: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11, 11, 11, 0.1);
  --series: #2a78d6;
  --good: #0ca30c;
  --warning: #fab219;
}
@media (prefers-color-scheme: dark) {
  .viz-root {
    color-scheme: dark;
    --plane: #0d0d0d;
    --surface: #1a1a19;
    --ink: #ffffff;
    --ink-secondary: #c3c2b7;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255, 255, 255, 0.1);
    --series: #3987e5;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--plane);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink);
}
.viz-root { max-width: 900px; margin: 0 auto; padding: 40px 24px 64px; }
.masthead {
  display: flex; flex-wrap: wrap; gap: 12px;
  align-items: baseline; justify-content: space-between; margin-bottom: 24px;
}
h1 { margin: 0; font-size: 24px; letter-spacing: -0.01em; }
h2 { margin: 0 0 4px; font-size: 15px; }
.lede { margin: 4px 0 0; color: var(--ink-secondary); }
.tags { display: flex; gap: 8px; }
.tag {
  padding: 2px 10px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--surface); color: var(--ink-secondary); font-size: 12px;
}
.panel {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 16px;
}
.hero-panel { display: flex; flex-wrap: wrap; gap: 32px; justify-content: space-between; }
.label {
  margin: 0; font-size: 12px; font-weight: 600; color: var(--ink-secondary);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.hero-figure { margin: 6px 0 2px; font-size: 56px; font-weight: 600; line-height: 1; }
.muted { margin: 2px 0 0; color: var(--ink-muted); font-size: 13px; }
.status { display: flex; align-items: center; gap: 6px; margin: 8px 0 0; font-size: 13px; }
.status-icon {
  display: grid; place-items: center; width: 16px; height: 16px;
  border-radius: 50%; color: #0b0b0b; font-size: 11px; font-weight: 700;
}
.status-good .status-icon { background: var(--good); }
.status-warning .status-icon { background: var(--warning); }
.tiles { display: flex; flex-wrap: wrap; gap: 28px; align-content: center; }
.tile-value { margin: 6px 0 0; font-size: 24px; font-weight: 600; line-height: 1; }
.chart { display: block; width: 100%; height: auto; margin: 12px 0 4px; overflow: visible; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.target { stroke: var(--ink-secondary); stroke-width: 1; }
.mark { fill: var(--series); }
.hit { fill: transparent; }
.bar:hover .mark { fill-opacity: 0.82; }
.tick, .target-label {
  fill: var(--ink-muted); font-size: 11px; font-variant-numeric: tabular-nums;
}
.cap { fill: var(--ink-secondary); font-size: 11px; font-weight: 600; }
details { margin-top: 12px; font-size: 13px; }
summary { color: var(--ink-secondary); cursor: pointer; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
.data { margin-top: 12px; font-variant-numeric: tabular-nums; }
.data th, .data td, .routes td {
  padding: 6px 10px 6px 0; border-bottom: 1px solid var(--border); text-align: left;
}
.data th { color: var(--ink-secondary); font-weight: 600; }
.routes tr:last-child td { border-bottom: 0; }
.verb {
  color: var(--ink-muted); font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
  white-space: nowrap;
}
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
.links { display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0 0; font-size: 13px; }
a { color: var(--series); }
"""
