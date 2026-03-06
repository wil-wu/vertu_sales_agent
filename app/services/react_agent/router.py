from fastapi import APIRouter, Depends

from .deps import get_react_agent
from .agent import ReActAgent
from .schemas import ReactAgentRequest, ReactAgentResponse

router = APIRouter(
    prefix="/api/v1/react",
    tags=["React Agent"],
)


@router.post("/chat", response_model=ReactAgentResponse)
async def chat(
    request: ReactAgentRequest,
    react_agent: ReActAgent = Depends(get_react_agent),
) -> ReactAgentResponse:
    user_message = f"""
    严格遵循用户输入的语种进行回复！！！
    用户消息：{request.message}
    用户id：{request.user_id}
    平台：{request.platform}
    地区：{request.region}
    """

    agent_message = await react_agent.arun(user_message, request.thread_id)
    
    return {
        "message": agent_message,
        "thread_id": request.thread_id,
    }
