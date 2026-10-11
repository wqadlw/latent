"""AI 提示词库路由（4 分类：outline / draft / rewrite / safety）- v4 增强版

新增功能：
- 提示词支持标签/自定义变量schema/使用次数/评分
- 内置变量参考列表接口
- 使用次数自增接口
- 评分接口
- 导入/导出接口
- 复制接口增强（含新字段）
"""
import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..constants import BUILTIN_VARIABLES
from ..database import get_db, now
from ..models import LlmConfig, PromptLibraryItem
from ..services.llm import LLMError, get_provider
from ..services.prompt_engine import VARIABLE_DESCRIPTIONS, extract_variables
from ..utils import to_dict

router = APIRouter(prefix="/api/prompt-library", tags=["AI提示词库"])


CATEGORIES = [
    {
        "key": "outline",
        "name": "大纲类提示词",
        "desc": "确定文章关键词与背景专业知识库，产出可执行的初稿大纲",
        "color": "#6366f1",
        "icon": "List",
    },
    {
        "key": "draft",
        "name": "专业初稿写作提示词",
        "desc": "基于大纲撰写文章初稿，结构完整、信息密度达标",
        "color": "#0ea5e9",
        "icon": "EditPen",
    },
    {
        "key": "rewrite",
        "name": "专业 AI 洗稿提示词",
        "desc": "去 AI 味精修，让 AI 搜索引擎能正确捕捉品牌关键词",
        "color": "#f59e0b",
        "icon": "MagicStick",
    },
    {
        "key": "illustration",
        "name": "文章配图提示词",
        "desc": "第8步文章配图：按封面与章节渲染文生图提示词（AI 生图）或图片关键字（网络搜图）",
        "color": "#ec4899",
        "icon": "Picture",
    },
    {
        "key": "geo",
        "name": "安全 · GEO 筛选提示词",
        "desc": "安全筛选 + GEO 筛选：合规检测/品牌露出优化，以及生成带信号的 GEO 软文与 GEO 评分优化（合并自原「安全筛选」与「GEO 软文」两类）",
        "color": "#14b8a6",
        "icon": "Shield",
    },
]


# 内置变量参考列表（供前端变量面板展示）
# 注意：此处必须与 services/prompt_engine.py 的 build_render_context 注入键、BUILTIN_VARIABLES 白名单保持一致，


class PromptIn(BaseModel):
    industry_id: int
    name: str
    category: str
    content: str
    variables: Any = "[]"
    variable_schema: Any = "[]"  # 自定义变量定义（支持 list 或 JSON 字符串）
    description: str = ""
    tags: str = ""
    is_default: int = 0
    rating: int = 0
    sort: int = 0

    @field_validator("variables", "variable_schema", mode="before")
    @classmethod
    def _to_json_str(cls, v):
        if v is None:
            return "[]"
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return v


@router.get("/categories")
def list_categories():
    return {"code": 0, "data": CATEGORIES}


@router.get("/builtin-variables")
def list_builtin_variables():
    """返回内置变量参考列表（供前端变量面板展示）"""
    # 按 group 分组
    groups = {}
    for v in BUILTIN_VARIABLES:
        g = v["group"]
        if g not in groups:
            groups[g] = []
        groups[g].append(v)
    return {"code": 0, "data": {"variables": BUILTIN_VARIABLES, "groups": groups}}


@router.get("")
def list_prompts(industry_id: int, category: Optional[str] = None,
                 keyword: Optional[str] = None, tag: Optional[str] = None,
                 db: Session = Depends(get_db)):
    q = db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == industry_id,
        PromptLibraryItem.is_deleted == 0
    )
    if category:
        q = q.filter(PromptLibraryItem.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (PromptLibraryItem.name.like(like)) |
            (PromptLibraryItem.description.like(like)) |
            (PromptLibraryItem.content.like(like))
        )
    if tag:
        q = q.filter(PromptLibraryItem.tags.like(f"%{tag}%"))
    items = q.order_by(PromptLibraryItem.sort.asc(), PromptLibraryItem.id.desc()).all()
    return {"code": 0, "data": [to_dict(i) for i in items]}


@router.post("")
def create_prompt(payload: PromptIn, db: Session = Depends(get_db)):
    data = payload.dict()
    it = PromptLibraryItem(**data)
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/{item_id}")
def update_prompt(item_id: int, payload: PromptIn, db: Session = Depends(get_db)):
    it = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "提示词不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{item_id}")
def delete_prompt(item_id: int, db: Session = Depends(get_db)):
    it = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "提示词不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.post("/{item_id}/default")
def set_default(item_id: int, db: Session = Depends(get_db)):
    it = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "提示词不存在")
    db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == it.industry_id,
        PromptLibraryItem.category == it.category,
        PromptLibraryItem.id != item_id,
    ).update({PromptLibraryItem.is_default: 0})
    it.is_default = 1
    db.commit()
    return {"code": 0, "msg": "已设为默认"}


@router.post("/sort")
def sort_prompts(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(PromptLibraryItem).filter(PromptLibraryItem.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


# ========== v4 新增：使用次数自增 ==========
@router.post("/{item_id}/use")
def increment_usage(item_id: int, db: Session = Depends(get_db)):
    """记录提示词被使用（使用次数+1，更新最后使用时间）"""
    it = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "提示词不存在")
    it.usage_count = (it.usage_count or 0) + 1
    it.last_used_time = now()
    db.commit()
    return {"code": 0, "msg": "已记录", "data": {"usage_count": it.usage_count}}


# ========== v4 新增：评分 ==========
@router.post("/{item_id}/rate")
def rate_prompt(item_id: int, payload: dict, db: Session = Depends(get_db)):
    """给提示词评分（0-5）"""
    it = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == item_id).first()
    if not it:
        raise HTTPException(404, "提示词不存在")
    rating = int(payload.get("rating", 0))
    if rating < 0 or rating > 5:
        raise HTTPException(400, "评分范围 0-5")
    it.rating = rating
    db.commit()
    return {"code": 0, "msg": "评分已更新"}


@router.post("/seed/{industry_id}")
def seed_defaults(industry_id: int, db: Session = Depends(get_db)):
    """一键灌入默认提示词模板（先清空该行业全部系统默认提示词，再写入 50 条耦合模板）。

    落实"删除所有提示词、重新编写可耦合系统"的要求：每次灌入都是一次干净替换。
    仅清除 is_default=1 的系统默认模板，保留用户自建（is_default=0）的提示词。
    """
    from ..services.prompt_engine import extract_variables
    from .prompt_defaults import DEFAULT_PROMPTS

    # 1) 先软删除该行业全部系统默认提示词（实现干净替换，不影响用户自建模板）
    db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == industry_id,
        PromptLibraryItem.is_deleted == 0,
        PromptLibraryItem.is_default == 1,
    ).update({PromptLibraryItem.is_deleted: 1})
    db.commit()

    # 2) 写入 50 条默认模板（变量列表由内容自动提取，保证与渲染上下文一致）
    created = 0
    for d in DEFAULT_PROMPTS:
        variables = json.dumps(extract_variables(d["content"]), ensure_ascii=False)
        it = PromptLibraryItem(
            industry_id=industry_id,
            name=d["name"],
            category=d["category"],
            content=d["content"],
            variables=variables,
            description=d.get("description", ""),
            tags=d.get("tags", ""),
            is_default=1,
            sort=0,
        )
        db.add(it)
        created += 1
    db.commit()
    return {"code": 0, "msg": f"已灌入 {created} 条默认提示词", "data": {"created": created}}


# ========== 变量自动检测 ==========
@router.post("/detect-variables")
def detect_variables(payload: dict):
    """从提示词模板内容中自动检测所有 {xxx} 占位符变量

    返回: [{"key": "xxx", "desc": "描述", "is_builtin": True/False}]
    """
    from ..services.prompt_engine import extract_variables
    content = payload.get("content", "")
    variables = extract_variables(content)
    return {"code": 0, "data": variables}


# ========== 测试渲染 ==========
@router.post("/test-render")
def test_render(payload: dict, db: Session = Depends(get_db)):
    """测试渲染提示词，返回渲染后的完整文本

    需要: prompt_id 或 content + industry_id
    可选: keyword_ids, knowledge_item_ids 等模拟上下文
    """
    from ..services.prompt_engine import build_render_context, render_prompt, unresolved_variables

    prompt_id = payload.get("prompt_id")
    content = payload.get("content", "")
    industry_id = payload.get("industry_id")

    if prompt_id:
        p = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == prompt_id).first()
        if not p:
            raise HTTPException(404, "提示词不存在")
        content = p.content
        industry_id = p.industry_id
    elif not content:
        raise HTTPException(400, "prompt_id 或 content 必填一项")

    if not industry_id:
        raise HTTPException(400, "industry_id 必填")

    # 构造一个临时 task 对象用于 build_render_context
    class _MockTask:
        pass
    mock_task = _MockTask()
    mock_task.platform_id = payload.get("platform_id", 0)
    mock_task.account_id = payload.get("account_id", 0)
    mock_task.persona_id = payload.get("persona_id", 0)
    mock_task.keyword_ids = ",".join(str(x) for x in payload.get("keyword_ids", []))
    mock_task.knowledge_item_ids = ",".join(str(x) for x in payload.get("knowledge_item_ids", []))
    mock_task.outline_content = payload.get("outline_content", "")
    mock_task.draft_content = payload.get("draft_content", "")
    mock_task.rewrite_content = payload.get("rewrite_content", "")
    mock_task.final_content = payload.get("final_content", "")

    context = build_render_context(db, mock_task, industry_id)
    # 合并自定义变量（覆盖同名内置变量），使预览能反映自定义变量值
    custom_vars = payload.get("custom_vars") or {}
    if isinstance(custom_vars, dict) and custom_vars:
        context.update(custom_vars)
    rendered = render_prompt(content, context)
    unresolved = unresolved_variables(content, context)
    return {"code": 0, "data": {"rendered": rendered, "variables_used": list(context.keys()), "unresolved": unresolved}}


# ========== 复制提示词 ==========
@router.post("/{prompt_id}/duplicate")
def duplicate_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """复制一条提示词（生成副本，名称加 (副本) 后缀）"""
    p = db.query(PromptLibraryItem).filter(PromptLibraryItem.id == prompt_id).first()
    if not p:
        raise HTTPException(404, "提示词不存在")
    new_p = PromptLibraryItem(
        industry_id=p.industry_id,
        name=p.name + " (副本)",
        category=p.category,
        content=p.content,
        variables=p.variables,
        variable_schema=p.variable_schema,
        description=p.description,
        tags=p.tags,
        is_default=0,
        sort=p.sort + 1,
    )
    db.add(new_p)
    db.commit()
    db.refresh(new_p)
    return {"code": 0, "data": to_dict(new_p), "msg": "复制成功"}


# ========== v4 新增：导出 ==========
@router.get("/export")
def export_prompts(industry_id: int, category: Optional[str] = None, db: Session = Depends(get_db)):
    """导出提示词为 JSON"""
    q = db.query(PromptLibraryItem).filter(
        PromptLibraryItem.industry_id == industry_id,
        PromptLibraryItem.is_deleted == 0
    )
    if category:
        q = q.filter(PromptLibraryItem.category == category)
    items = q.order_by(PromptLibraryItem.sort.asc()).all()
    data = []
    for it in items:
        data.append({
            "name": it.name,
            "category": it.category,
            "content": it.content,
            "variables": it.variables,
            "variable_schema": it.variable_schema,
            "description": it.description,
            "tags": it.tags,
            "is_default": it.is_default,
        })
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=prompts_export.json"}
    )


# ========== v4 新增：导入 ==========
@router.post("/import")
def import_prompts(payload: dict, db: Session = Depends(get_db)):
    """批量导入提示词（JSON 数组）"""
    industry_id = payload.get("industry_id")
    data = payload.get("data", [])
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")
    if not isinstance(data, list):
        try:
            data = json.loads(data) if isinstance(data, str) else []
        except Exception:
            raise HTTPException(400, "data 格式错误，应为 JSON 数组") from None

    created = 0
    errors = []
    for i, item in enumerate(data):
        name = (item.get("name") or "").strip()
        category = (item.get("category") or "").strip()
        content = item.get("content") or ""
        if not name or not category:
            errors.append(f"第{i+1}条: 名称或分类为空")
            continue
        if category not in ["outline", "draft", "rewrite", "illustration", "geo"]:
            errors.append(f"第{i+1}条: 分类 {category} 不合法")
            continue
        it = PromptLibraryItem(
            industry_id=industry_id,
            name=name,
            category=category,
            content=content,
            variables=item.get("variables", "[]"),
            variable_schema=item.get("variable_schema", "[]"),
            description=item.get("description", ""),
            tags=item.get("tags", ""),
            is_default=item.get("is_default", 0),
            sort=i,
        )
        db.add(it)
        created += 1
    db.commit()
    return {
        "code": 0,
        "msg": f"成功导入 {created} 条提示词" + (f"，{len(errors)} 条失败" if errors else ""),
        "data": {"created": created, "errors": errors},
    }


# ========== AI 写提示词（让 AI 为系统写标准提示词模板） ==========
# 用元提示词约束被调用的 LLM：只能使用白名单变量、符合类目职责与产出契约，
# 保证 AI 生成的提示词直接可被系统的渲染引擎正确替换、耦合生产链路。
_CATEGORY_CONTRACT = {
    "outline": (
        "职责：基于关键词与知识库，产出可执行的软文大纲（多级标题结构，含引言/正文分点/收尾）。\n"
        "关键变量：{keywords} {knowledge_content} {geo_signals} {platform_word_min} {platform_word_max} "
        "{brand_name} {creation_rules}。\n"
        "产出：直接输出大纲正文（用 # / ## 分层），不要解释。"
    ),
    "draft": (
        "职责：基于大纲撰写软文初稿，结构完整、信息密度达标、可读性强。\n"
        "关键变量：{outline_content} {keywords} {knowledge_content} {brand_info} {geo_signals} "
        "{platform_word_min} {platform_word_max} {creation_rules}。\n"
        "产出：直接输出文章初稿正文，不要解释。"
    ),
    "rewrite": (
        "职责：对初稿做「去 AI 味」精修，让 AI 搜索引擎能正确捕捉品牌关键词与可信信号。\n"
        "关键变量：{draft_content} {rewrite_content} {anti_ai_rules} {brand_name} {keywords} "
        "{geo_signals} {creation_rules}。\n"
        "产出：直接输出精修后的文章正文，不要解释。"
    ),
    "geo": (
        "职责：安全 · GEO 筛选终稿——合规检测 + 品牌露出优化 + GEO 评分优化，输出可直接发布的最终形态。\n"
        "关键变量：{final_content} 或 {rewrite_content} {geo_signals} {compliance_rules} "
        "{expected_recommendation} {brand_name} {brand_official_url} {contact_phone}。\n"
        "硬性产出契约：必须按顺序输出以下四个段落（标题严格一致，系统将自动解析回填）：\n"
        "  ## 优化后标题\n  （一行最终标题）\n  ## 优化后正文\n  （完整最终正文）\n"
        "  ## GEO 评分（0-100）\n  （一个数字）\n  ## 优化建议\n  （若干条优化建议）"
    ),
    "illustration": (
        "职责：文章配图提示词——按「封面 / 各章节」渲染可直接粘贴到即梦/通义万相/Midjourney 的文生图提示词。\n"
        "关键变量：{section_title} {section_content} {style_label} {brand_name} {aspect_ratio} "
        "{image_size} {image_position} {platform_name} {keywords}。\n"
        "产出：直接输出该张配图的文生图提示词（中文），不要解释。"
    ),
}


def _build_prompt_meta_prompt(category: str, requirement: str) -> str:
    """构造约束 AI 生成标准提示词模板的元提示词。"""
    cat = next((c for c in CATEGORIES if c["key"] == category), None)
    cat_name = cat["name"] if cat else category
    cat_contract = _CATEGORY_CONTRACT.get(category, "职责：通用软文生产提示词。")
    # 白名单变量块（键 + 描述）
    var_lines = []
    for k in sorted(BUILTIN_VARIABLES):
        var_lines.append(f"- {{{k}}}：{VARIABLE_DESCRIPTIONS.get(k, '自定义变量')}")
    var_block = "\n".join(var_lines)
    req_block = f"\n# 用户对这条提示词的额外要求\n{requirement.strip()}\n" if requirement and requirement.strip() else ""

    return f"""你是一位顶尖的提示词工程师，专门为「多行业软文生产系统」编写可被系统直接渲染的高质量提示词模板。

# 系统背景
该系统用提示词模板驱动大模型（DeepSeek 等）生产可被 AI 搜索引擎正确收录、引用、推荐的 GEO 软文。
模板中的 {{变量名}} 会在运行时被系统自动替换为真实上下文（行业 / 平台 / 品牌 / 关键词 / 知识库 / 规则 / 已生成内容 / 目标客户画像等）。

# 你要生成的提示词类别
类别 key：{category}
类别名称：{cat_name}
类别职责与产出契约：
{cat_contract}
{req_block}
# 允许的变量白名单（只能使用以下 {{xxx}}，禁止自创变量名；未列出的变量会被系统原样保留造成污染）
{var_block}

# 严格要求
1. 只能使用上方白名单中的变量，不得自创变量名。
2. 模板必须是「可直接交给大模型执行的完整指令」，简体中文，结构清晰（用 # 标题分层）。
3. 必须充分利用该类别职责对应的关键变量，使生成的软文贴合平台调性与品牌信号。
4. 只输出提示词模板正文本身，不要输出任何解释、不要使用 ``` 代码块包裹、不要加前缀。
5. 若用户给了额外要求，必须满足；但不得引入白名单外的变量。

请直接输出提示词模板正文："""


class GeneratePromptIn(BaseModel):
    industry_id: int
    category: str
    requirement: str = ""   # 用户对该提示词的描述/要求
    name: str = ""          # 可选，便于前端回显
    config_id: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


def _resolve_llm(db: Session, industry_id: int, config_id: Optional[int]) -> Optional[LlmConfig]:
    """解析行业生效的 LLM 配置。"""
    if config_id:
        c = db.query(LlmConfig).filter(
            LlmConfig.id == config_id, LlmConfig.industry_id == industry_id,
            LlmConfig.is_deleted == 0,
        ).first()
        if c:
            return c
    c = db.query(LlmConfig).filter(
        LlmConfig.industry_id == industry_id, LlmConfig.is_deleted == 0,
        LlmConfig.is_default == 1,
    ).first()
    if not c:
        c = db.query(LlmConfig).filter(
            LlmConfig.industry_id == industry_id, LlmConfig.is_deleted == 0,
            LlmConfig.status == 1,
        ).first()
    return c


@router.post("/generate")
def generate_prompt(payload: GeneratePromptIn, db: Session = Depends(get_db)):
    """用 AI 为系统写一条标准提示词模板（变量白名单约束）。

    返回的 content 可直接由前端「保存为提示词」写入提示词库；同时返回
    非白名单变量列表，便于前端警示用户修正后再保存。
    """
    if payload.category not in ["outline", "draft", "rewrite", "geo", "illustration"]:
        raise HTTPException(400, f"不支持的 category：{payload.category}")
    c = _resolve_llm(db, payload.industry_id, payload.config_id)
    if not c or not c.api_key:
        return {
            "code": 0,
            "data": {
                "ok": False,
                "need_config": True,
                "content": "",
                "non_builtin": [],
                "error": "未配置 LLM（如 DeepSeek）API Key。请先在「设置 → LLM 配置」填写，"
                         "或手动编写提示词（仍可使用白名单变量）。",
            },
        }
    meta = _build_prompt_meta_prompt(payload.category, payload.requirement)
    kwargs = {}
    if payload.temperature is not None:
        kwargs["temperature"] = payload.temperature
    if payload.max_tokens is not None:
        kwargs["max_tokens"] = payload.max_tokens
    try:
        text = get_provider({
            "provider": c.provider, "api_key": c.api_key, "base_url": c.base_url,
            "model": c.model,
            "temperature": float(c.temperature) if c.temperature not in (None, "") else 0.7,
            "max_tokens": c.max_tokens, "timeout": c.timeout,
        }).generate(meta, **kwargs)
    except LLMError as e:
        return {"code": 0, "data": {"ok": False, "need_config": False, "content": "", "non_builtin": [], "error": str(e)}}

    # 去掉可能的 ``` 包裹（部分模型仍会包裹）
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.lower().startswith("prompt"):
            text = text[text.find("\n"):].strip()

    # 校验变量是否全部在白名单内
    detected = extract_variables(text)
    non_builtin = [v["key"] for v in detected if not v["is_builtin"]]
    return {
        "code": 0,
        "data": {
            "ok": True,
            "need_config": False,
            "content": text,
            "name": payload.name,
            "category": payload.category,
            "non_builtin": non_builtin,
            "config_name": c.name,
            "provider": c.provider,
            "model": c.model,
        },
    }
