from langchain_openai import ChatOpenAI

from .config import react_agent_settings
from .utils import DataManager

chat_model = ChatOpenAI(
    base_url=react_agent_settings.openai_base_url,
    api_key=react_agent_settings.openai_api_key,
    model=react_agent_settings.llm_model,
    temperature=react_agent_settings.temperature,
)

backup_chat_model = ChatOpenAI(
    base_url=react_agent_settings.backup_openai_base_url,
    api_key=react_agent_settings.backup_openai_api_key,
    model=react_agent_settings.backup_llm_model,
    temperature=react_agent_settings.temperature,
)

data_manager = DataManager()
