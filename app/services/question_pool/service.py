import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.shared import httpx_async_client
from .config import question_pool_settings, PLATFORM_CONFIG, DISTRIBUTION_RATIO
from .prompts import GRAPH_QA_GENERATION_PROMPT, COMBINED_QA_GENERATION_PROMPT
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
    async def _fetch_graph(self, product_name: str) -> dict:
        """获取图谱数据"""
        response = await httpx_async_client.post(
            self.graph_url,
            params={"product_name": product_name, "path_len": 2, "is_oversea": "false"},
            timeout=20.0
        )
        response.raise_for_status()
        return response.json()

    async def _generate_graph_qa(self, graph_data: dict) -> List[dict]:
        """使用 LLM 生成图谱问答对"""
        prompt = GRAPH_QA_GENERATION_PROMPT.replace("{graph_data}", json.dumps(graph_data, ensure_ascii=False, indent=2))

        messages = [{"role": "system", "content": "你是一个专业的知识图谱问答对生成专家。"}]
        messages.append({"role": "user", "content": prompt})

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

        qa_pairs = json.loads(content)
        if isinstance(qa_pairs, dict):
            qa_pairs = [qa_pairs]
        return qa_pairs if isinstance(qa_pairs, list) else []

    async def _generate_combined_qa(
        self,
        faq_item: dict,
        price_item: dict,
        graph_summary: str
    ) -> dict:
        """使用 LLM 生成综合问答对"""
        prompt = COMBINED_QA_GENERATION_PROMPT.format(
            faq_question=faq_item.get("question", ""),
            faq_answer=faq_item.get("answer", ""),
            price_name=price_item.get("name", ""),
            price_value=price_item.get("price", 0),
            graph_info=graph_summary
        )

        messages = [{"role": "system", "content": "你是一个专业的问答对生成专家。"}]
        messages.append({"role": "user", "content": prompt})

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

        return json.loads(content)

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
        platform_label = config["platform_label"]

        # 计算各渠道需要的数量（1.5倍冗余以应对可能的不足）
        faq_target = int(count * DISTRIBUTION_RATIO["faq"])
        price_target = int(count * DISTRIBUTION_RATIO["price"])
        graph_target = int(count * DISTRIBUTION_RATIO["graph"])
        combined_target = int(count * DISTRIBUTION_RATIO["combined"])

        # 并发获取三个渠道的数据
        faq_data = await self._fetch_faq(
            product_name,
            config["faq_collection"],
            max(faq_target * 2, 10)
        )
        price_data = await self._fetch_price(
            product_name,
            config["price_index"],
            max(price_target * 2, 10)
        )
        graph_data = await self._fetch_graph(product_name)

        # 统计原始数据
        source_stats = {
            "faq_hits": len(faq_data),
            "price_hits": len(price_data),
            "graph_nodes": len(graph_data.get("results", [])) if isinstance(graph_data, dict) else 0
        }

        # 转换 FAQ 数据
        faq_pool = [
            {"question": item["question"], "answer": item["answer"], "platform": platform_label}
            for item in faq_data[:faq_target]
        ]

        # 转换价格数据
        price_pool = [
            {"question": item["name"], "answer": f"{item['price']}元", "platform": platform_label}
            for item in price_data[:price_target]
        ]

        # 生成图谱问答对
        graph_qa_list = await self._generate_graph_qa(graph_data)
        graph_pool = [
            {"question": qa["question"], "answer": qa["answer"], "platform": platform_label}
            for qa in graph_qa_list[:graph_target]
        ]

        # 兜底策略：如果某个渠道数据不足，用其他渠道补足
        combined_pool = await self._generate_combined_pool(
            faq_data, price_data, graph_data,
            combined_target, platform_label
        )

        # 合并所有数据
        all_questions = faq_pool + price_pool + graph_pool + combined_pool

        # 兜底：如果总量不足，循环填充
        while len(all_questions) < count:
            for source in [faq_pool, price_pool, graph_pool, combined_pool]:
                if source and len(all_questions) < count:
                    idx = len(all_questions) % len(source)
                    all_questions.append(source[idx])

        # 截取所需数量
        all_questions = all_questions[:count]

        # 生成 CSV 文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"question_pool_{product_name.replace(' ', '_')}_{platform}_{timestamp}_{count}.csv"
        file_path = self.output_dir / filename

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "platform"])
            writer.writeheader()
            writer.writerows(all_questions)

        logger.info(f"问题池已生成: {file_path}")

        return {
            "file_path": str(file_path),
            "total_generated": len(all_questions),
            "breakdown": {
                "faq": len(faq_pool),
                "price": len(price_pool),
                "graph": len(graph_pool),
                "combined": len(combined_pool)
            },
            "sources": source_stats
        }

    async def _generate_combined_pool(
        self,
        faq_data: List[dict],
        price_data: List[dict],
        graph_data: dict,
        target_count: int,
        platform_label: str
    ) -> List[dict]:
        """生成综合问答池"""
        combined_pool = []

        if not faq_data or not price_data:
            return combined_pool

        graph_summary = self._generate_graph_summary(graph_data)

        # 生成组合（简单的笛卡尔积，取前 target_count 个）
        for i in range(min(target_count, len(faq_data))):
            faq_item = faq_data[i]
            price_item = price_data[i % len(price_data)]

            qa = await self._generate_combined_qa(faq_item, price_item, graph_summary)
            combined_pool.append({
                "question": qa.get("question", ""),
                "answer": qa.get("answer", ""),
                "platform": platform_label
            })

        return combined_pool
