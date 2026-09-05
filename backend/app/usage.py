"""Provider token usage with explicitly labeled USD estimates, never a billing claim."""
from datetime import datetime, timezone
from .database import get_db_connection
from .settings import settings

# Standard paid-tier USD / million tokens; verified 2026-09-04 at
# https://ai.google.dev/gemini-api/docs/pricing . Unknown models remain unpriced.
PRICES = {'gemini-2.5-flash-lite': (0.10, 0.40), 'gemini-2.5-flash': (0.30, 2.50)}


def estimate_cost(model, input_tokens, output_tokens, audio_tokens=0):
    prices = PRICES.get(model)
    if prices is None:
        return None
    audio_rate = 1.0 if model == 'gemini-2.5-flash' else 0.30
    extra_audio = audio_tokens * (audio_rate - prices[0])
    return (input_tokens * prices[0] + output_tokens * prices[1] + extra_audio) / 1_000_000


def quick_request_reserve():
    # Three <=384px stills, prompt/schema allowance, bounded 256-token output.
    return estimate_cost(settings.QUICK_SUMMARY_MODEL, 2000, 256)


def record_usage(reel_id, kind, model, usage):
    if usage is None:
        # An unreported call is unknown, not free; charge the quick estimate for budgeting.
        inputs, outputs = (2000, 256) if kind == 'quick' else (0, 0)
        cost = quick_request_reserve() if kind == 'quick' else None
    else:
        inputs = usage.prompt_token_count or 0
        outputs = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        audio = sum(t.token_count or 0 for t in (usage.prompt_tokens_details or [])
                    if str(t.modality).upper().endswith('AUDIO'))
        cost = estimate_cost(model, inputs, outputs, audio)
    with get_db_connection() as conn:
        conn.execute('INSERT INTO ai_usage (reel_id,kind,model,input_tokens,output_tokens,estimated_cost_usd,created_at) VALUES (?,?,?,?,?,?,?)',
                     (reel_id, kind, model, inputs, outputs, cost, datetime.now(timezone.utc).isoformat()))
        conn.commit()


def usage_summary():
    today = datetime.now(timezone.utc).date().isoformat()
    with get_db_connection() as conn:
        totals = dict(conn.execute('''SELECT COUNT(*) AS requests, COALESCE(SUM(input_tokens),0) AS input_tokens,
            COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(estimated_cost_usd),0) AS estimated_cost_usd,
            SUM(CASE WHEN estimated_cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced_requests FROM ai_usage''').fetchone())
        totals['quick_today_usd'] = conn.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) FROM ai_usage WHERE kind='quick' AND created_at>=?", (today,)).fetchone()[0]
    totals['quick_daily_budget_usd'] = settings.QUICK_SUMMARY_DAILY_BUDGET_USD
    totals['quick_estimate_per_reel_usd'] = quick_request_reserve()
    totals['pricing_date'] = '2026-09-04'
    return totals
