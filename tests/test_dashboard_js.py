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
