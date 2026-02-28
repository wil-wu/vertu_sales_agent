import re
from pathlib import Path
from typing import NamedTuple

import fasttext
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage


class LanguageResult(NamedTuple):
    """语言检测结果。"""

    lang: str
    """首选语言 ISO 639-1 代码，如 'en', 'zh'。"""
    score: float
    """首选语言的置信度 [0, 1]。"""
    candidates: list[tuple[str, float]]
    """前 k 个候选 (语言代码, 置信度)，便于排查。"""


class LanguageDetector:
    """
    基于 FastText 的语言检测器。
    """

    _LABEL_PREFIX = "__label__"

    def __init__(self, model_path: str | Path) -> None:
        """
        Args:
            model_path: 预训练 lid 模型路径（.bin 或 .ftz）。
        """
        self._model_path = Path(model_path)
        self._model: fasttext.FastText._FastText | None = None

    @property
    def model(self) -> fasttext.FastText._FastText:
        """懒加载模型。"""
        if self._model is None:
            if not self._model_path.exists():
                raise FileNotFoundError(
                    f"FastText 语言检测模型不存在: {self._model_path}。"
                    "请从 https://fasttext.cc/docs/en/language-identification.html 下载。"
                )
            self._model = fasttext.load_model(str(self._model_path))
        return self._model

    def detect(self, text: str) -> str:
        """
        检测文本语言，返回 ISO 639-1 语言代码。

        Args:
            text: 待检测文本（UTF-8）。

        Returns:
            语言代码，如 'en', 'zh'；空或过短文本返回 'unknown'。
        """
        result = self.detect_with_confidence(text)
        return result.lang

    def detect_with_confidence(self, text: str, k: int = 5) -> LanguageResult:
        """
        检测文本语言并返回置信度及前 k 个候选。

        Args:
            text: 待检测文本（UTF-8）。
            k: 返回前 k 个候选数量，便于排查歧义或低置信度情况。

        Returns:
            LanguageResult(lang, score, candidates)。空或过短文本返回 unknown 且 candidates 为空。
        """
        text = self._preprocess(text)
        if not text:
            return LanguageResult("unknown", 0.0, [])
        try:
            labels, scores = self.model.predict(text, k=k)
            if not labels or not scores.size:
                return LanguageResult("unknown", 0.0, [])
            candidates: list[tuple[str, float]] = []
            for i, label in enumerate(labels):
                sc = float(scores[i]) if i < scores.size else 0.0
                if label.startswith(self._LABEL_PREFIX):
                    lang_code = label[len(self._LABEL_PREFIX) :]
                else:
                    lang_code = label
                candidates.append((lang_code, sc))
            lang, score = candidates[0]
            return LanguageResult(lang, score, candidates)
        except Exception as e:
            print(f"Language detection error: {e}")
            return LanguageResult("unknown", 0.0, [])
    
    def _preprocess(self, text: str, max_len: int = 500) -> str | None:
        text = text.strip()
        text = text.replace("\n", " ").replace("\r", " ").replace("\x00", "")
        
        # 去除 URL
        text = re.sub(r"https?://\S+", "", text)
        # 去除邮箱
        text = re.sub(r"\S+@\S+\.\S+", "", text)
        # 去除 emoji
        text = re.sub(r"[^\w\s\u4e00-\u9fff\u3040-\u30ff]", "", text)
        # 合并多余空格
        text = re.sub(r"\s+", " ", text).strip()
        # 截断
        text = text[:max_len]
        
        return text


class LanguageTranslator:
    """
    基于 LLM 的翻译器。

    使用初始化时传入的翻译 prompt 模板（含 {target_lang}、{text}），将文本翻译为目标语言。
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        translate_system_prompt: str,
    ) -> None:
        """
        Args:
            chat_model: 用于翻译的对话模型（如 ChatOpenAI）。
            translate_system_prompt: 翻译系统提示词，需包含占位符 {target_lang} 与 {text}。
        """
        self._chat_model = chat_model
        self._translate_system_prompt = translate_system_prompt

    def translate(self, text: str, target_lang: str) -> str:
        """
        将文本翻译为目标语言。

        Args:
            text: 待翻译文本。
            target_lang: 目标语言，如 'en', 'zh'（与 prompt 中 target_lang 含义一致）。

        Returns:
            翻译后的文本。空输入返回空字符串。
        """
        text = text.strip() if text else ""
        if not text:
            return ""
        prompt = self._translate_system_prompt.format(
            target_lang=target_lang,
            text=text,
        )
        response = self._chat_model.invoke([SystemMessage(content=prompt)])
        content = response.content
        return content.strip() if isinstance(content, str) else str(content).strip()

    async def atranslate(self, text: str, target_lang: str) -> str:
        """translate 的异步版本。"""
        text = text.strip() if text else ""
        if not text:
            return ""
        prompt = self._translate_system_prompt.format(
            target_lang=target_lang,
            text=text,
        )
        response = await self._chat_model.ainvoke([SystemMessage(content=prompt)])
        content = response.content
        return content.strip() if isinstance(content, str) else str(content).strip()


class MarkdownHelper:
    """
    Markdown 辅助工具。
    """

    @staticmethod
    def remove_markdown_links(text: str) -> str:
        """去除 markdown 链接 [text](url)，保留链接文字"""
        return re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)

    @staticmethod
    def extract_markdown_links(text: str) -> list[str]:
        """从文本中提取 markdown 链接（含 [text](url) 和 ![alt](url)）"""
        return re.findall(r"!?\[[^\]]*\]\([^\)]*\)", text)
