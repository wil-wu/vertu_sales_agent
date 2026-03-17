import logging
from typing import Self, Generator, AsyncGenerator
from datetime import datetime

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import Tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)


class ReActAgent:
    """ReAct Agent 单例工作流"""

    _instance: Self | None = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs) -> Self:
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self, 
        chat_model: BaseChatModel, 
        tools: list[Tool], 
        system_prompt: str, 
        backup_chat_model: BaseChatModel = None,
    ):
        if self._initialized:
            return
        self._initialized = True
        self._chat_model = chat_model
        self._backup_chat_model = backup_chat_model
        self._tools = tools
        self._chat_model_with_tools = chat_model.bind_tools(tools)
        self._backup_chat_model_with_tools = backup_chat_model.bind_tools(tools) if backup_chat_model else None
        self._system_prompt = system_prompt
        self._graph = self._build()

    def run(self, message: str, thread_id: str) -> str:
        response = self._graph.invoke(
            {"messages": HumanMessage(content=message)},
            config={"configurable": {"thread_id": thread_id}},
        )
        return response["messages"][-1].content
    
    def stream(self, message: str, thread_id: str, stream_mode: str = "updates") -> Generator[str, None, None]:
        return self._graph.stream(
            {"messages": HumanMessage(content=message)},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=stream_mode,
        )
    
    def astream(self, message: str, thread_id: str, stream_mode: str = "updates") -> AsyncGenerator[str, None]:
        return self._graph.astream(
            {"messages": HumanMessage(content=message)},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=stream_mode,
        )

    async def arun(self, message: str, thread_id: str) -> str:
        response = await self._graph.ainvoke(
            {"messages": HumanMessage(content=message)},
            config={"configurable": {"thread_id": thread_id}},
        )
        return response["messages"][-1].content

    async def _agent_node(self, state: MessagesState) -> dict:
        system_message = SystemMessage(
            content=self._system_prompt.format(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        messages = [
            system_message,
            *state["messages"],
        ]

        try:
            response = await self._chat_model_with_tools.ainvoke(messages)
        except Exception as e:
            logger.error(f"Primary chat model invocation failed: {e}")
            if self._backup_chat_model_with_tools:
                logger.warning("Falling back to backup chat model")
                response = await self._backup_chat_model_with_tools.ainvoke(messages)
            else:
                logger.error("No backup chat model available, re-raising")
                raise e
        return {"messages": [response]}

    def _should_continue(self, state: MessagesState) -> str:
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    def _get_checkpointer(self) -> BaseCheckpointSaver:
        """会话持久化存储，默认使用内存存储"""
        return MemorySaver()

    def _build(self) -> StateGraph:
        graph = StateGraph(MessagesState)

        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", ToolNode(self._tools))

        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self._should_continue)
        graph.add_edge("tools", "agent")

        return graph.compile(checkpointer=self._get_checkpointer())


class AISalesAgent(ReActAgent):
    """销售场景 ReAct Agent：会话持久化使用 PostgreSQL checkpointer。"""
    
    def _get_checkpointer(self) -> BaseCheckpointSaver:
        """Postgres checkpointer 做会话持久化。"""
        from app.core.shared import postgres_checkpointer
        return postgres_checkpointer
