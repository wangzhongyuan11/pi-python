from pi_coding_agent.extensions import ExtensionAPI


def _command(value: str) -> str:
    return value or "python-ok"


def activate(api: ExtensionAPI) -> None:
    api.define_command("upstream-python-proof", _command)
