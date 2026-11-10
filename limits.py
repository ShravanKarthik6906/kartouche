"""
Cost accounting and the public-demo safety limits.

  * compute_cost(usage)        - dollars for a token-usage summary.
  * SpendLedger                - running total of real API spend per UTC day,
                                 persisted, with the daily cap check.
  * RateLimiter                - N actions per visitor per rolling hour.

The ledger is the basis of the daily spending cap: every real API call adds
its cost as soon as the response arrives, and in public mode a guard checks
the cap before every call (llm.GuardedClient), so a run stops within one
call of the cap. The cap is a safety net, not a billing system: also set a
hard monthly budget in the OpenAI dashboard.
"""

import time
from datetime import datetime, timezone

# USD per 1,000,000 tokens. Verify against https://openai.com/api/pricing/
# before relying on a figure here. Models without an entry have no dollar
# figure, and public demo mode refuses to spend on a model it can't price.
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},  # verified vs OpenAI pricing page, early Sep 2026
}


def price_for(model):
    return PRICING.get(model)


def cost_usd(model, prompt_tokens, completion_tokens):
    """Dollar cost of one call, or None if the model has no configured pricing."""
    pricing = price_for(model)
    if not pricing:
        return None
    return (prompt_tokens / 1e6) * pricing["input"] + (completion_tokens / 1e6) * pricing["output"]


def compute_cost(usage):
    """usage: {"model", "prompt_tokens", "completion_tokens", ...} accumulated over a job."""
    model = usage.get("model")
    if not usage.get("calls"):
        return {"available": True, "model": model, "usd": 0.0}
    pricing = price_for(model)
    if not pricing:
        return {
            "available": False,
            "model": model,
            "note": f"No pricing is configured for model '{model}', so the cost can't be shown. "
                    f"Token counts are exact.",
        }
    usd = cost_usd(model, usage["prompt_tokens"], usage["completion_tokens"])
    return {"available": True, "model": model, "usd": round(usd, 4)}


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SpendLedger:
    def __init__(self, db, daily_cap_usd=0.0):
        self.db = db
        self.daily_cap_usd = daily_cap_usd

    def add(self, usd, day=None):
        if not usd:
            return
        self.db.execute(
            "INSERT INTO spend (day, usd) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd",
            (day or _today(), float(usd)),
        )

    def spent(self, day=None):
        rows = self.db.query("SELECT usd FROM spend WHERE day = ?", (day or _today(),))
        return rows[0]["usd"] if rows else 0.0

    def cap_enabled(self):
        return self.daily_cap_usd > 0

    def cap_reached(self):
        return self.cap_enabled() and self.spent() >= self.daily_cap_usd

    def remaining(self):
        return max(0.0, self.daily_cap_usd - self.spent()) if self.cap_enabled() else None


class RateLimiter:
    WINDOW_SECONDS = 3600

    def __init__(self, db):
        self.db = db

    def check(self, visitor, kind, limit, now=None):
        """(allowed, seconds_until_next_slot). limit <= 0 means unlimited."""
        if limit <= 0:
            return True, 0
        now = now or time.time()
        since = now - self.WINDOW_SECONDS
        rows = self.db.query(
            "SELECT ts FROM rate_events WHERE visitor = ? AND kind = ? AND ts > ? ORDER BY ts",
            (visitor, kind, since),
        )
        if len(rows) < limit:
            return True, 0
        oldest = rows[len(rows) - limit]["ts"]
        return False, int(oldest + self.WINDOW_SECONDS - now) + 1

    def record(self, visitor, kind, now=None):
        now = now or time.time()
        self.db.execute("INSERT INTO rate_events (visitor, kind, ts) VALUES (?, ?, ?)", (visitor, kind, now))
        self.db.execute("DELETE FROM rate_events WHERE ts < ?", (now - 2 * self.WINDOW_SECONDS,))
