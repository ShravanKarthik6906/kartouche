"""
OpenAI client plumbing shared by the translation stages (translate.py and
overflow_resolve.py). Nothing here decides *what* is sent to the model;
it only controls *how* calls are made:

  * make_client()      - the real client, with a request timeout and
                         automatic retries (exponential backoff, done by the
                         openai library itself on 429/5xx/timeouts).
  * GuardedClient      - runs a check before every call (used for the daily
                         spending cap in public demo mode).
  * CachingClient      - answers repeated, identical prompts from a JSON file
                         instead of the API. Used for the built-in sample so
                         "Try it" costs nothing after the first run.
  * classify_error()   - turns any exception from a call into a stable code
                         plus a plain-language explanation for the UI.

All wrappers expose the same `client.chat.completions.create(...)` surface
as the real client, so the pipeline code doesn't know or care which it has.
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace


DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "90"))
DEFAULT_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "3"))


class MissingAPIKey(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def has_api_key() -> bool:
    """True if an OpenAI key is configured. Never returns or logs the key."""
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def make_client(api_key=None, timeout=None, max_retries=None):
    from openai import OpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise MissingAPIKey("OPENAI_API_KEY is not set")
    return OpenAI(
        api_key=key,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS,
        max_retries=max_retries if max_retries is not None else DEFAULT_MAX_RETRIES,
    )


class _ChatProxy:
    def __init__(self, create):
        self.completions = SimpleNamespace(create=create)


class GuardedClient:
    """Calls `before_call()` before every request; it may raise (e.g. BudgetExceeded)."""

    def __init__(self, inner, before_call):
        self._inner = inner
        self._before_call = before_call
        self.chat = _ChatProxy(self._create)

    def _create(self, **kwargs):
        self._before_call()
        return self._inner.chat.completions.create(**kwargs)


class LazyClient:
    """Builds the real client only when the first call is actually made, so a
    fully cached run works without an API key."""

    def __init__(self, factory):
        self._factory = factory
        self._client = None
        self._lock = threading.Lock()
        self.chat = _ChatProxy(self._create)

    def _create(self, **kwargs):
        with self._lock:
            if self._client is None:
                self._client = self._factory()
        return self._client.chat.completions.create(**kwargs)


def cache_key(messages) -> str:
    """Prompt-only key: the same prompt reuses the same answer whichever model
    produced it, so a cache built locally also serves the deployed site."""
    blob = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CachingClient:
    """
    Serves identical prompts from a JSON cache. Lookups try each path in
    `seed_paths` (read-only, e.g. a cache committed to the repo) and then
    `cache_path` (read/write, written atomically after every new answer).
    Cached answers report no token usage, because they cost nothing.
    """

    def __init__(self, inner, cache_path, seed_paths=()):
        self._inner = inner
        self._path = Path(cache_path)
        self._lock = threading.Lock()
        self._data = {}
        for p in list(seed_paths) + [self._path]:
            p = Path(p)
            if p.exists():
                try:
                    self._data.update(json.loads(p.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    pass  # a damaged cache just means a cache miss
        self.hits = 0
        self.misses = 0
        self.chat = _ChatProxy(self._create)

    def __contains__(self, messages):
        return cache_key(messages) in self._data

    def _create(self, model, messages, **kwargs):
        key = cache_key(messages)
        with self._lock:
            hit = self._data.get(key)
        if hit is not None:
            self.hits += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=hit["content"]))],
                usage=None,
            )
        self.misses += 1
        response = self._inner.chat.completions.create(model=model, messages=messages, **kwargs)
        content = response.choices[0].message.content
        with self._lock:
            self._data[key] = {"content": content, "model": model}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self._path)
        return response


# ------------------------------------------------------------------ errors

# code -> (headline, what to do next). Shown to visitors.
ERROR_MESSAGES = {
    "missing_key": ("Translation isn't set up on this server",
                    "The server has no OpenAI API key configured. If you run this site, set OPENAI_API_KEY "
                    "and restart it."),
    "auth": ("The translation service rejected our credentials",
             "The OpenAI API key configured on this server is invalid or was revoked. If you run this site, "
             "check OPENAI_API_KEY."),
    "quota": ("The translation service is out of credit",
              "The OpenAI account behind this site has run out of credit or hit its spending limit. "
              "Please try again later."),
    "budget": ("Today's translation budget has been used up",
               "This public demo has a daily spending limit, and it has been reached. Please try again tomorrow, "
               "or try the sample lesson, which is free."),
    "rate_limited": ("The translation service is busy",
                     "OpenAI is limiting how fast we can send requests right now. Please try again in a few minutes."),
    "timeout": ("The translation service took too long to respond",
                "Requests to OpenAI kept timing out, even after retrying. Please try again in a few minutes."),
    "connection": ("Couldn't reach the translation service",
                   "The server couldn't connect to OpenAI. Please try again in a few minutes."),
    "model": ("The translation model isn't available",
              "The configured model isn't available to this OpenAI account. If you run this site, check "
              "KARTOUCHE_OPENAI_MODEL."),
    "unknown": ("Something went wrong while translating",
                "An unexpected error occurred. Please try again; if it keeps happening, the technical details "
                "below will help whoever runs this site."),
}

# Errors that will fail every following call too, so the run should stop
# straight away rather than spend minutes repeating them.
FATAL_CODES = {"missing_key", "auth", "quota", "budget", "model", "rate_limited"}


def classify_error(exc) -> str:
    if isinstance(exc, MissingAPIKey):
        return "missing_key"
    if isinstance(exc, BudgetExceeded):
        return "budget"
    try:
        import openai
    except ImportError:  # pragma: no cover
        return "unknown"
    if isinstance(exc, openai.AuthenticationError) or isinstance(exc, openai.PermissionDeniedError):
        return "auth"
    if isinstance(exc, openai.RateLimitError):
        body = getattr(exc, "body", None) or {}
        code = (body.get("code") if isinstance(body, dict) else None) or ""
        text = f"{code} {exc}".lower()
        return "quota" if ("insufficient_quota" in text or "quota" in text or "billing" in text) else "rate_limited"
    if isinstance(exc, openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.APIConnectionError):
        return "connection"
    if isinstance(exc, openai.NotFoundError):
        return "model"
    if isinstance(exc, openai.OpenAIError) and "credentials" in str(exc).lower():
        return "missing_key"
    return "unknown"


def is_fatal(exc) -> bool:
    return classify_error(exc) in FATAL_CODES


class FatalAPIError(RuntimeError):
    """Raised by the pipeline stages to abort a run on an error that would
    repeat on every call (bad key, no credit, budget reached, ...)."""

    def __init__(self, original):
        super().__init__(str(original))
        self.original = original
        self.code = classify_error(original)
