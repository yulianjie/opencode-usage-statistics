from app.core.data_loader import load_usage_from_db
from app.core.pricing import price_loaded_usage
from app.core.report import build_report_html
from app.core.service import scope_datasets_to_session
from app.core.viewmodels import build_application_viewmodels


def test_load_drops_zero_token_messages(sample_db):
    datasets = load_usage_from_db(sample_db)
    # m4 (user, total=0) dropped -> 4 messages remain
    assert datasets["summary"]["message_count"] == 4
    assert datasets["summary"]["total_tokens"] == 1000 + 500 + 2000 + 300


def test_aggregations(sample_db):
    datasets = load_usage_from_db(sample_db)
    models = {(r["provider"], r["model"]): r for r in datasets["by_model"]}
    assert models[("anthropic", "claude-sonnet-4-6")]["message_count"] == 2
    assert models[("anthropic", "claude-sonnet-4-6")]["total_tokens"] == 1500
    sessions = {r["session_id"]: r for r in datasets["by_session"]}
    assert sessions["ses_a"]["total_tokens"] == 1500
    assert sessions["ses_b"]["total_tokens"] == 2300


def test_pricing_priced_and_unpriced(sample_db):
    priced = price_loaded_usage(load_usage_from_db(sample_db))
    summary = priced["summary"]
    # 3 priced (anthropic x2, openai x1), 1 unpriced (mystery)
    assert summary["priced_message_count"] == 3
    assert summary["unpriced_message_count"] == 1
    # single currency (USD) -> estimated_cost_total is a number
    assert isinstance(summary["estimated_cost_total"], (int, float))
    assert "USD" in summary["estimated_cost_totals"]


def test_sonnet_cost_matches_manual(sample_db):
    priced = price_loaded_usage(load_usage_from_db(sample_db))
    rows = [r for r in priced["raw_messages"] if r["message_id"] == "m1"][0]
    # sonnet-4-6: input 3, output 15, cache_read .3, cache_write 3.75 per million
    expected = (800 / 1e6) * 3 + (200 / 1e6) * 15 + (100 / 1e6) * 0.3 + (50 / 1e6) * 3.75
    assert abs(rows["estimated_cost"] - round(expected, 10)) < 1e-9


def test_scope_to_session(sample_db):
    datasets = load_usage_from_db(sample_db)
    scoped = scope_datasets_to_session(datasets, "ses_a")
    assert scoped["summary"]["message_count"] == 2
    assert scoped["summary"]["total_tokens"] == 1500


def test_scope_to_multiple_sessions_combines(sample_db):
    from app.core.service import scope_datasets_to_sessions

    datasets = load_usage_from_db(sample_db)
    scoped = scope_datasets_to_sessions(datasets, ["ses_a", "ses_b"])
    # combined summary spans both sessions (all 4 token-bearing messages)
    assert scoped["summary"]["message_count"] == 4
    assert scoped["summary"]["total_tokens"] == 1500 + 2300
    # but by_session still breaks them out individually
    assert len(scoped["by_session"]) == 2


def test_scope_to_sessions_ignores_unknown_ids(sample_db):
    from app.core.service import scope_datasets_to_sessions

    datasets = load_usage_from_db(sample_db)
    scoped = scope_datasets_to_sessions(datasets, ["ses_a", "does-not-exist"])
    assert scoped["summary"]["message_count"] == 2
    assert len(scoped["by_session"]) == 1


def test_viewmodels_displays(sample_db):
    priced = price_loaded_usage(load_usage_from_db(sample_db))
    vm = build_application_viewmodels(priced)
    assert vm["overview"]["cards"]["total_tokens_display"].endswith("M")
    assert len(vm["raw_messages"]) == 4
    assert vm["models"][0]["price_status_label"] in ("已定价", "未定价")


def test_report_html_self_contained(sample_db):
    priced = price_loaded_usage(load_usage_from_db(sample_db))
    html = build_report_html(priced, title="测试报告", source_label="x", generated_at="now")
    assert "<canvas id=\"trendChart\"" in html
    assert "Chart" in html  # chart.js inlined
    assert "测试报告" in html
