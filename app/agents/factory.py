import app.tools
from google.adk.agents import BaseAgent, LlmAgent

from app.agents.registry import Registry, registry
from app.config import DEFAULT_GEMINI_MODEL_ID, get_settings


def create_agent(name: str, reg: Registry = registry) -> LlmAgent:
    config = reg.get_agent_config(name)
    prompt = reg.get_prompt(name)

    tool_funcs = []
    for t_name in config.tools:
        if not hasattr(app.tools, t_name):
            raise ValueError(f"Tool {t_name} not found in app.tools")
        tool_funcs.append(getattr(app.tools, t_name))

    sub_agents: list[BaseAgent] = []
    for sub_name in config.sub_agents:
        sub_agents.append(create_agent(sub_name, reg))

    return LlmAgent(
        name=name,
        description=config.description,
        model=get_settings().gemini_model_id or DEFAULT_GEMINI_MODEL_ID,
        instruction=prompt,
        tools=tool_funcs,
        sub_agents=sub_agents,
    )
