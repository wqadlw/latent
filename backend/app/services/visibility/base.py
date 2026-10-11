"""
可见性采集 Provider 抽象

为什么需要抽象层
----------------
「AI 怎么回答我的问题」这件事，获取方式差异极大：
- 有官方 API 的（DeepSeek / OpenAI 兼容网关）→ 直接调用
- 只有网页版的（豆包 / 文心 / 元宝）→ 人工复制粘贴（走 ``manual`` 通道）
- 离线 / 测试 → 确定性 mock

如果每接一个引擎就在业务代码里写一遍 if/else，加第三个引擎时就会失控。
Provider 层把「怎么拿到回答」与「拿到之后怎么分析」彻底分开：
无论回答从哪来，落库结构、信源解析、指标计算**完全一致**。

稳定错误码
----------
调用失败时返回**稳定错误码**而不是自由文本。原因：
自由文本无法聚合统计，「AI 调用失败」在运维看板上应该能按类型分组，
而不是变成一堆看不出共性的字符串。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..llm import LLMError, get_provider

# ---- provider 类型 ----
PROVIDER_LLM_CHAT = "llm_chat"        # OpenAI 兼容网关问答（主力通道）
PROVIDER_MOCK = "mock"                # 确定性 mock（测试 / 离线演示）
PROVIDER_MANUAL = "manual"            # 人工粘贴（不通过本模块调用，仅作为来源标记）

# ---- 稳定错误码 ----
ERR_NOT_CONFIGURED = "ai_model_not_configured"
ERR_AUTH = "ai_provider_auth_failed"
ERR_RATE_LIMIT = "ai_provider_rate_limited"
ERR_TIMEOUT = "ai_provider_timeout"
ERR_REQUEST = "ai_provider_request_failed"
ERR_EMPTY = "ai_provider_empty_response"

# 默认提问模板：刻意引导模型**标注引用来源**。
# 不要求它给出处，返回的就是一段无出处的散文，信源分析直接废掉。
DEFAULT_PROMPT_TEMPLATE = """请回答以下问题：

{keyword}

要求：
- 给出详细、专业的回答，覆盖主流方案与关键判断依据
- 如果有值得推荐的品牌或方案，请明确提及并说明理由
- 若参考了网络资料，请在正文中用 [1] [2] 标注，并在结尾以「来源：」列出完整链接
- 如有数据、案例或行业报告，请一并给出
- 结尾用一句话给出明确结论"""


def build_default_prompt(keyword: str) -> str:
    return DEFAULT_PROMPT_TEMPLATE.format(keyword=(keyword or "").strip())


@dataclass
class SourceData:
    """一条被 AI 引用的信源。"""
    source_type: str = ""
    citation_key: str = ""
    title: str = ""
    url: str = ""
    domain: str = ""
    site_name: str = ""
    snippet: str = ""
    summary: str = ""
    content_excerpt: str = ""
    published_at: str = ""
    rank: int = 0
    rank_score: float = 0.0
    authority_level: str = ""
    is_owned: int = 0
    metadata_json: Dict[str, Any] = field(default_factory=dict)

    def to_db(self) -> Dict[str, Any]:
        """转成可直接写库的字典（JSON 字段序列化）。"""
        data = asdict(self)
        data["metadata_json"] = json.dumps(data.get("metadata_json") or {}, ensure_ascii=False)
        return data


@dataclass
class VisibilityResult:
    """一次探测的原始结果。"""
    provider_type: str = ""
    provider_key: str = ""
    model_id: str = ""
    answer_text: str = ""
    sources: List[SourceData] = field(default_factory=list)
    latency_ms: int = 0
    usage: Dict[str, Any] = field(default_factory=dict)
    raw_request: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_code: str = ""

    @property
    def ok(self) -> bool:
        return not self.error_code


def classify_error(exc: Exception) -> str:
    """把异常映射成稳定错误码。

    只区分**处理方式不同**的类别：鉴权失败要换密钥、限流要退避、超时要放宽时限，
    其余归入通用请求失败。过度细分反而没人看。
    """
    if isinstance(exc, LLMError):
        msg = str(exc)
        if "未配置 api_key" in msg:
            return ERR_NOT_CONFIGURED
        m = re.search(r"HTTP\s*(\d{3})", msg)
        if m:
            code = int(m.group(1))
            if code in (401, 403):
                return ERR_AUTH
            if code == 429:
                return ERR_RATE_LIMIT
            if code >= 500:
                return ERR_REQUEST
        if "超时" in msg or "timeout" in msg.lower():
            return ERR_TIMEOUT
        if "网络错误" in msg:
            return ERR_REQUEST
        return ERR_REQUEST
    if isinstance(exc, TimeoutError):
        return ERR_TIMEOUT
    return ERR_REQUEST


class BaseVisibilityProvider:
    """所有可见性采集 provider 的基类。"""

    provider_type = "base"
    provider_key = "base"

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None,
                 options: Optional[Dict[str, Any]] = None):
        self.llm_config = dict(llm_config or {})
        self.options = dict(options or {})

    def collect(self, keyword: str, prompt: Optional[str] = None) -> VisibilityResult:  # pragma: no cover - 抽象
        raise NotImplementedError


class LLMChatProvider(BaseVisibilityProvider):
    """OpenAI 兼容网关问答（DeepSeek / OpenAI / 通义 / Kimi 通用）。

    这是本系统的主力通道：用户配好一套 LLM 配置，就能自动探测
    「这个模型在回答目标问题时会不会提到我们、引用了谁」。
    """

    provider_type = PROVIDER_LLM_CHAT

    def __init__(self, llm_config=None, options=None):
        super().__init__(llm_config, options)
        self.provider_key = str(self.llm_config.get("provider") or "deepseek")
        self.model_id = str(self.llm_config.get("model") or "")

    def collect(self, keyword: str, prompt: Optional[str] = None) -> VisibilityResult:
        final_prompt = (prompt or "").strip() or build_default_prompt(keyword)
        result = VisibilityResult(
            provider_type=self.provider_type,
            provider_key=self.provider_key,
            model_id=self.model_id,
        )
        if not self.llm_config.get("api_key"):
            result.error_code = ERR_NOT_CONFIGURED
            return result

        started = time.time()
        try:
            provider = get_provider(self.llm_config)
            answer = provider.generate(
                final_prompt,
                temperature=float(self.options.get("temperature", 0.3)),
                max_tokens=int(self.options.get("max_tokens", 2000)),
            )
        except Exception as exc:  # noqa: BLE001
            result.error_code = classify_error(exc)
            result.latency_ms = int((time.time() - started) * 1000)
            result.raw_request = {"prompt": final_prompt}
            result.raw_response = {"error": str(exc)[:500]}
            return result

        result.latency_ms = int((time.time() - started) * 1000)
        result.answer_text = (answer or "").strip()
        result.raw_request = {"prompt": final_prompt}
        result.raw_response = {"answer": result.answer_text[:8000]}
        if not result.answer_text:
            result.error_code = ERR_EMPTY
        return result


class MockVisibilityProvider(BaseVisibilityProvider):
    """确定性 mock：不联网、不花钱，用于测试与离线演示。

    返回内容刻意包含 Markdown 链接与来源行，以便覆盖信源解析路径。
    """

    provider_type = PROVIDER_MOCK

    def __init__(self, llm_config=None, options=None):
        super().__init__(llm_config, options)
        self.provider_key = "mock"
        self.model_id = "mock-visibility-v1"

    def collect(self, keyword: str, prompt: Optional[str] = None) -> VisibilityResult:
        kw = (keyword or "").strip() or "示例问题"
        answer = (
            f"关于「{kw}」，行业内主流的判断依据包括极限真空度、抽速与长期运行稳定性。\n\n"
            "推荐方案：优先考虑有公开实测数据与完整交付案例的厂商，"
            "并要求提供第三方检测报告与现场验收记录。\n\n"
            "据行业报告统计，选型失误导致的返工成本约占项目总投入的 15% [1]。\n\n"
            "来源：\n"
            "[1] 行业选型指南 - https://www.example.com/guide/selection\n"
            "[2] 第三方检测机构 - https://www.testlab.cn/reports/vacuum\n"
            "[3] 行业资讯 - https://news.example.org/articles/vacuum-trend\n"
        )
        return VisibilityResult(
            provider_type=self.provider_type,
            provider_key=self.provider_key,
            model_id=self.model_id,
            answer_text=answer,
            latency_ms=0,
            usage={},
            raw_request={"prompt": prompt or build_default_prompt(kw)},
            raw_response={"answer": answer},
        )


_PROVIDERS: Dict[str, type] = {
    PROVIDER_LLM_CHAT: LLMChatProvider,
    PROVIDER_MOCK: MockVisibilityProvider,
}

PROVIDER_CHOICES = [
    {"value": PROVIDER_LLM_CHAT, "label": "LLM 问答探测", "desc": "调用已配置的模型提问，自动解析回答与引用来源"},
    {"value": PROVIDER_MOCK, "label": "模拟探测", "desc": "离线确定性输出，用于演示与测试"},
    {"value": PROVIDER_MANUAL, "label": "人工粘贴", "desc": "在监测任务里手动粘贴 AI 回答（保留通道）"},
]


def get_provider_cls(provider_type: str) -> type:
    """按类型取 provider 类，未知类型回退到 mock（宁可返回可识别的占位，也不要崩）。"""
    return _PROVIDERS.get((provider_type or "").strip().lower(), MockVisibilityProvider)


def list_provider_types() -> List[Dict[str, str]]:
    return list(PROVIDER_CHOICES)
