from __future__ import annotations

from dataclasses import replace

from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import FakeProvider, TextContent, fake_model

generation = 0


class GoldenArgs(BaseModel):
    text: str


async def _execute(_call_id, params, _abort, _update):
    return AgentToolResult(
        content=(TextContent(text=f"golden-tool:{params.text}"),),
        details={"text": params.text},
    )


class GoldenProvider(FakeProvider):
    @property
    def id(self):
        return "golden"

    @property
    def models(self):
        return (replace(fake_model(), provider="golden", id="golden-model"),)


def activate(api):
    global generation
    generation += 1

    api.define_flag("--golden-mode", default=False)
    api.define_tool(
        "golden_echo",
        AgentTool(
            name="golden_echo",
            label="Golden echo",
            description="Echo one value through the installed golden extension",
            parameter_type=GoldenArgs,
            execute=_execute,
        ),
    )
    api.define_provider("golden", GoldenProvider())
    api.define_message_renderer("golden-status", lambda message: f"golden-render:{message.content}")
    api.define_tool_renderer(
        "golden_echo",
        render_result=lambda result: "golden-tool-rendered"
        if getattr(result, "details", None)
        else None,
    )

    def session_start(_event):
        enabled = api.get_flag("--golden-mode") is True
        api.send_message("golden-status", f"mode:{'on' if enabled else 'off'}")

    def tool_result(event):
        if event.tool_name == "golden_echo":
            return {
                "content": (TextContent(text="golden-hook-result"),),
                "details": {"hooked": True},
                "is_error": False,
            }
        return None

    async def reload_command(_args, context):
        await context.reload()
        return "golden-reloaded"

    async def new_command(_args, context):
        cancelled = await context.new_session()
        return "golden-new-cancelled" if cancelled else "golden-new-session"

    async def switch_command(args, context):
        cancelled = await context.switch_session(args.strip())
        return "golden-switch-cancelled" if cancelled else "golden-switched"

    api.on("session_start", session_start)
    api.on("tool_result", tool_result)
    api.define_command(
        "golden-status",
        lambda _args, _context: (
            f"golden-status mode={api.get_flag('--golden-mode')} generation={generation}"
        ),
    )
    api.define_command("golden-reload", reload_command)
    api.define_command("golden-new", new_command)
    api.define_command("golden-switch", switch_command)

    return lambda: None
