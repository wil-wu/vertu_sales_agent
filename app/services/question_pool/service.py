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
from .prompts import (
    GRAPH_QA_GENERATION_PROMPT,
    PRICE_QUESTION_REWRITE_PROMPT,
    FAQ_PRICE_COMBINED_PROMPT,
    FAQ_GRAPH_COMBINED_PROMPT,
    PRICE_GRAPH_COMBINED_PROMPT,
    TRIPLE_COMBINED_PROMPT
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

    async def _rewrite_price_question(self, product_name: str, price: float) -> str:
        """使用 LLM 将商品名称改写为用户价格询问问题"""
        prompt = PRICE_QUESTION_REWRITE_PROMPT.format(product_name=product_name, price=price)

        messages = [{"role": "user", "content": prompt}]
        response = await chat_model.ainvoke(messages)
        return response.content.strip().strip('"')

    async def _generate_faq_price_qa(self, faq_item: dict, price_item: dict) -> dict:
        """生成 FAQ × 价格 组合问答对"""
        prompt = FAQ_PRICE_COMBINED_PROMPT.format(
            faq_question=faq_item.get("question", ""),
            faq_answer=faq_item.get("answer", ""),
            price_name=price_item.get("name", ""),
            price_value=price_item.get("price", 0)
        )
        messages = [{"role": "user", "content": prompt}]
        response = await chat_model.ainvoke(messages)
        content = self._clean_json_response(response.content)
        return json.loads(content)

    async def _generate_faq_graph_qa(self, faq_item: dict, graph_qa: dict) -> dict:
        """生成 FAQ × 图谱 组合问答对"""
        prompt = FAQ_GRAPH_COMBINED_PROMPT.format(
            faq_question=faq_item.get("question", ""),
            faq_answer=faq_item.get("answer", ""),
            graph_info=f"{graph_qa.get('question', '')}: {graph_qa.get('answer', '')}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await chat_model.ainvoke(messages)
        content = self._clean_json_response(response.content)
        return json.loads(content)

    async def _generate_price_graph_qa(self, price_item: dict, graph_qa: dict) -> dict:
        """生成 价格 × 图谱 组合问答对"""
        prompt = PRICE_GRAPH_COMBINED_PROMPT.format(
            price_name=price_item.get("name", ""),
            price_value=price_item.get("price", 0),
            graph_info=f"{graph_qa.get('question', '')}: {graph_qa.get('answer', '')}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await chat_model.ainvoke(messages)
        content = self._clean_json_response(response.content)
        return json.loads(content)

    async def _generate_triple_qa(self, faq_item: dict, price_item: dict, graph_qa: dict) -> dict:
        """生成 FAQ × 价格 × 图谱 三者组合问答对"""
        prompt = TRIPLE_COMBINED_PROMPT.format(
            faq_question=faq_item.get("question", ""),
            faq_answer=faq_item.get("answer", ""),
            price_name=price_item.get("name", ""),
            price_value=price_item.get("price", 0),
            graph_info=f"{graph_qa.get('question', '')}: {graph_qa.get('answer', '')}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await chat_model.ainvoke(messages)
        content = self._clean_json_response(response.content)
        return json.loads(content)

    def _clean_json_response(self, content: str) -> str:
        """清理 LLM 返回的 JSON 响应"""
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

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

        # 新比例：FAQ 0.5, 价格 0.1, 图谱 0.2, 多源组合平分 0.3
        faq_target = int(count * 0.5)
        price_target = int(count * 0.1)
        graph_target = int(count * 0.2)
        combined_each = int(count * 0.075)  # 四种组合各 0.075

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
            {"question": item["question"], "answer": item["answer"], "platform": platform, "channel": "faq"}
            for item in faq_data[:faq_target]
        ]

        # 转换价格数据（使用 LLM 改写问题）
        price_pool = []
        for item in price_data[:price_target]:
            rewritten_question = await self._rewrite_price_question(item["name"], item["price"])
            price_pool.append({
                "question": rewritten_question,
                "answer": f"{item['price']}元",
                "platform": platform,
                "channel": "price"
            })

        # 生成图谱问答对
        graph_qa_list = await self._generate_graph_qa(graph_data)
        graph_pool = [
            {"question": qa["question"], "answer": qa["answer"], "platform": platform, "channel": "graph"}
            for qa in graph_qa_list[:graph_target]
        ]

        # 生成多源组合（FAQ×价格、FAQ×图谱、价格×图谱、FAQ×价格×图谱）
        combined_pools = await self._generate_all_combined_pools(
            faq_data, price_data, graph_qa_list, combined_each, platform
        )

        # 合并所有数据
        combined_pool = (
            combined_pools["faq_price"] +
            combined_pools["faq_graph"] +
            combined_pools["price_graph"] +
            combined_pools["faq_price_graph"]
        )
        all_questions = faq_pool + price_pool + graph_pool + combined_pool

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
                "graph": len(graph_pool),
                "faq_price": len(combined_pools["faq_price"]),
                "faq_graph": len(combined_pools["faq_graph"]),
                "price_graph": len(combined_pools["price_graph"]),
                "faq_price_graph": len(combined_pools["faq_price_graph"]),
                "combined_total": len(combined_pool)
            },
            "sources": source_stats
        }

    async def _generate_all_combined_pools(
        self,
        faq_data: List[dict],
        price_data: List[dict],
        graph_qa_list: List[dict],
        each_count: int,
        platform: str
    ) -> dict:
        """生成所有多源组合：FAQ×价格、FAQ×图谱、价格×图谱、FAQ×价格×图谱"""
        pools = {
            "faq_price": [],
            "faq_graph": [],
            "price_graph": [],
            "faq_price_graph": []
        }

        # 对 FAQ 去重（忽略大小写）
        seen_faq = set()
        unique_faq = []
        for item in faq_data:
            q = item.get("question", "").lower().strip()
            if q and q not in seen_faq:
                seen_faq.add(q)
                unique_faq.append(item)
        faq_data = unique_faq

        # FAQ × 价格
        seen_questions = set()
        for i in range(min(each_count, len(faq_data))):
            for j in range(min(3, len(price_data))):
                if len(pools["faq_price"]) >= each_count:
                    break
                qa = await self._generate_faq_price_qa(faq_data[i], price_data[j])
                q = qa.get("question", "").lower().strip()
                if q and q not in seen_questions:
                    seen_questions.add(q)
                    pools["faq_price"].append({
                        "question": qa.get("question", ""),
                        "answer": qa.get("answer", ""),
                        "platform": platform,
                        "channel": "faq_price"
                    })
            for j in range(min(3, len(price_data))):
                if len(pools["faq_price"]) >= each_count:
                    break
                qa = await self._generate_faq_price_qa(faq_data[i], price_data[j])
                pools["faq_price"].append({
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", ""),
                    "platform": platform,
                    "channel": "faq_price"
                })

        # FAQ × 图谱
        for i in range(min(each_count, len(faq_data))):
            for j in range(min(3, len(graph_qa_list))):
                if len(pools["faq_graph"]) >= each_count:
                    break
                qa = await self._generate_faq_graph_qa(faq_data[i], graph_qa_list[j])
                pools["faq_graph"].append({
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", ""),
                    "platform": platform,
                    "channel": "faq_graph"
                })

        # 价格 × 图谱
        for i in range(min(each_count, len(price_data))):
            for j in range(min(3, len(graph_qa_list))):
                if len(pools["price_graph"]) >= each_count:
                    break
                qa = await self._generate_price_graph_qa(price_data[i], graph_qa_list[j])
                pools["price_graph"].append({
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", ""),
                    "platform": platform,
                    "channel": "price_graph"
                })

        # FAQ × 价格 × 图谱（笛卡尔积）
        for i in range(min(each_count, len(faq_data))):
            for j in range(min(2, len(price_data))):
                for k in range(min(2, len(graph_qa_list))):
                    if len(pools["faq_price_graph"]) >= each_count:
                        break
                    qa = await self._generate_triple_qa(faq_data[i], price_data[j], graph_qa_list[k])
                    pools["faq_price_graph"].append({
                        "question": qa.get("question", ""),
                        "answer": qa.get("answer", ""),
                        "platform": platform,
                        "channel": "faq_price_graph"
                    })

        return pools
