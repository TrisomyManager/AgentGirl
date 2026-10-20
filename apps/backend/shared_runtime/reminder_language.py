"""Recognize requests to cancel existing reminders without confusing a veto with creation."""

import re

_CANCEL = re.compile(
    r"^(?:请|麻烦|你|帮我|替我|帮忙|\s){0,6}(?:取消|停掉|停止|删掉|删除)(?:一下)?(?P<target>.*提醒.*)$|"
    r"^(?:(?:以后)?(?:不用|不需要|不要再|别再)(?:再)?提醒(?:我)?)(?P<stop>.*)$|"
    r"^stop reminding me(?P<english>.*)$",
    re.I,
)


def cancellation_target(message: str) -> str | None:
    match = _CANCEL.search(message.strip())
    if not match:
        return None
    target = (match.group("target") or match.group("stop") or match.group("english") or "").strip()
    target = re.sub(r"^(?:我|那个|那条|这条|一下|关于)", "", target)
    target = re.sub(r"(?:的)?提醒(?:了|吧)?[。！!\s]*$", "", target)
    target = re.sub(r"^(?:提醒我|提醒)", "", target)
    target = re.sub(r"[。！!\s]*(?:了|吧)[。！!\s]*$", "", target)
    return target.strip(" 。！!，,~～")
