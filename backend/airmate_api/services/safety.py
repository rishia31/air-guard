"""Safety rules that sit outside the language model.

* Red flags (inhaler not helping, can't finish sentences, blue lips, ...) stop the
  conversation: Airmate tells the person to call 911, alerts their buddy, and
  shares their location. Detection is deterministic so it cannot be talked out of.
* Airmate only repeats medicines and doses that are written in the person's own
  action plan. Any generated text that mentions a dose the plan does not contain
  is rejected and replaced by a template.
"""

from __future__ import annotations

import re

_NOT = r"(?:not|n't|no longer|never)"
RED_FLAGS: dict[str, list[str]] = {
    "inhaler_not_helping": [
        rf"\b(?:inhaler|albuterol|puffer|rescue med\w*|nebuli[sz]er)\b[^.?!]{{0,40}}\b(?:is|was|does|did|has|have|it'?s)?\s*{_NOT}\s*(?:help\w*|work\w*|do\w* anything)",
        r"\b(?:inhaler|albuterol|puffer)\b[^.?!]{0,30}\b(?:stopped|isn'?t|wasn'?t|doesn'?t|didn'?t|won'?t)\s*(?:help\w*|work\w*)",
        r"\bpuffs? (?:are not|aren'?t|is not|isn'?t|did not|didn'?t|do not|don'?t) (?:help\w*|work\w*)\b",
        r"\b(?:took|used|had)\b[^.?!]{0,30}\b(?:puffs?|inhaler)\b[^.?!]{0,30}\b(?:still|and it'?s still|but still)\b[^.?!]{0,20}\b(?:can'?t|cannot|hard to|struggling)",
    ],
    "cant_speak": [
        r"\b(?:can'?t|cannot|can not|unable to|hard to|struggling to)\s+(?:finish|complete|get out|say)\s+(?:a |my |full |whole )*(?:sentences?|words?)",
        r"\b(?:can'?t|cannot|can not|unable to)\s+(?:talk|speak)\b",
        r"\btoo (?:breathless|short of breath|out of breath) to (?:talk|speak|walk|eat)\b",
    ],
    "blue_lips": [
        r"\b(?:blue|bluish|gr[ae]y|purple|pale blue)\s+(?:lips?|fingernails?|nails|fingers?|face|mouth)\b",
        r"\b(?:lips?|fingernails?|nails|fingers?|face)\b[^.?!]{0,20}\b(?:blue|bluish|gr[ae]y|purple)\b",
    ],
    "cant_breathe": [
        r"\b(?:can'?t|cannot|can not|unable to)\s+(?:breathe|catch (?:my|his|her|their) breath|get (?:any )?air)\b",
        r"\b(?:struggling|fighting|gasping) (?:to breathe|for (?:air|breath))\b",
        r"\b(?:ribs|chest|neck|skin)\b[^.?!]{0,25}\b(?:sucking|pulling|caving) in\b",
        r"\bpeak flow\b[^.?!]{0,25}\b(?:below|under|less than)\s+(?:50|half)\b",
    ],
    "consciousness": [
        r"\b(?:passing out|passed out|fainting|fainted|can'?t stay awake|very (?:drowsy|confused)|confused and)\b",
    ],
}
RED_FLAG_LABELS = {
    "inhaler_not_helping": "rescue inhaler is not helping",
    "cant_speak": "too breathless to speak in full sentences",
    "blue_lips": "blue or gray lips or fingernails",
    "cant_breathe": "severe trouble breathing",
    "consciousness": "fainting, confusion, or extreme drowsiness",
}
_COMPILED = {key: [re.compile(p, re.IGNORECASE) for p in patterns] for key, patterns in RED_FLAGS.items()}
_NEGATED_CONTEXT = re.compile(r"\b(?:no|not|never|without|isn'?t|aren'?t)\b[^.?!]{0,12}$", re.IGNORECASE)


def detect_red_flags(text: str) -> list[str]:
    """Keys of the red flags present in ``text`` (empty when there are none)."""
    if not text:
        return []
    text = text.replace("’", "'")
    found = []
    for key, patterns in _COMPILED.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match and not (key == "blue_lips" and _NEGATED_CONTEXT.search(text[: match.start()])):
                found.append(key)
                break
    return found


def emergency_script(first_name: str, buddy_name: str | None, red_zone: str | None) -> str:
    """The exact words Airmate says when a red flag fires. Spoken verbatim, never generated."""
    lines = [f"{first_name}, this could be a serious asthma attack. Call 9 1 1 now."]
    if buddy_name:
        lines.append(f"I'm alerting {buddy_name} and sharing your location.")
    else:
        lines.append("I'm sharing your location with your emergency contact.")
    if red_zone:
        lines.append(f"Your action plan says: {red_zone.strip().rstrip('.')}.")
    lines.append("Sit upright, stay calm, and keep your phone with you.")
    return " ".join(lines)


_DOSE = re.compile(
    r"\b(\d+(?:\.\d+)?)(?:\s*(?:to|-|–|or)\s*(\d+(?:\.\d+)?))?\s*"
    r"(puffs?|inhalations?|mg|mcg|µg|micrograms?|milligrams?|ml|tablets?|pills?|sprays?|doses?|nebuli[sz]ers?|vials?)\b",
    re.IGNORECASE,
)
_INTERVAL = re.compile(r"\bevery\s+(\d+(?:\.\d+)?)(?:\s*(?:to|-|–)\s*(\d+(?:\.\d+)?))?\s*(hours?|hrs?|minutes?|mins?)\b",
                       re.IGNORECASE)
_WORD_NUMBERS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "eight": "8", "ten": "10",
                 "twenty": "20"}


def _normalize(text: str) -> str:
    text = text.lower().replace("–", "-")
    return re.sub(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", lambda m: _WORD_NUMBERS[m.group(1)], text)


def _unit(u: str) -> str:
    u = u.lower().rstrip("s")
    return {"inhalation": "puff", "microgram": "mcg", "µg": "mcg", "milligram": "mg", "hr": "hour", "min": "minute"}.get(u, u)


def _claims(text: str) -> set[tuple[str, str]]:
    text = _normalize(text)
    claims = set()
    for m in _DOSE.finditer(text):
        claims.add((m.group(1), _unit(m.group(3))))
        if m.group(2):
            claims.add((m.group(2), _unit(m.group(3))))
    for m in _INTERVAL.finditer(text):
        claims.add((m.group(1), "every-" + _unit(m.group(3))))
        if m.group(2):
            claims.add((m.group(2), "every-" + _unit(m.group(3))))
    return claims


def invented_doses(generated: str, action_plan_text: str) -> list[str]:
    """Dose or interval claims in ``generated`` that the action plan does not contain."""
    allowed = _claims(action_plan_text)
    return sorted(f"{n} {u}" for n, u in _claims(generated) - allowed)


def plan_text(plan: dict | None) -> str:
    """Flatten an action plan (green/yellow/red zones) into plain text."""
    if not plan:
        return ""
    parts = []
    for zone in ("green", "yellow", "red"):
        z = plan.get(zone) or {}
        if isinstance(z, str):
            parts.append(f"{zone}: {z}")
            continue
        parts.append(f"{zone.title()} zone ({z.get('when', '')}): " + " ".join(z.get("do", [])))
    for key in ("controller", "rescue", "notes"):
        if plan.get(key):
            parts.append(f"{key}: {plan[key]}")
    return "\n".join(parts)


def zone_steps(plan: dict | None, zone: str) -> str:
    z = (plan or {}).get(zone) or {}
    if isinstance(z, str):
        return z
    return " ".join(z.get("do", []))
