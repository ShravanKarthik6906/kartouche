"""Cost computation, spending cap, rate limiting and the client wrappers."""

import pytest

import limits
import llm
from fake_openai import FakeOpenAI
from state import StateDB


def test_compute_cost_known_model():
    usage = {"model": "gpt-5-mini", "prompt_tokens": 1_000_000, "completion_tokens": 500_000, "calls": 3}
    assert limits.compute_cost(usage) == {"available": True, "model": "gpt-5-mini", "usd": 1.25}


def test_compute_cost_unknown_model_and_no_calls():
    unknown = limits.compute_cost({"model": "mystery", "prompt_tokens": 10, "completion_tokens": 10, "calls": 1})
    assert unknown["available"] is False and "mystery" in unknown["note"]
    assert limits.compute_cost({"model": None, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0})["usd"] == 0


def test_cost_per_call():
    assert limits.cost_usd("gpt-4o", 2000, 1000) == pytest.approx(0.005 + 0.01)
    assert limits.cost_usd("nope", 1, 1) is None


def test_spend_ledger_cap(tmp_path):
    ledger = limits.SpendLedger(StateDB(tmp_path / "s.db"), daily_cap_usd=1.0)
    ledger.add(0.6)
    assert not ledger.cap_reached() and ledger.remaining() == pytest.approx(0.4)
    ledger.add(0.5)
    assert ledger.cap_reached()
    ledger.add(5, day="2000-01-01")  # other days don't count
    assert ledger.spent() == pytest.approx(1.1)
    assert not limits.SpendLedger(ledger.db, 0).cap_reached()  # 0 = no cap


def test_rate_limiter(tmp_path):
    rl = limits.RateLimiter(StateDB(tmp_path / "s.db"))
    t0 = 1_000_000.0
    for i in range(3):
        assert rl.check("1.2.3.4", "upload", 3, now=t0 + i)[0]
        rl.record("1.2.3.4", "upload", now=t0 + i)
    ok, wait = rl.check("1.2.3.4", "upload", 3, now=t0 + 10)
    assert not ok and 3580 < wait <= 3591
    assert rl.check("5.6.7.8", "upload", 3, now=t0 + 10)[0]        # other visitor
    assert rl.check("1.2.3.4", "sample", 3, now=t0 + 10)[0]        # other kind
    assert rl.check("1.2.3.4", "upload", 3, now=t0 + 3601)[0]      # window passed
    assert rl.check("1.2.3.4", "upload", 0, now=t0)[0]             # 0 = unlimited


def chat(client, text):
    return client.chat.completions.create(model="m", messages=[{"role": "system", "content": "x"},
                                                               {"role": "user", "content": text}])


def test_guarded_client_blocks_when_over_budget():
    fake = FakeOpenAI()
    over = {"v": False}

    def check():
        if over["v"]:
            raise llm.BudgetExceeded("cap")
    g = llm.GuardedClient(fake, check)
    chat(g, "a")
    over["v"] = True
    with pytest.raises(llm.BudgetExceeded):
        chat(g, "b")
    assert len(fake.calls) == 1


def test_caching_client_reuses_answers_and_persists(tmp_path):
    fake = FakeOpenAI()
    path = tmp_path / "cache.json"
    c = llm.CachingClient(fake, path)
    first = chat(c, "hello")
    again = chat(c, "hello")
    assert again.choices[0].message.content == first.choices[0].message.content
    assert again.usage is None and len(fake.calls) == 1 and c.hits == 1
    # A new client reading the same file (e.g. after a restart) needs no API at all.
    never = llm.LazyClient(lambda: (_ for _ in ()).throw(AssertionError("should not build a client")))
    c2 = llm.CachingClient(never, tmp_path / "other.json", seed_paths=[path])
    assert chat(c2, "hello").choices[0].message.content == first.choices[0].message.content


def test_error_classification():
    assert llm.classify_error(llm.MissingAPIKey()) == "missing_key"
    assert llm.classify_error(llm.BudgetExceeded()) == "budget"
    assert llm.classify_error(ValueError("x")) == "unknown"
    assert llm.is_fatal(llm.BudgetExceeded()) and not llm.is_fatal(ValueError())
    with pytest.raises(llm.MissingAPIKey):
        llm.make_client(api_key="")
