from app.core.data_loader import aggregate_usage, load_usage_from_db
from app.core.pricing import price_loaded_usage
from app.core.viewmodels import build_application_viewmodels


def load_priced_datasets(db_path):
    """Load full usage from the db and apply pricing overlays."""
    datasets = load_usage_from_db(db_path)
    return price_loaded_usage(datasets)


def scope_datasets_to_sessions(datasets, session_ids):
    """Re-aggregate + re-price using only the given sessions' raw messages.

    Accepts one or many session ids and combines their usage into a single
    set of priced datasets (summary totals span all selected sessions, while
    by_session still breaks them out per conversation).

    `datasets` must be the result of load_usage_from_db / aggregate_usage
    (its raw_messages carry the normalized per-row fields).
    """
    wanted = {sid for sid in session_ids if sid}
    rows = [row for row in datasets.get("raw_messages", []) if row.get("session_id") in wanted]
    re_aggregated = aggregate_usage(rows)
    return price_loaded_usage(re_aggregated)


def scope_datasets_to_session(datasets, session_id):
    """Convenience wrapper: scope to a single session id."""
    return scope_datasets_to_sessions(datasets, [session_id])


def build_payload(db_path, session_ids=None):
    """Return (viewmodels, priced_datasets) for the whole db or selected sessions."""
    base = load_usage_from_db(db_path)
    if session_ids:
        priced = scope_datasets_to_sessions(base, session_ids)
    else:
        priced = price_loaded_usage(base)
    return build_application_viewmodels(priced), priced
