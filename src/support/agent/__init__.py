from typing import Any

__all__ = ["Agent", "make_graph"]


def __getattr__(name: str) -> Any:
    if name in {"Agent", "make_graph"}:
        from src.support.agent.agent import Agent, make_graph

        return {"Agent": Agent, "make_graph": make_graph}[name]
    raise AttributeError(name)
