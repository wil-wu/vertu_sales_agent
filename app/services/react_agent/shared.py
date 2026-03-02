from langchain_openai import ChatOpenAI

from .config import react_agent_settings

chat_model = ChatOpenAI(
    base_url=react_agent_settings.openai_base_url,
    api_key=react_agent_settings.openai_api_key,
    model=react_agent_settings.llm_model,
    temperature=react_agent_settings.temperature,
)
