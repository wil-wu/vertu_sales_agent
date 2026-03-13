import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.shared import httpx_async_client
from .config import question_pool_settings, PLATFORM_CONFIG
from .prompts import (
    GRAPH_QA_GENERATION_PROMPT,
    PRICE_QUESTION_REWRITE_PROMPT,
    SCREEN_CONTENT_FILTER_PROMPT
)
from .shared import chat_model

logger = logging.getLogger(__name__)


class QuestionPoolService:
    """问题池生成服务"""

    def __init__(self):
        self.faq_url = question_pool_settings.faq_url
        self.price_url = question_pool_settings.price_url
        self.graph_url = question_pool_settings.graph_url
        self.output_dir = Path(question_pool_settings.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _fetch_faq(self, query: str, collection_name: str, top_k: int) -> List[dict]:
        """获取 FAQ 数据"""
        response = await httpx_async_client.post(
            self.faq_url,
            json={"query": query, "collection_names": [collection_name], "top_k": top_k},
            timeout=15.0
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for category in data.get("categories", []):
            for item in category.get("items", []):
                items.append({
                    "question": item.get("question", ""),
                    "answer": item.get("answer", "")
                })
        return items

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _fetch_price(self, query: str, index_name: str, hits_per_page: int) -> List[dict]:
        """获取价格数据"""
        response = await httpx_async_client.post(
            self.price_url,
            json={"query": query, "index_name": index_name, "hits_per_page": hits_per_page, "page": 1},
            timeout=15.0
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for hit in data.get("hits", []):
            items.append({
                "name": hit.get("name", ""),
                "price": hit.get("price", 0)
            })
        return items

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _fetch_graph(self, product_name: str, is_oversea: bool = False) -> dict:
        """获取图谱数据"""
        response = await httpx_async_client.post(
            self.graph_url,
            json={"product_name": product_name, "path_len": 2, "is_oversea": is_oversea},
            timeout=20.0
        )
        response.raise_for_status()
        return response.json()

    async def _generate_graph_qa(self, graph_data: dict) -> List[dict]:
        """使用 LLM 生成图谱问答对"""
        prompt = GRAPH_QA_GENERATION_PROMPT.replace("{graph_data}", json.dumps(graph_data, ensure_ascii=False, indent=2))

        messages = [{"role": "system", "content": "你是一个专业的知识图谱问答对生成专家。"}]
        messages.append({"role": "user", "content": prompt})

        try:
            response = await chat_model.ainvoke(messages)
            content = response.content.strip()

            # 清理 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 处理可能的单引号包裹
            if content.startswith("'") and content.endswith("'"):
                content = content[1:-1]

            # 处理双重引号包裹
            if content.startswith('"') and content.endswith('"'):
                try:
                    content = json.loads(content)
                except:
                    pass

            qa_pairs = json.loads(content)
            if isinstance(qa_pairs, dict):
                qa_pairs = [qa_pairs]
            return qa_pairs if isinstance(qa_pairs, list) else []
        except Exception as e:
            logger.warning(f"[图谱QA生成] LLM 生成失败: {e}")
            return []  # 失败时返回空列表

    async def _rewrite_price_question(self, product_name: str, price: float) -> str:
        """使用 LLM 将商品名称改写为用户价格询问问题"""
        prompt = PRICE_QUESTION_REWRITE_PROMPT.format(product_name=product_name, price=price)

        messages = [{"role": "user", "content": prompt}]
        try:
            response = await chat_model.ainvoke(messages)
            return response.content.strip().strip('"')
        except Exception as e:
            logger.warning(f"[价格问题改写] LLM 调用失败: {e}")
            return f"{product_name}多少钱？"  # 失败时返回默认问题

    async def _filter_screen_related(self, data_type: str, data_content: str) -> bool:
        """使用 LLM 筛选与屏幕相关的内容"""
        prompt = SCREEN_CONTENT_FILTER_PROMPT.format(
            data_type=data_type,
            data_content=data_content
        )

        messages = [{"role": "user", "content": prompt}]
        content = ""
        try:
            response = await chat_model.ainvoke(messages)
            content = response.content.strip()

            # 清理 markdown 代码块
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 处理可能的单引号包裹
            if content.startswith("'") and content.endswith("'"):
                content = content[1:-1]

            # 处理双重引号包裹（如 '"{...}"'）
            if content.startswith('"') and content.endswith('"'):
                try:
                    # 尝试先解析外层引号
                    content = json.loads(content)
                except:
                    pass

            result = json.loads(content)
            
            # 处理可能的引号包裹的 key
            is_related = result.get("is_screen_related", None)
            if is_related is None:
                is_related = result.get('"is_screen_related"', False)
            if is_related is None:
                is_related = result.get("'is_screen_related'", False)
            
            reason = result.get("reason", "")
            if not reason:
                reason = result.get('"reason"', "")
            if not reason:
                reason = result.get("'reason'", "")

            if is_related:
                logger.debug(f"[屏幕过滤] 保留 {data_type}: {reason}")
            else:
                logger.debug(f"[屏幕过滤] 过滤 {data_type}: {reason}")

            return is_related
        except Exception as e:
            logger.warning(f"[屏幕过滤] LLM 筛选失败，默认保留: {e}, content: {repr(content)}")
            return True  # 失败时默认保留

    def _generate_graph_summary(self, graph_data: dict) -> str:
        """从图谱数据生成摘要文本用于综合问答"""
        summary_parts = []

        if "p" in graph_data:
            p = graph_data["p"]
            summary_parts.append(f"产品信息: {p}")

        if "n1" in graph_data:
            n1 = graph_data["n1"]
            summary_parts.append(f"款式信息: {n1}")

        return "; ".join(summary_parts) if summary_parts else "暂无图谱信息"

    async def generate_pool(
        self,
        product_name: str,
        platform: str,
        count: int
    ) -> dict:
        """生成问题池 CSV 文件"""
        logger.info(f"开始生成问题池: product={product_name}, platform={platform}, count={count}")

        config = PLATFORM_CONFIG.get(platform)
        if not config:
            raise ValueError(f"不支持的平台: {platform}")

        # 简化比例：FAQ 0.5, 价格 0.3, 图谱 0.2
        faq_target = int(count * 0.5)
        price_target = int(count * 0.3)
        graph_target = int(count * 0.2)

        # 并发获取三个渠道的数据
        faq_data = await self._fetch_faq(
            product_name,
            config["faq_collection"],
            max(faq_target * 4, 20)  # 获取更多数据用于过滤
        )
        price_data = await self._fetch_price(
            product_name,
            config["price_index"],
            max(price_target * 4, 20)  # 获取更多数据用于过滤
        )
        is_oversea = platform == "overseas"
        graph_data = await self._fetch_graph(product_name, is_oversea)

        # 使用 LLM 过滤屏幕相关内容
        logger.info("开始筛选屏幕相关内容...")

        # 过滤 FAQ 数据
        faq_data_filtered = []
        for item in faq_data:
            content = f"问题: {item.get('question', '')}\n答案: {item.get('answer', '')}"
            if await self._filter_screen_related("FAQ", content):
                faq_data_filtered.append(item)
            if len(faq_data_filtered) >= faq_target * 2:  # 获取足够数量后停止
                break

        # 过滤价格数据
        price_data_filtered = []
        for item in price_data:
            content = f"商品名称: {item.get('name', '')}"
            if await self._filter_screen_related("价格", content):
                price_data_filtered.append(item)
            if len(price_data_filtered) >= price_target * 2:
                break

        # 统计原始数据
        graph_results = graph_data.get("data", {}).get("result", []) if isinstance(graph_data, dict) else []
        source_stats = {
            "faq_hits": len(faq_data),
            "price_hits": len(price_data),
            "graph_nodes": len(graph_results)
        }

        # 转换 FAQ 数据
        faq_pool = [
            {"question": item["question"], "answer": item["answer"], "platform": platform, "channel": "faq"}
            for item in faq_data_filtered[:faq_target]
        ]

        # 转换价格数据（使用 LLM 改写问题）
        price_pool = []
        for item in price_data_filtered[:price_target]:
            rewritten_question = await self._rewrite_price_question(item["name"], item["price"])
            price_pool.append({
                "question": rewritten_question,
                "answer": f"{item['price']}元",
                "platform": platform,
                "channel": "price"
            })

        # 生成图谱问答对并过滤屏幕相关内容
        graph_qa_list = await self._generate_graph_qa(graph_data)
        graph_pool = []
        for qa in graph_qa_list:
            content = f"问题: {qa.get('question', '')}\n答案: {qa.get('answer', '')}"
            if await self._filter_screen_related("图谱", content):
                graph_pool.append({
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "platform": platform,
                    "channel": "graph"
                })
            if len(graph_pool) >= graph_target:
                break

        # 合并所有数据
        all_questions = faq_pool + price_pool + graph_pool

        # 去重：相同 question 只保留一个
        seen = set()
        unique = []
        for qa in all_questions:
            q = qa["question"].lower().strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(qa)
        all_questions = unique

        # 生成 CSV 文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"question_pool_{product_name.replace(' ', '_')}_{platform}_{timestamp}_{count}.csv"
        file_path = self.output_dir / filename

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "platform", "channel"])
            writer.writeheader()
            writer.writerows(all_questions)

        logger.info(f"问题池已生成: {file_path}")

        return {
            "file_path": str(file_path),
            "total_generated": len(all_questions),
            "breakdown": {
                "faq": len(faq_pool),
                "price": len(price_pool),
                "graph": len(graph_pool)
            },
            "sources": source_stats
        }
