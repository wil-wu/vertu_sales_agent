import csv
import json
import logging
from datetime import datetime
from enum import Enum
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


class ProductType(Enum):
    """产品类型"""
    IVERTU = "IVERTU"
    METAVERTU = "METAVERTU"
    METAVERTU_2 = "METAVERTU 2"
    SIGNATURE_4G = "Signature 4G"
    SIGNATURE_S = "Signature S"
    VERTU_AGENT_Q = "VERTU AGENT Q"
    VERTU_AGENT_IRONFLIP = "VERTU AGENT IRONFLIP"
    VERTU_QUANTUM = "VERTU QUANTUM"


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
    async def _fetch_faq(self, query: str, collection_name: str, top_k: int = 1000) -> List[dict]:
        """获取 FAQ 数据 - 全量查询"""
        response = await httpx_async_client.post(
            self.faq_url,
            json={"query": query, "collection_names": [collection_name], "top_k": top_k},
            timeout=30.0
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
        logger.info(f"FAQ 全量查询完成: {len(items)} 条")
        return items

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _fetch_price(self, query: str, index_name: str, hits_per_page: int = 1000) -> List[dict]:
        """获取价格数据 - 全量查询"""
        all_items = []
        page = 1

        while True:
            response = await httpx_async_client.post(
                self.price_url,
                json={"query": query, "index_name": index_name, "hits_per_page": hits_per_page, "page": page},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("hits", [])
            if not hits:
                break

            for hit in hits:
                all_items.append({
                    "name": hit.get("name", ""),
                    "price": hit.get("price", 0)
                })

            # 如果返回的数据少于每页数量，说明已经获取完所有数据
            if len(hits) < hits_per_page:
                break

            page += 1

            # 安全限制：最多获取 10 页
            if page > 10:
                break

        logger.info(f"价格全量查询完成: {len(all_items)} 条")
        return all_items

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

    async def _generate_pool_for_product(
        self,
        product_name: str,
        platform: str
    ) -> List[dict]:
        """为单个产品生成问答对 - 只包含屏幕相关内容"""
        logger.info(f"开始处理产品: {product_name}")

        config = PLATFORM_CONFIG.get(platform)
        if not config:
            raise ValueError(f"不支持的平台: {platform}")

        # 并发获取三个渠道的数据（全量查询）
        faq_data = await self._fetch_faq(product_name, config["faq_collection"])
        price_data = await self._fetch_price(product_name, config["price_index"])
        is_oversea = platform == "overseas"
        graph_data = await self._fetch_graph(product_name, is_oversea)

        # 统计原始数据
        graph_results = graph_data.get("data", {}).get("result", []) if isinstance(graph_data, dict) else []

        # 第一步：筛选屏幕相关内容
        logger.info(f"[{product_name}] 开始筛选屏幕相关内容...")

        # 筛选 FAQ 中与屏幕相关的内容
        faq_screen_related = []
        for item in faq_data:
            content = f"问题: {item.get('question', '')}\n答案: {item.get('answer', '')}"
            if await self._filter_screen_related("FAQ", content):
                faq_screen_related.append(item)
        logger.info(f"[{product_name}] FAQ 筛选完成: {len(faq_screen_related)}/{len(faq_data)} 条与屏幕相关")

        # 筛选价格中与屏幕相关的内容
        price_screen_related = []
        for item in price_data:
            content = f"商品名称: {item.get('name', '')}"
            if await self._filter_screen_related("价格", content):
                price_screen_related.append(item)
        logger.info(f"[{product_name}] 价格筛选完成: {len(price_screen_related)}/{len(price_data)} 条与屏幕相关")

        # 筛选图谱中与屏幕相关的内容
        graph_screen_related = []
        for item in graph_results:
            # 构建图谱内容描述
            content_parts = []
            if "p" in item:
                p = item["p"]
                if "ScreenType" in p:
                    content_parts.append(f"屏幕类型: {p['ScreenType']}")
                if "ScreenSize" in p:
                    content_parts.append(f"屏幕尺寸: {p['ScreenSize']}")
                if "Resolution" in p:
                    content_parts.append(f"分辨率: {p['Resolution']}")
            content = "; ".join(content_parts) if content_parts else "无屏幕信息"
            if await self._filter_screen_related("图谱", content):
                graph_screen_related.append(item)
        logger.info(f"[{product_name}] 图谱筛选完成: {len(graph_screen_related)}/{len(graph_results)} 条与屏幕相关")

        # 第二步：用筛选后的数据生成问答对
        logger.info(f"[{product_name}] 开始生成问答对...")

        all_questions = []

        # 从 FAQ 生成问答对
        for item in faq_screen_related:
            all_questions.append({
                "question": item["question"],
                "answer": item["answer"],
                "platform": platform,
                "channel": "faq",
                "product": product_name
            })

        # 从价格数据生成问答对（改写问题）
        for item in price_screen_related:
            rewritten_question = await self._rewrite_price_question(item["name"], item["price"])
            all_questions.append({
                "question": rewritten_question,
                "answer": f"{item['price']}元",
                "platform": platform,
                "channel": "price",
                "product": product_name
            })

        # 从图谱数据生成问答对
        if graph_screen_related:
            graph_qa_list = await self._generate_graph_qa({"data": {"result": graph_screen_related}})
            for qa in graph_qa_list:
                all_questions.append({
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "platform": platform,
                    "channel": "graph",
                    "product": product_name
                })

        logger.info(f"[{product_name}] 生成完成: {len(all_questions)} 条问答对")
        return all_questions

    async def generate_pool(
        self,
        platform: str,
        count: int
    ) -> dict:
        """生成问题池 CSV 文件 - 遍历所有产品，只包含屏幕相关内容"""
        logger.info(f"开始生成问题池: platform={platform}, count={count}")
        logger.info(f"将遍历以下产品: {[p.value for p in ProductType]}")

        # 遍历所有产品类型
        all_questions = []
        for product_type in ProductType:
            product_questions = await self._generate_pool_for_product(product_type.value, platform)
            all_questions.extend(product_questions)

        logger.info(f"所有产品处理完成，共 {len(all_questions)} 条问答对")

        # 去重：相同 question 只保留一个
        seen = set()
        unique = []
        for qa in all_questions:
            q = qa["question"].lower().strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(qa)
        all_questions = unique
        logger.info(f"去重后: {len(all_questions)} 条")

        # 如果总数超过 count，随机选择
        if len(all_questions) > count:
            import random
            all_questions = random.sample(all_questions, count)
            logger.info(f"随机抽样后: {len(all_questions)} 条")

        # 生成 CSV 文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"question_pool_all_products_{platform}_{timestamp}_{count}.csv"
        file_path = self.output_dir / filename

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "platform", "channel", "product"])
            writer.writeheader()
            writer.writerows(all_questions)

        logger.info(f"问题池已生成: {file_path}, 共 {len(all_questions)} 条")

        # 统计各渠道数量
        breakdown = {
            "faq": sum(1 for q in all_questions if q["channel"] == "faq"),
            "price": sum(1 for q in all_questions if q["channel"] == "price"),
            "graph": sum(1 for q in all_questions if q["channel"] == "graph")
        }

        # 统计各产品数量
        product_breakdown = {}
        for q in all_questions:
            product = q.get("product", "unknown")
            product_breakdown[product] = product_breakdown.get(product, 0) + 1

        return {
            "file_path": str(file_path),
            "total_generated": len(all_questions),
            "breakdown": breakdown,
            "product_breakdown": product_breakdown
        }
