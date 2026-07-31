"""
Prompt rendering.

An LLM prompt is data that happens to contain other people's syntax. Ours
document JSON shapes to the model ({"available": false}) and quote money
($3.84), so the two obvious ways to fill in a template are both traps:

    str.format()      — reads {"available": false} as a replacement field and
                        dies with KeyError('"available"')
    string.Template   — reads $3.84 as a placeholder and dies with ValueError

Both failures are indistinguishable from "the model had a bad day" at the call
site, which is how one of them survived in production: every synthesis fell
back to plain markdown and nothing looked broken.

So placeholders here use a delimiter that cannot occur in JSON, in prose, or
in a price: <<name>>. Nothing else in the template is special, ever.

Substitution is strict in both directions. A placeholder with no value raises,
and a value with no placeholder raises — the second catches the rename that
would otherwise leave a stale <<token>> in the text sent to the model.
"""
from __future__ import annotations

import re
from typing import Any

# <<name>> — optional inner spacing, identifier only.
_TOKEN = re.compile(r"<<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>>")


class PromptError(ValueError):
    """A template and its values do not agree."""


def placeholders(template: str) -> set[str]:
    """Names the template expects."""
    return set(_TOKEN.findall(template))


def render(template: str, /, **values: Any) -> str:
    """Fill <<name>> placeholders. Raises rather than shipping a broken prompt.

    >>> render("hola <<who>>, {\\"json\\": true} y $3.84", who="mundo")
    'hola mundo, {"json": true} y $3.84'
    """
    expected = placeholders(template)
    given = set(values)

    missing = expected - given
    if missing:
        raise PromptError(
            f"template expects {sorted(missing)} but no value was given"
        )

    extra = given - expected
    if extra:
        raise PromptError(
            f"values {sorted(extra)} have no placeholder — renamed or removed "
            f"in the template?"
        )

    out = _TOKEN.sub(lambda m: str(values[m.group(1)]), template)

    # Belt and braces: a malformed token (<<a b>>) is not matched above and
    # would otherwise reach the model verbatim.
    if "<<" in out and _TOKEN.search(template) is not None:
        stray = re.search(r"<<[^>]{0,40}>>", out)
        if stray:
            raise PromptError(f"unsubstituted placeholder left in prompt: {stray.group(0)!r}")

    return out
