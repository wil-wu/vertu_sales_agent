from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, ToolMessage

from .deps import get_react_agent
from .agent import ReActAgent
from .schemas import ReactAgentRequest, ReactAgentResponse
from .utils import MarkdownHelper

router = APIRouter(
    prefix="/api/v1/react",
    tags=["React Agent"],
)


@router.post("/chat", response_model=ReactAgentResponse)
async def chat(
    request: ReactAgentRequest,
    react_agent: ReActAgent = Depends(get_react_agent),
) -> ReactAgentResponse:
    agent_content = ""
    graph_query_links: list[str] = []

    user_message = request.message + f"\n严格遵循用户输入的语种进行回复！！！\n用户id：{request.user_id}\n平台：{request.platform}\n地区：{request.region}"

    async for event in react_agent.astream(
        user_message, request.thread_id, stream_mode="updates"
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
    
    return {
        "message": message,
        "thread_id": request.thread_id,
    }
