from .agent import ReActAgent
from .shared import chat_model
from .tools import TOOLS
from .prompts import REACT_AGENT_SYSTEM_PROMPT


def get_react_agent() -> ReActAgent:
    return ReActAgent(
        chat_model=chat_model,
        tools=TOOLS,
        system_prompt=REACT_AGENT_SYSTEM_PROMPT,
    )
