from .forecast import ACTION_TERMS, MILITARY_ANCHORS, NEGATIVE_TERMS, TARGET_TERMS, _has_direct_military_action, _has_military_anchor, _has_target, _is_negative, _root_event, _stage, _text


def has_target(event):
    return _has_target(event)


def is_negative(event):
    return _is_negative(event)


def has_military_anchor(event):
    return _has_military_anchor(event)


def has_direct_military_action(event):
    return _has_direct_military_action(event)


def safe_root_event(event):
    return _root_event(event)


def safe_stage(event, fallback_stage=None):
    return _stage(event) if fallback_stage is None else _stage(event)
