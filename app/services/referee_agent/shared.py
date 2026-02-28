import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional
import aiofiles

from langchain_openai import ChatOpenAI

from .config import referee_agent_settings
from .schemas import SessionRecord

# 聊天模型实例
chat_model = ChatOpenAI(
    api_key=referee_agent_settings.openai_api_key,
    base_url=referee_agent_settings.openai_base_url,
    model=referee_agent_settings.llm_model,
    temperature=0.7,
    max_tokens=4000,
)


class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, SessionRecord] = {}
        if referee_agent_settings.save_session_data:
            self.data_dir = Path(referee_agent_settings.session_data_dir)
            self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def create_session(self, session_id: str) -> SessionRecord:
        """创建新会话"""
        session = SessionRecord(
            session_id=session_id,
            start_time=datetime.now()
        )
        self.sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def close_session(self, session_id: str, reason: str):
        """关闭会话"""
        session = self.get_session(session_id)
        if session:
            session.end_time = datetime.now()
            session.termination_reason = reason
            session.calculate_final_score()
            
            if referee_agent_settings.save_session_data and hasattr(self, 'data_dir'):
                try:
                    # 使用异步任务保存
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._save_session_async(session))
                except RuntimeError:
                    # 如果没有运行的事件循环，直接保存
                    filename = f"{session.session_id}_{session.start_time.strftime('%Y%m%d_%H%M%S')}.json"
                    filepath = self.data_dir / filename
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(session.model_dump_json(indent=2))
    
    async def _save_session_async(self, session: SessionRecord):
        """异步保存会话数据"""
        filename = f"{session.session_id}_{session.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.data_dir / filename
        
        try:
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(session.model_dump_json(indent=2))
        except Exception as e:
            # 记录错误但不中断主流程
            print(f"Failed to save session data: {e}")
            
    def get_all_sessions(self) -> list[SessionRecord]:
        """获取所有会话"""
        return list(self.sessions.values())


class AssessmentTracker:
    """评估跟踪器"""
    
    def __init__(self):
        self.score_history: Dict[str, list[float]] = {}
    
    def add_score(self, session_id: str, score: float):
        """添加评分"""
        if session_id not in self.score_history:
            self.score_history[session_id] = []
        self.score_history[session_id].append(score)
        
    def check_consecutive_low_scores(self, session_id: str) -> bool:
        """检查连续低分"""
        scores = self.score_history.get(session_id, [])
        if len(scores) < referee_agent_settings.consecutive_low_scores:
            return False
            
        recent_scores = scores[-referee_agent_settings.consecutive_low_scores:]
        return all(score < referee_agent_settings.low_score_threshold 
                  for score in recent_scores)
    
    def get_score_trend(self, session_id: str) -> float:
        """获取评分趋势"""
        scores = self.score_history.get(session_id, [])
        if len(scores) < 2:
            return 0.0
        
        # 计算最近5轮的趋势
        recent_scores = scores[-5:] if len(scores) > 5 else scores
        if len(recent_scores) < 2:
            return 0.0
            
        trend = (recent_scores[-1] - recent_scores[0]) / len(recent_scores)
        return trend


# 全局实例
session_manager = SessionManager()
assessment_tracker = AssessmentTracker()
