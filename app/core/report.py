import html
import json
from pathlib import Path

from app.core.viewmodels import (
    build_application_viewmodels,
    format_token_millions,
    _format_cost,
    _format_cost_totals,
)

CHART_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "chart.umd.min.js"


def _esc(value):
    return html.escape("" if value is None else str(value))


def _chart_js_source():
    try:
        return CHART_JS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _cards_block(cards):
    items = [
        ("总消息数", cards.get("message_count", 0)),
        ("总 Token", cards.get("total_tokens_display", "")),
        ("输入 Token", cards.get("input_tokens_display", "")),
        ("输出 Token", cards.get("output_tokens_display", "")),
        ("推理 Token", cards.get("reasoning_tokens_display", "")),
        ("缓存读取", cards.get("cache_read_display", "")),
        ("缓存写入", cards.get("cache_write_display", "")),
        ("预估成本", cards.get("estimated_cost_total_display", "") or "—"),
        ("已记录成本", cards.get("recorded_cost_total_display", "") or "—"),
        ("已定价/未定价", f"{cards.get('priced_message_count', 0)} / {cards.get('unpriced_message_count', 0)}"),
    ]
    cells = "".join(
        f'<div class="card"><div class="card-label">{_esc(label)}</div>'
        f'<div class="card-value">{_esc(value)}</div></div>'
        for label, value in items
    )
    return f'<div class="cards">{cells}</div>'


def _table(headers, rows):
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
    if not rows:
        body = f'<tr><td colspan="{len(headers)}" class="empty">无数据</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _model_rows(models):
    return [
        [
            r.get("provider", ""),
            r.get("model", ""),
            r.get("message_count", 0),
            r.get("total_tokens_display", ""),
            r.get("input_tokens_display", ""),
            r.get("output_tokens_display", ""),
            r.get("estimated_cost_display", "") or "—",
            r.get("price_status_label", ""),
        ]
        for r in models
    ]


def _day_rows(days):
    return [
        [
            r.get("day", ""),
            r.get("message_count", 0),
            r.get("total_tokens_display", ""),
            r.get("input_tokens_display", ""),
            r.get("output_tokens_display", ""),
            r.get("estimated_cost_display", "") or "—",
        ]
        for r in days
    ]


def _session_rows(sessions):
    return [
        [
            r.get("session_title", "") or r.get("session_id", ""),
            r.get("message_count", 0),
            r.get("total_tokens_display", ""),
            r.get("estimated_cost_display", "") or "—",
            r.get("price_status_label", ""),
        ]
        for r in sessions
    ]


def build_report_html(priced_datasets, *, title="OpenCode Token 使用分析报告", source_label="", generated_at=""):
    vm = build_application_viewmodels(priced_datasets)
    overview = vm["overview"]
    cards = overview["cards"]
    models = vm["models"]
    days = vm["days"]
    sessions = vm["sessions"]

    # chart data (oldest -> newest for trend)
    day_trend = sorted(days, key=lambda r: r.get("day", "") or "")
    trend_labels = [r.get("day", "") for r in day_trend]
    trend_total = [r.get("total_tokens", 0) for r in day_trend]
    trend_input = [r.get("input_tokens", 0) for r in day_trend]
    trend_output = [r.get("output_tokens", 0) for r in day_trend]

    top_models = models[:10]
    model_labels = [f"{r.get('provider','')}:{r.get('model','')}" for r in top_models]
    model_totals = [r.get("total_tokens", 0) for r in top_models]

    chart_data = {
        "trendLabels": trend_labels,
        "trendTotal": trend_total,
        "trendInput": trend_input,
        "trendOutput": trend_output,
        "modelLabels": model_labels,
        "modelTotals": model_totals,
    }

    cost_totals_line = _format_cost_totals(
        cards.get("estimated_cost_totals"), cards.get("estimated_cost_total")
    ) or "—"

    chart_js = _chart_js_source()
    data_json = json.dumps(chart_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", "Segoe UI", system-ui, sans-serif; margin: 0; background: #f5f6fa; color: #1f2430; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }}
  header h1 {{ margin: 0 0 6px; font-size: 24px; }}
  header .meta {{ color: #6b7280; font-size: 13px; }}
  h2 {{ font-size: 17px; margin: 36px 0 12px; border-left: 4px solid #4f46e5; padding-left: 10px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; }}
  .card-label {{ color: #6b7280; font-size: 12px; }}
  .card-value {{ font-size: 20px; font-weight: 600; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; font-size: 13px; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #eef0f4; }}
  th {{ background: #f0f1f6; font-weight: 600; }}
  td.empty {{ text-align: center; color: #9ca3af; padding: 18px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .chart-box {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; }}
  .chart-box.full {{ grid-column: 1 / -1; }}
  .cost-line {{ font-size: 15px; font-weight: 600; color: #4f46e5; }}
  @media (max-width: 760px) {{ .charts {{ grid-template-columns: 1fr; }} }}
  @media print {{ body {{ background: #fff; }} .chart-box, .card, table {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{_esc(title)}</h1>
    <div class="meta">数据来源：{_esc(source_label or "—")} ｜ 生成时间：{_esc(generated_at or "—")}</div>
  </header>

  <h2>总览</h2>
  {_cards_block(cards)}
  <p class="cost-line" style="margin-top:14px;">预估成本合计：{_esc(cost_totals_line)}</p>

  <h2>图表</h2>
  <div class="charts">
    <div class="chart-box full"><canvas id="trendChart" height="120"></canvas></div>
    <div class="chart-box"><canvas id="modelBarChart" height="220"></canvas></div>
    <div class="chart-box"><canvas id="modelPieChart" height="220"></canvas></div>
  </div>

  <h2>按模型</h2>
  {_table(["Provider", "模型", "消息数", "总Token", "输入", "输出", "预估成本", "定价"], _model_rows(models))}

  <h2>按日期</h2>
  {_table(["日期", "消息数", "总Token", "输入", "输出", "预估成本"], _day_rows(days))}

  <h2>按会话</h2>
  {_table(["会话", "消息数", "总Token", "预估成本", "定价"], _session_rows(sessions))}
</div>

<script>{chart_js}</script>
<script>
const D = {data_json};
function build() {{
  if (typeof Chart === "undefined") return;
  Chart.defaults.font.family = '"Microsoft YaHei","Segoe UI",sans-serif';
  new Chart(document.getElementById("trendChart"), {{
    type: "line",
    data: {{ labels: D.trendLabels, datasets: [
      {{ label: "总 token", data: D.trendTotal, borderColor: "#4F46E5", backgroundColor: "rgba(79,70,229,.1)", tension: .25, fill: true }},
      {{ label: "输入", data: D.trendInput, borderColor: "#10B981", tension: .25 }},
      {{ label: "输出", data: D.trendOutput, borderColor: "#F59E0B", tension: .25 }}
    ] }},
    options: {{ responsive: true, plugins: {{ title: {{ display: true, text: "每日 Token 趋势" }} }} }}
  }});
  new Chart(document.getElementById("modelBarChart"), {{
    type: "bar",
    data: {{ labels: D.modelLabels, datasets: [{{ label: "总 token", data: D.modelTotals, backgroundColor: "#4F46E5" }}] }},
    options: {{ indexAxis: "y", responsive: true, plugins: {{ title: {{ display: true, text: "模型 Token (Top 10)" }}, legend: {{ display: false }} }} }}
  }});
  new Chart(document.getElementById("modelPieChart"), {{
    type: "pie",
    data: {{ labels: D.modelLabels, datasets: [{{ data: D.modelTotals }}] }},
    options: {{ responsive: true, plugins: {{ title: {{ display: true, text: "模型 Token 占比" }} }} }}
  }});
}}
build();
</script>
</body>
</html>"""
