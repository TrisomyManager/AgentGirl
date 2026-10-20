"""Disabled until the host explicitly grants users access in its private config."""

from action_executor.registry import ActionResult


async def setup(api):
    async def echo(arguments, context):
        return ActionResult(message=arguments["text"], data={"operation_id": context.operation_id})

    api.add_tool(
        "echo",
        "返回用户提供的文字，用于验证扩展接入。",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 1000}},
            "required": ["text"],
            "additionalProperties": False,
        },
        echo,
        read_only=True,
    )
