"""Host task scope: limit available effects to the current explicit request."""

import re


def is_multistep_request(message: str) -> bool:
    # A conjunction alone does not authorize tasks in an ordinary conversation.
    operation = r"提醒|查|搜索|告诉我.{0,8}几点|几点|计时|待办|设备|电脑|更新.{0,5}资料|偏好|回忆"
    clauses = re.split(r"然后|再(?:帮我|替我)?|接着|之后|并且|同时|，|,|；|;", message)
    return len([part for part in clauses if re.search(operation, part)]) >= 2 and bool(
        re.search(r"先|然后|再|接着|并且|同时|依次", message)
    )


def task_tool_scope(message: str, tools: list[dict]) -> set[str]:
    """Host-side effect scope. Model choice cannot create new capabilities."""
    permitted = {tool["name"] for tool in tools if tool.get("annotations", {}).get("readOnlyHint")}
    from shared_runtime.reminder_language import cancellation_target

    target = cancellation_target(message)
    if target is None and re.search(r"(?:不要|先别|不用|不需要).{0,12}(?:提醒|打开|通知|设置)", message):
        return permitted
    if target is not None:
        permitted.add("cancel_reminder")
    elif re.search(r"提醒我|提醒一下|帮我提醒|remind me|set.*reminder", message, re.I):
        permitted.add("set_reminder")
    if re.search(r"计时|倒计时|timer|countdown", message, re.I):
        permitted.add("timer_countdown")
    if re.search(r"(?:更新|修改|设置).{0,8}(?:资料|偏好|名字|称呼|语言)", message):
        permitted.add("update_user_profile")
    for clause in re.split(r"然后|接着|，|,|；|;", message):
        if re.search(r"(?:电脑|设备).{0,12}(?:通知|打开)|(?:给|让).{0,10}(?:电脑|设备)", clause):
            if re.search(r"通知|notification", clause, re.I):
                permitted.add("device_notify")
            if re.search(r"打开|open", clause, re.I):
                permitted.add("device_open_url")
    # External writes require both explicit host configuration and a request
    # naming that server. General chat never silently activates remote writes.
    for tool in tools:
        if "__" in tool["name"] and tool["name"].split("__", 1)[0] in message:
            permitted.add(tool["name"])
    return permitted
