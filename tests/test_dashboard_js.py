import subprocess


APP_JS = "src/polybot/dashboard/static/app.js"


def run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_equity_curve_svg_handles_empty_points():
    script = f"""
const {{ equityCurveSvg }} = require("./{APP_JS}");
const svg = equityCurveSvg([]);
if (svg !== "") {{
  throw new Error(`Expected empty SVG, got: ${{svg}}`);
}}
const nullSvg = equityCurveSvg(null);
if (nullSvg !== "") {{
  throw new Error(`Expected empty SVG for null input, got: ${{nullSvg}}`);
}}
"""

    run_node(script)


def test_equity_curve_svg_renders_single_point_marker_centered():
    script = f"""
const {{ equityCurveSvg }} = require("./{APP_JS}");
const svg = equityCurveSvg([{{ cumulative_pnl: 5 }}]);
if (!svg.includes('class="equity-point"')) {{
  throw new Error(`Missing single point marker: ${{svg}}`);
}}
if (!svg.includes('cx="320.00"')) {{
  throw new Error(`Single point marker should be centered: ${{svg}}`);
}}
if (svg.includes('cx="640.00"') || svg.includes('cy="0.00"') || svg.includes('cy="220.00"')) {{
  throw new Error(`Single point marker should not touch clip edge: ${{svg}}`);
}}
"""

    run_node(script)


def test_equity_curve_svg_handles_negative_single_point_marker():
    script = f"""
const {{ equityCurveSvg }} = require("./{APP_JS}");
const svg = equityCurveSvg([{{ cumulative_pnl: -3 }}]);
if (!svg.includes('class="equity-point"')) {{
  throw new Error(`Missing negative single point marker: ${{svg}}`);
}}
if (!svg.includes('negative-line')) {{
  throw new Error(`Negative single point should use negative line color: ${{svg}}`);
}}
"""

    run_node(script)


def test_equity_curve_svg_renders_multiple_point_path_without_markers():
    script = f"""
const {{ equityCurveSvg }} = require("./{APP_JS}");
const svg = equityCurveSvg([
  {{ cumulative_pnl: -1 }},
  {{ cumulative_pnl: 0 }},
  {{ cumulative_pnl: 2 }},
]);
if (!svg.includes("<path")) {{
  throw new Error(`Missing path for multi-point curve: ${{svg}}`);
}}
if (svg.includes('class="equity-point"')) {{
  throw new Error(`Unexpected point marker for multi-point curve: ${{svg}}`);
}}
if (!svg.includes("M 18.00") || !svg.includes("L 622.00")) {{
  throw new Error(`Path should use padded horizontal coordinates: ${{svg}}`);
}}
"""

    run_node(script)


def test_format_event_countdown_uses_snapshot_time_and_end_time():
    script = f"""
const {{ formatEventCountdown }} = require("./{APP_JS}");
const label = formatEventCountdown(
  "2026-05-14T08:00:00+00:00",
  "2026-05-14T07:59:41+00:00",
);
if (label !== "00:19") {{
  throw new Error(`Expected 00:19, got: ${{label}}`);
}}
const expired = formatEventCountdown(
  "2026-05-14T08:00:00+00:00",
  "2026-05-14T08:00:01+00:00",
);
if (expired !== "00:00") {{
  throw new Error(`Expected expired countdown at 00:00, got: ${{expired}}`);
}}
const missing = formatEventCountdown(null, "2026-05-14T08:00:01+00:00");
if (missing !== "-") {{
  throw new Error(`Expected missing countdown as -, got: ${{missing}}`);
}}
"""

    run_node(script)


def test_format_event_countdown_falls_back_to_browser_clock():
    script = f"""
const {{ formatEventCountdown }} = require("./{APP_JS}");
const originalNow = Date.now;
Date.now = () => Date.parse("2026-05-14T07:59:41+00:00");
const label = formatEventCountdown("2026-05-14T08:00:00+00:00", null);
Date.now = originalNow;
if (label !== "00:19") {{
  throw new Error(`Expected browser-clock fallback at 00:19, got: ${{label}}`);
}}
"""

    run_node(script)
