"""Engineering Brain Agent System — deep reasoning over brain knowledge.

Public API:
    from engineering_brain.agent import run_agent, agent_status
    result = run_agent(brain, query)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engineering_brain.core.brain import Brain

from engineering_brain.agent.types import AgentQuery, ComposedKnowledge


def run_agent(brain: Brain, query: AgentQuery) -> ComposedKnowledge:
    """Run the agent system on a query.

    This is the main entry point. It:
    1. Validates the agent is configured (API key + feature flag)
    2. Creates BrainAccess, LLMClient, Orchestrator
    3. Runs the orchestration flow
    4. Returns ComposedKnowledge

    Raises:
        RuntimeError: If agent is not enabled or API key is missing
    """
    from engineering_brain.agent.brain_access import BrainAccess
    from engineering_brain.agent.config import get_agent_config
    from engineering_brain.agent.llm_client import LLMClient
    from engineering_brain.agent.orchestrator import Orchestrator

    config = get_agent_config(brain._config)

    if not config.is_configured:
        raise RuntimeError(
            "Agent system not configured. Set BRAIN_AGENT_ENABLED=true "
            "and BRAIN_AGENT_API_KEY=<your-anthropic-key>"
        )

    brain_access = BrainAccess(brain)
    llm_client = LLMClient(config)
    orchestrator = Orchestrator(brain_access, llm_client, config)

    return orchestrator.run(query)


def agent_status(brain: Brain) -> dict[str, Any]:
    """Check agent system availability.

    Returns:
        {
            "enabled": bool,
            "configured": bool,  # enabled + has API key
            "model": str,
            "orchestrator_model": str,
            "max_workers": int,
        }
    """
    from engineering_brain.agent.config import get_agent_config

    config = get_agent_config(brain._config)
    return {
        "enabled": config.enabled,
        "configured": config.is_configured,
        "model": config.model,
        "orchestrator_model": config.orchestrator_model,
        "max_workers": config.max_workers,
    }
