from google.adk.agents import LlmAgent

from app.agents.factory import create_agent


materials_agent: LlmAgent = create_agent("materials")
