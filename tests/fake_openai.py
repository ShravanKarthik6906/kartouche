"""
A stand-in for the OpenAI client, so the pipeline can be tested end to end
without an API key or any spending.

It answers the two kinds of prompts Rosetta sends:
  * translation (translate.call_openai_translate): keeps every <tN> tag and
    replaces the text inside it with a deterministic pseudo-translation;
  * shorten-for-layout (overflow.retranslate_shorter): returns a shorter
    version of the current translation.

Pseudo-translations make text longer (like real Spanish/French/German/
Portuguese usually is), and for Arabic map Latin letters onto Arabic ones
so right-to-left handling and Arabic font measurement are exercised.
"""

import re
from types import SimpleNamespace

TAG_RE = re.compile(r"<t(\d+)>(.*?)</t\1>", re.DOTALL)

ARABIC = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"

EXPANSION = {"Spanish": 1.3, "French": 1.3, "German": 1.35, "Brazilian Portuguese": 1.25, "Portuguese": 1.25}


def pseudo_translate(text, lang_name):
    if lang_name == "Arabic":
        out = []
        for ch in text:
            if ch.isascii() and ch.isalpha():
                out.append(ARABIC[(ord(ch.lower()) - 97) % len(ARABIC)])
            else:
                out.append(ch)
        return "".join(out)
    factor = EXPANSION.get(lang_name, 1.3)
    words = text.split(" ")
    extra = max(0, round(len(text) * factor) - len(text))
    marker = {"Spanish": "ñ", "French": "é", "German": "ß", "Brazilian Portuguese": "ã",
              "Portuguese": "ã"}.get(lang_name, "x")
    if extra and words:
        # lengthen the longest word, so wrapping still happens at spaces
        longest = max(range(len(words)), key=lambda i: len(words[i]))
        words[longest] = words[longest] + marker * extra
    return " ".join(words)


class _Completions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, model, messages, **kwargs):
        system = messages[0]["content"]
        user = messages[-1]["content"]
        self.owner.calls.append({"model": model, "messages": messages})
        if self.owner.fail_with is not None:
            raise self.owner.fail_with
        m = re.search(r"from English into (.+?)\. ", system)
        if m:
            lang = m.group(1)
            body = user.split("\n", 1)[1] if user.startswith("[Context:") else user
            content = TAG_RE.sub(lambda mm: f"<t{mm.group(1)}>{pseudo_translate(mm.group(2), lang)}</t{mm.group(1)}>", body)
        else:
            current = user.split("translation (too wide): ", 1)[-1]
            content = current[: max(1, len(current) * 6 // 10)].rstrip()
        usage = SimpleNamespace(prompt_tokens=len(system + user) // 4, completion_tokens=len(content) // 4)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


class FakeOpenAI:
    """Drop-in for openai.OpenAI(...) in tests. Records every call in .calls."""

    def __init__(self, *args, fail_with=None, **kwargs):
        self.calls = []
        self.fail_with = fail_with
        self.chat = SimpleNamespace(completions=_Completions(self))
