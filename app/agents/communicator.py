from google.adk.agents import LlmAgent

from app.agents.factory import create_agent


communicator_agent: LlmAgent = create_agent("communicator")
