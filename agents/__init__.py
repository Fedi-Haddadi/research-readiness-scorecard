"""Research Readiness Scorecard agents package."""

__all__ = ["run_research_readiness_agent"]


def __getattr__(name: str):
    if name == "run_research_readiness_agent":
        from agents.agent import run_research_readiness_agent

        return run_research_readiness_agent
    raise AttributeError(name)
