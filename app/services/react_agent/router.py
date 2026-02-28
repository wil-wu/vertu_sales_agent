from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, ToolMessage

from .deps import get_react_agent
from .agent import ReActAgent
from .schemas import ReactAgentRequest, ReactAgentResponse
from .utils import LanguageDetector, LanguageTranslator, MarkdownHelper
from .config import react_agent_settings
from .shared import chat_model
from .prompts import TRANSLATE_SYSTEM_PROMPT

router = APIRouter(
    prefix="/api/v1/react",
    tags=["React Agent"],
)

language_detector = LanguageDetector(react_agent_settings.language_detector_model_path)
language_translator = LanguageTranslator(chat_model, TRANSLATE_SYSTEM_PROMPT)


@router.post("/chat", response_model=ReactAgentResponse)
async def chat(
    request: ReactAgentRequest,
    react_agent: ReActAgent = Depends(get_react_agent),
) -> ReactAgentResponse:
    agent_content = ""
    graph_query_links: list[str] = []

    async for event in react_agent.astream(
        request.message, request.thread_id, stream_mode="updates"
    ):
        if "agent" in event:
            msgs = event["agent"].get("messages", [])
            if msgs:
                last_msg = msgs[-1]
                if isinstance(last_msg, AIMessage) and last_msg.content:
                    content = (
                        last_msg.content
                        if isinstance(last_msg.content, str)
                        else str(last_msg.content)
                    )
                    agent_content = MarkdownHelper.remove_markdown_links(content)

        if "tools" in event:
            msgs = event["tools"].get("messages", [])
            for msg in msgs:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == "graph_query":
                    content = msg.content
                    if isinstance(content, list):
                        content = "\n".join(str(item) for item in content)
                    else:
                        content = content if isinstance(content, str) else str(content)
                    graph_query_links.extend(MarkdownHelper.extract_markdown_links(content))

    if graph_query_links:
        message = f"{agent_content}\n\n" + "\n".join(graph_query_links)
    else:
        message = agent_content
    
    user_lang = language_detector.detect(request.message)
    answer_lang = language_detector.detect(message)

    if user_lang != "unknown" and answer_lang != user_lang:
        message = language_translator.translate(message, user_lang)
    
    return {
        "message": message,
        "thread_id": request.thread_id,
    }
