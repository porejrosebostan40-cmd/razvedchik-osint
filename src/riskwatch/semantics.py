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
PREPARATION_STAGE_TERMS = ("подготов", "список", "списки", "отбор", "учет", "учёт", "медицин", "провер", "поручен", "поручён")
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
    return has_direct_military_action(event)


def safe_stage(event, fallback_stage):
    text = _text(event)
    if safe_root_event(event):
        return 5
    if fallback_stage == 5:
        if any(term in text for term in PREPARATION_STAGE_TERMS):
            return 2
        return 4
    return fallback_stage


# Forecast functions resolve their helper names at call time. Patch the shared
# module once this semantic layer is imported so all production callers use the
# conservative predicates, including direct build_forecast() consumers.
import riskwatch.forecast as _forecast
_forecast._root_event = safe_root_event
_original_stage = _forecast._stage

def _patched_stage(event):
    return safe_stage(event, _original_stage(event))

_forecast._stage = _patched_stage
