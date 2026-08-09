from google.adk.agents import LlmAgent

from app.agents.factory import create_agent


site_report_agent: LlmAgent = create_agent("site_report")
