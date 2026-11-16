"""The trip graph: one supervisor agent, built once per process."""

from safar_api.agents.supervisor import build_supervisor_agent

_graph = None


def get_graph():
    """Return the compiled supervisor."""
    global _graph
    if _graph is None:
        _graph = build_supervisor_agent()
    return _graph
