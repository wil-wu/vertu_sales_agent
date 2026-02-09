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
    react_agent: ReActAgent = Depends(get_react_agent)
) -> ReactAgentResponse:
    message = await react_agent.arun(request.message, request.thread_id)
    return {
        "message": message,
        "thread_id": request.thread_id,
    }
