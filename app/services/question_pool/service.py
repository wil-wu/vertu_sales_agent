import asyncio
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
    PRICE_QUESTION_REWRITE_PROMPT
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

    async def _fetch_faq(self, query: str, collection_name: str, top_k: int = 1000) -> List[dict]:
        """获取 FAQ 数据 - 带重试机制"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
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
                return items
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    logger.warning(f"FAQ查询失败(尝试{attempt+1}/{max_retries}): {e}, {wait_time}秒后重试")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"FAQ查询最终失败: {e}")
                    return []  # 失败时返回空列表

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
        platform: str,
        count: int
    ) -> dict:
        """生成问题池 CSV 文件 - 只包含屏幕相关内容"""
        logger.info(f"开始生成问题池: platform={platform}, count={count}")

        config = PLATFORM_CONFIG.get(platform)
        if not config:
            raise ValueError(f"不支持的平台: {platform}")

        # 并发获取三个渠道的数据（直接查询屏幕相关内容）
        logger.info("开始查询屏幕相关数据...")

        # FAQ: 使用屏幕相关关键词查询
        screen_keywords = ["屏幕", "分辨率", "刷新率", "英寸", "尺寸"]
        faq_screen_related = []
        for i, keyword in enumerate(screen_keywords):
            data = await self._fetch_faq(keyword, config["faq_collection"], top_k=10)
            faq_screen_related.extend(data)
            # 添加延迟避免请求过快
            if i < len(screen_keywords) - 1:
                await asyncio.sleep(0.5)
        # 去重
        seen = set()
        unique = []
        for item in faq_screen_related:
            key = item.get("question", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        faq_screen_related = unique
        logger.info(f"FAQ 屏幕相关查询完成: {len(faq_screen_related)} 条")

        # Price: 使用屏幕相关关键词查询
        price_screen_related = []
        for keyword in screen_keywords:
            data = await self._fetch_price(keyword, config["price_index"], hits_per_page=10)
            price_screen_related.extend(data)
        # 去重
        seen = set()
        unique = []
        for item in price_screen_related:
            key = item.get("name", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        price_screen_related = unique
        logger.info(f"价格屏幕相关查询完成: {len(price_screen_related)} 条")

        # Graph: 使用标准产品列表查询图谱
        is_oversea = platform == "overseas"

        # 标准产品列表
        product_names = [
            "IVERTU",
            "METAVERTU",
            "METAVERTU 2",
            "Signature 4G",
            "Signature S",
            "VERTU AGENT Q",
            "VERTU AGENT IRONFLIP",
            "VERTU QUANTUM"
        ]

        logger.info(f"使用标准产品列表查询图谱: {product_names}")

        # 查询每个产品的图谱数据
        graph_screen_related = []
        for product_name in product_names:
            try:
                graph_data = await self._fetch_graph(product_name, is_oversea)
                graph_results = graph_data.get("data", {}).get("result", []) if isinstance(graph_data, dict) else []

                # 筛选包含屏幕属性的节点
                for item in graph_results:
                    if "p" in item:
                        p = item["p"]
                        if any(key in p for key in ["ScreenType", "ScreenSize", "Resolution"]):
                            graph_screen_related.append(item)
            except Exception as e:
                logger.warning(f"查询 {product_name} 图谱失败: {e}")

        logger.info(f"图谱屏幕相关筛选完成: {len(graph_screen_related)} 条")

        # 第二步：用筛选后的数据生成问答对
        logger.info("开始生成问答对...")

        all_questions = []

        # 从 FAQ 生成问答对
        for item in faq_screen_related:
            all_questions.append({
                "question": item["question"],
                "answer": item["answer"],
                "platform": platform,
                "channel": "faq"
            })

        # 从价格数据生成问答对（改写问题）
        for item in price_screen_related:
            rewritten_question = await self._rewrite_price_question(item["name"], item["price"])
            all_questions.append({
                "question": rewritten_question,
                "answer": f"{item['price']}元",
                "platform": platform,
                "channel": "price"
            })

        # 从图谱数据生成问答对
        if graph_screen_related:
            graph_qa_list = await self._generate_graph_qa({"data": {"result": graph_screen_related}})
            for qa in graph_qa_list:
                all_questions.append({
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "platform": platform,
                    "channel": "graph"
                })

        logger.info(f"问答对生成完成: {len(all_questions)} 条")

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
        filename = f"question_pool_{platform}_{timestamp}_{count}.csv"
        file_path = self.output_dir / filename

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "platform", "channel"])
            writer.writeheader()
            writer.writerows(all_questions)

        logger.info(f"问题池已生成: {file_path}, 共 {len(all_questions)} 条")

        # 统计各渠道数量
        breakdown = {
            "faq": sum(1 for q in all_questions if q["channel"] == "faq"),
            "price": sum(1 for q in all_questions if q["channel"] == "price"),
            "graph": sum(1 for q in all_questions if q["channel"] == "graph")
        }

        return {
            "file_path": str(file_path),
            "total_generated": len(all_questions),
            "breakdown": breakdown
        }
