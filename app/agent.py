from google.adk.agents import LlmAgent

from app.agents.factory import create_agent


oga_agent: LlmAgent = create_agent("oga_coordinator")
