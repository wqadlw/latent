"""
LLM 服务层：可插拔大模型供应商抽象（同步阻塞，便于在 FastAPI 路由直接调用）

设计目标
--------
- 让系统「既能手动复制提示词给 AI（网页/客户端）→ 粘贴结果回系统」，
  「也能一键调用配置的 LLM（默认 DeepSeek）直接生成」，两种模式并存、互不排斥。
- 供应商以 OpenAI 兼容协议 /v1/chat/completions 为基准实现，DeepSeek 直接复用，
  OpenAI / 通义千问 / 月之暗面 等兼容网关只需切换 base_url + model 即可。

依赖：仅使用 Python 标准库 urllib，零额外安装，避免污染环境。
"""
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional


class LLMError(Exception):
    """LLM 调用相关错误（未配置 / 网络 / 鉴权 / 限流 / 解析失败）"""


class BaseLLMProvider:
    """所有供应商的基类，统一接口。"""

    name = "base"

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}

    def generate(self, prompt: str, **kwargs) -> str:
        """单轮补全：给定一段提示词文本，返回模型回复。"""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """多轮对话：给定 messages 列表。"""
        raise NotImplementedError

    def test(self) -> Dict[str, Any]:
        """连通性测试：用极短 prompt 验证 api_key / base_url 是否有效。"""
        try:
            out = self.generate("ping", max_tokens=8)
            return {"ok": True, "reply": (out or "")[:80]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI 兼容协议供应商（DeepSeek / OpenAI / 通义千问 / 月之暗面 通用实现）。

    仅 POST 到 {base_url}/chat/completions，解析 choices[0].message.content。
    """

    name = "openai_compatible"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = (config.get("api_key") or "").strip()
        self.base_url = (config.get("base_url") or "https://api.openai.com").rstrip("/")
        self.model = config.get("model") or "gpt-4o-mini"
        self.timeout = int(config.get("timeout") or 60)
        # DeepSeek v4 thinking 机制：通过 thinking 参数开启「推理模式」，替代旧的
        # deepseek-reasoner 模型名（2026/07/24 弃用）。仅当配置显式携带时透传。
        self.thinking = config.get("thinking")   # None / {"type": "enabled"}
        self.reasoning_effort = config.get("reasoning_effort") or ""  # "high" / "medium" / "low"

    @property
    def _endpoint(self) -> str:
        # DeepSeek 默认网关：https://api.deepseek.com  （已含 /v1）
        # OpenAI / 通义千问 / 月之暗面 默认网关通常需补 /v1
        base = self.base_url
        if base.endswith("/v1") or base.endswith("/v1/"):
            return f"{base.rstrip('/')}/chat/completions"
        # 兼容「填了 https://api.deepseek.com 即可」的简洁写法
        if "deepseek.com" in base and not base.endswith("/v1"):
            return f"{base}/v1/chat/completions"
        return f"{base}/v1/chat/completions"

    def _post(self, messages: List[Dict[str, str]], **kwargs) -> str:
        if not self.api_key:
            raise LLMError("未配置 api_key，请先在 LLM 设置中填写密钥")
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 4000)),
            "stream": False,
        }
        # DeepSeek v4：开启推理（主编/规划角色用）。非 v4 或写手未携带时跳过。
        if self.thinking is not None:
            body["thinking"] = self.thinking
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self._endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:400]
            raise LLMError(f"HTTP {e.code}：{detail}")
        except urllib.error.URLError as e:
            raise LLMError(f"网络错误：{getattr(e, 'reason', e)}")
        except TimeoutError:
            raise LLMError(f"请求超时（>{self.timeout}s）")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise LLMError(f"返回非 JSON：{raw[:200]}")
        if not isinstance(payload, dict) or "choices" not in payload or not payload["choices"]:
            raise LLMError(f"返回缺少 choices：{raw[:200]}")
        return payload["choices"][0]["message"]["content"]

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return self._post(messages, **kwargs)


# DeepSeek 复用 OpenAI 兼容实现（仅默认值不同）
class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"

    def __init__(self, config: Dict[str, Any]):
        cfg = dict(config or {})
        cfg.setdefault("base_url", "https://api.deepseek.com")
        cfg.setdefault("model", "deepseek-v4-pro")
        super().__init__(cfg)


# 供应商注册表：新增供应商只需在此登记
_PROVIDERS = {
    "deepseek": DeepSeekProvider,
    "openai": OpenAICompatibleProvider,
    "qwen": OpenAICompatibleProvider,   # 通义千问（DashScope OpenAI 兼容）
    "moonshot": OpenAICompatibleProvider,  # 月之暗面 Kimi
    "openai_compatible": OpenAICompatibleProvider,
}

# 各供应商默认 base_url（用户留空时使用）
DEFAULT_BASE_URL = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode",
    "moonshot": "https://api.moonshot.cn",
}

PROVIDER_CHOICES = [
    {"value": "deepseek", "label": "DeepSeek", "default_base_url": DEFAULT_BASE_URL["deepseek"], "default_model": "deepseek-v4-pro"},
    {"value": "openai", "label": "OpenAI 兼容", "default_base_url": DEFAULT_BASE_URL["openai"], "default_model": "gpt-4o-mini"},
    {"value": "qwen", "label": "通义千问", "default_base_url": DEFAULT_BASE_URL["qwen"], "default_model": "qwen-plus"},
    {"value": "moonshot", "label": "月之暗面 Kimi", "default_base_url": DEFAULT_BASE_URL["moonshot"], "default_model": "moonshot-v1-8k"},
]


def normalize_config(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """补全供应商默认 base_url / model，避免用户未填时调用失败。"""
    cfg = dict(llm_config or {})
    provider = (cfg.get("provider") or "deepseek").lower()
    if not cfg.get("base_url"):
        cfg["base_url"] = DEFAULT_BASE_URL.get(provider, "")
    if not cfg.get("model"):
        cfg["model"] = next(
            (p["default_model"] for p in PROVIDER_CHOICES if p["value"] == provider),
            "deepseek-v4-pro",
        )
    return cfg


def get_provider(llm_config: Dict[str, Any]) -> BaseLLMProvider:
    """根据配置对象构造供应商实例。

    llm_config 至少含 provider 字段；api_key / base_url / model 可选（有默认值）。
    """
    cfg = normalize_config(llm_config)
    provider = (cfg.get("provider") or "deepseek").lower()
    cls = _PROVIDERS.get(provider, DeepSeekProvider)
    return cls(cfg)


def generate_with_config(llm_config: Dict[str, Any], prompt: str, **kwargs) -> str:
    """便捷函数：用一份配置直接生成文本。"""
    return get_provider(llm_config).generate(prompt, **kwargs)
