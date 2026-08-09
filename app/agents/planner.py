from google.adk.agents import LlmAgent

from app.agents.factory import create_agent


planner_agent: LlmAgent = create_agent("planner")
