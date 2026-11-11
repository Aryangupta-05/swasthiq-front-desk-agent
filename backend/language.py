"""Conservative bilingual extraction. All dates use the explicit reference date."""

import re
from datetime import date, timedelta
from .tools import normalise

TRANSLATIONS = {
    "आज": "aaj",
    "कल": "kal",
    "परसों": "parso",
    "सुबह": "subah",
    "शाम": "shaam",
    "सोमवार": "somwar",
    "मंगलवार": "mangalwar",
    "बुधवार": "budhwar",
    "गुरुवार": "guruwar",
    "शुक्रवार": "shukrawar",
    "शनिवार": "shanivaar",
    "रविवार": "ravivaar",
    "ग्यारह": "gyarah",
    "दस": "das",
    "नौ": "nau",
    "बजे": "baje",
    "नहीं": "nahi",
    "सीने में दर्द": "seene mein dard",
    "सांस": "saans",
    "साँस": "saans",
    "दवाई": "dawai",
    "गोली": "goli",
    "खुराक": "dose",
    "रद्द": "cancel",
}
WEEKDAYS = [
    r"monday|somw?ar",
    r"tuesday|mangalwar",
    r"wednesday|budhw?ar",
    r"thursday|guruwar|brihaspatiwar",
    r"friday|shukrawar",
    r"saturday|shanivaar|shaniwar",
    r"sunday|ravivaar|raviwar",
]


def text(value):
    value = value.lower().translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    for old, new in TRANSLATIONS.items():
        value = value.replace(old, new)
    return value


def corrected(value):
    # A correction supersedes only extraction of scheduling preferences. Safety
    # scans the original text and cannot be erased by saying "ignore that".
    parts = re.split(r"\b(?:nahi nahi|actually|instead|rather|correction|make that)\b", text(value))
    return parts[-1]


def dates(value, today):
    value = corrected(value)
    base = date.fromisoformat(today)
    found = []
    for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", value):
        try:
            found.append((m.start(), date.fromisoformat(m.group()).isoformat()))
        except ValueError:
            found.append((m.start(), "invalid"))
    for m in re.finditer(r"\b(\d{1,2})\s*(?:tareekh|tarikh|date)\b", value):
        try:
            found.append((m.start(), base.replace(day=int(m[1])).isoformat()))
        except ValueError:
            found.append((m.start(), "invalid"))
    month_names = "january february march april may june july august september october november december".split()
    for m in re.finditer(r"\b(\d{1,2})\s+(" + "|".join(month_names) + r")(?:\s+(\d{4}))?\b", value):
        try:
            found.append((m.start(), date(int(m[3] or base.year), month_names.index(m[2]) + 1, int(m[1])).isoformat()))
        except ValueError:
            found.append((m.start(), "invalid"))
    for m in re.finditer(r"\b(day after tomorrow|parso|parson|tomorrow|kal|today|aaj)\b", value):
        offset = 2 if m[0] in ["day after tomorrow", "parso", "parson"] else (0 if m[0] in ["aaj", "today"] else 1)
        found.append((m.start(), (base + timedelta(days=offset)).isoformat()))
    for index, pattern in enumerate(WEEKDAYS):
        for m in re.finditer(r"\b(?:" + pattern + r")\b", value):
            delta = (index - base.weekday()) % 7
            if re.search(r"next\s*$", value[: m.start()]):
                delta = delta or 7
            found.append((m.start(), (base + timedelta(days=delta)).isoformat()))
    return [d for _, d in sorted(found)]


def time_preference(value):
    value = corrected(value)
    window = (
        "morning"
        if re.search(r"\b(subah|morning)\b", value)
        else ("evening" if re.search(r"\b(shaam|sham|evening|afternoon)\b", value) else None)
    )
    words = {
        "ek": 1,
        "do": 2,
        "teen": 3,
        "char": 4,
        "chaar": 4,
        "paanch": 5,
        "chhe": 6,
        "saat": 7,
        "aath": 8,
        "nau": 9,
        "das": 10,
        "gyarah": 11,
        "barah": 12,
    }
    values = []
    pattern = (
        r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm|baje|o.clock)\b|\b(" + "|".join(words) + r")\s+baje\b"
    )
    for m in re.finditer(pattern, value):
        h = int(m[1] or m[4] or words[m[6]])
        minutes = int(m[2] or 0)
        suffix = m[3] or m[5] or ""
        if h > 23 or minutes > 59:
            values.append("invalid")
            continue
        if suffix == "pm" or (window == "evening" and h < 12):
            h = h % 12 + 12
        elif suffix == "am" and h == 12:
            h = 0
        values.append(f"{h:02d}:{minutes:02d}")
    return (values[-1] if values else None), window


def clinical_risk(turns):
    """Administrative triage only, never a diagnosis. Negation is clause-local."""
    for raw in turns:
        value = text(raw)
        for clause in re.split(r"[.!?;]|\b(?:but|lekin|magar)\b", value):
            urgent = re.search(
                r"chest\s+(?:pain|pressure|tight)|seene\s+mein\s+(?:dard|dabav)|saans.*(?:phool|nahi|nahin|mushkil)|(?:cannot|can.t|unable to|struggling to)\s+breathe|breathless|shortness of breath|unconscious|behosh|severe bleeding|face.*droop|slurred speech|blue lips|not breathing",
                clause,
            )
            if urgent:
                # Do not negate "can't breathe". Historic or explicit negative
                # symptoms are not present emergencies, unless symptoms remain.
                negative = re.search(
                    r"\b(?:no|without|denies|not having)\s+(?:any\s+)?(?:chest pain|breathlessness|shortness of breath)|(?:seene mein dard)\s+(?:nahi|nahin)",
                    clause,
                )
                historic = re.search(r"\b(?:last year|years ago|history of)\b", clause) and not re.search(
                    r"\b(?:now|abhi|today|again)\b", clause
                )
                # Another red flag in a clause cannot be negated by "no chest pain".
                other_active = re.search(
                    r"(?:can.t|cannot|unable to) breathe|unconscious|blue lips|not breathing", clause
                )
                if (not negative and not historic) or other_active:
                    return "clinical_urgent"
    combined = text(" ".join(turns))
    if re.search(
        r"\b(?:dose|dosage|diagnos\w*|prescri\w*|medical advice|which medicine|should i take|goli le|kitni goli|dawai|dava|is it cancer|is this serious)\b",
        combined,
    ):
        return "medical_advice"
    return None


def malicious(turns):
    combined = text(" ".join(turns))
    return bool(
        re.search(
            r"ignore\s+(?:your |all |the )?(?:previous |prior )?instructions|administrator mode|system\s*:|<\s*system|developer\s*:|(?:cancel|delete|reschedule)\s+(?:all|every)\s+appointment|(?:dump|export|show)\s+(?:all|every)\s+(?:patient|record)|(?:override|bypass|skip)\s+(?:the )?(?:authorisation|authorization|identity|safety)|(?:execute|run)\s+(?:sql|shell)|drop\s+table",
            combined,
        )
    )


def name_mentions(turns, patients):
    mentions = []
    for index, raw in enumerate(turns):
        value = " " + normalise(text(raw)) + " "
        for p in patients:
            full = normalise(p["name"])
            if " " + full + " " in value:
                mentions.append((index, value.rfind(" " + full + " "), p))
    return sorted(mentions, key=lambda item: (item[0], item[1], -len(item[2]["name"])))
