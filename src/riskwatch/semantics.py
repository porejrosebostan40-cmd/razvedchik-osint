import re

from .forecast import ACTION_TERMS, NEGATIVE_TERMS, TARGET_TERMS, _text

MILITARY_ANCHORS = (
    "мобилиз", "военн", "военком", "военнослуж", "арм", "сво", "вооружен", "вооружён",
    "министерств оборон", "минобороны", "вооруженные силы", "вооружённые силы"
)
DIRECT_ACTION_TERMS = (
    "привлеч", "зачислен", "зачислён", "направлен", "отправлен", "отправл", "призван",
    "заключил контракт", "заключен контракт", "заключён контракт", "начал службу", "службу"
)
NEGATION_RE = re.compile(r"\bне\s+(?:будут|будет|стал|стали|станут|привлеч|зачислен|зачислён|направлен|отправлен|призван|мобилиз)")


def has_target(event):
    text = _text(event)
    return any(term in text for term in TARGET_TERMS)


def is_negative(event):
    text = _text(event)
    return any(term in text for term in NEGATIVE_TERMS) or bool(NEGATION_RE.search(text))


def has_military_anchor(event):
    text = _text(event)
    return any(term in text for term in MILITARY_ANCHORS)


def has_direct_military_action(event):
    text = _text(event)
    return has_target(event) and has_military_anchor(event) and any(term in text for term in DIRECT_ACTION_TERMS) and not is_negative(event)


def safe_root_event(event):
    """Conservative root predicate: target + explicit military context + direct action, not a denial."""
    return has_direct_military_action(event)


def safe_stage(event, fallback_stage):
    if safe_root_event(event):
        return 5
    if has_target(event) and has_military_anchor(event) and not is_negative(event):
        text = _text(event)
        if any(term in text for term in ACTION_TERMS):
            return max(3, min(4, fallback_stage))
    if fallback_stage == 5:
        return 4
    return fallback_stage
