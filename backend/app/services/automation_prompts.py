"""
自动化提示词：可编辑存储 + 解析覆盖（页面编辑即时生效于后续运行）。

设计要点：
- 每个流程 / 专家角色用到的提示词都落库到 automation_prompt 表，页面可编辑、可复制；
- 运行时 get_studio_prompts / resolve_studio_prompt 优先取 DB 中的 content，
  覆盖 services/doubao_studio.py 里的默认常量；
- 正文模板保留 {brand_policy} / {mode_goal} / {expert_team} 等占位符，
  resolver 按当前发布模式注入；{issues}/{count}/{round}/{directives} 等由调用点 .format 填充；
- OFFICIAL_MDX_PROMPT 单独 resolver（占位符由 render_prompt 渲染，不在本层注入）。
"""
from ..models import AutomationPrompt
from .prompt_engine import get_brand_policy, get_mode_goal


# —— 精细化阶段提示词默认正文（含角色设定 / 输出格式约束 / 质量检查点）——
# 仅作「自动化指挥中心」可编辑底座与后续引擎接入；当前编排已覆盖选题/撰写/审核，
# 调研与搜索优化为独立可编辑模板，便于按需开启增强。
_RESEARCH_DEFAULT = """\
# 角色设定
你是资深行业调研员（主编团队·调研角色）。基于给定背景资料，快速提炼「值得写的选题」与「可佐证的事实锚点」。

# 输入
- 行业背景、品牌资产、目标客户画像、竞品/关键词、知识库条目。

# 输出格式约束
请严格输出 JSON：
{
  "topics": [{"angle":"选题角度","why":"为什么值得写","evidence":"可佐证的数据/案例来源"}],
  "facts": ["可引用的关键数据/案例（须标注来源或说明可溯源）"],
  "keywords": ["建议覆盖的核心关键词（用于 GEO）"]
}

# 质量检查点
1. 每个选题必须有「证据锚点」，禁止无来源夸大；
2. 关键词须与品牌/产品/行业强相关，便于 AI 检索推荐；
3. 不出现联系方式、不自我夸赞、不使用极限词。"""

_SEARCH_OPT_DEFAULT = """\
# 角色设定
你是 GEO（生成式引擎优化）专家。任务：把终稿改造成「更容易被 AI 搜索引擎推荐并引用」的结构。

# 输入
- 终稿正文、目标关键词、用户常问的意图问题。

# 输出格式约束
1. 标题信息量：用「疑问式 / 数据式 / 场景式」标题，包含核心关键词；
2. 结构化：用清晰小标题（H2/H3），每段回答一个明确问题；
3. FAQ：文末给 3 组「用户问 AI 的问题 → 直接答案」；
4. 实体密度：品牌名/产品名/核心参数自然出现，关键词密度 2-4%；
5. 保留原文事实，不编造数据。

# 质量检查点
- 每节小标题像一个真实搜索问题；
- 关键结论可被单独引用（独立成句）；
- 品牌实体与可量化论据齐备，利于 AI 摘要。"""

_QUALITY_GATE_DEFAULT = """\
# 角色设定
你是合规官，负责终稿上线前的硬闸门检查。

# 检查清单（任一项命中即不过审）
1. 违禁词 / 敏感词（政治、医疗断言、绝对化用语）；
2. 硬广特征：联系方式（电话/微信/邮箱/网址）、引导加购、限时促销；
3. 极限词：最/第一/唯一/顶级/国家级 等（专业技术词如「绝对压力」除外）；
4. 数据可溯：所有关键数据须有来源或可溯源，禁止虚构；
5. 平台特规：按发布模式（geo/platform/green）执行对应软文与品牌提及约束。

# 输出
逐项给出 通过/不通过 + 理由；若有问题，列出精确修改建议（定位到句）。"""


# 提示词元数据（不含正文；正文在 seed 时从 doubao_studio / prompt_engine 常量懒加载）。
# 字段：(key, category, name, expert_role, step_no, sort_order)
# category：team(专家团队) / system(创作总纲) / stage(写手逐阶段) / planner(主编智能体)
#           / writer(写手改写) / revise(整改指令) / mdx(官网 MDX 模板)
PROMPT_META = [
    ("EXPERT_TEAM_DESC", "team", "专家团队配置（多角色协同）", "主编", 0, 10),
    ("SYSTEM_PROMPT", "system", "创作系统提示词（豆包/模拟路径）", "写手", 0, 20),
    ("DEEPSEEK_MASTER_PROMPT", "system", "DeepSeek 创作总纲（API 路径）", "写手", 0, 22),
    ("STAGE_outline", "stage", "① 选题大纲（逐阶段指令·写手）", "写手", 1, 30),
    ("STAGE_draft", "stage", "② 初稿（逐阶段指令·写手）", "写手", 2, 31),
    ("STAGE_depolish", "stage", "③ 去AI味精修（逐阶段指令·写手）", "写手", 3, 32),
    ("STAGE_geo", "stage", "④ GEO强化+过审（逐阶段指令·写手）", "写手", 4, 33),
    ("STAGE_research", "stage", "① 选题调研（主编·调研角色）", "主编", 1, 29),
    ("STAGE_search_opt", "stage", "⑤ 搜索优化·GEO增强（GEO优化师）", "GEO优化师", 5, 34),
    ("QUALITY_GATE_PROMPT", "revise", "⑥ 质量检查点（合规官硬闸门）", "合规官", 6, 41),
    ("REVISE_PROMPT", "revise", "整改指令（豆包/模拟路径）", "主编", 6, 40),
    ("PLANNER_SYSTEM", "planner", "主编·系统提示词（总协调）", "主编", 0, 50),
    ("PLANNER_CLARIFY_PROMPT", "planner", "①b 主编·明晰选题（创作简报）", "主编", 1, 51),
    ("PLANNER_OUTLINE_PROMPT", "planner", "② 主编·拟定大纲", "主编", 2, 52),
    ("PLANNER_REVIEW_PROMPT", "planner", "⑥ 主编·自然语言评审", "主编", 6, 53),
    ("PLANNER_DIRECTIVE_PROMPT", "planner", "⑦ 主编·整改指令（给写手）", "主编", 7, 54),
    ("WRITER_APPLY_PROMPT", "writer", "写手·按主编指令改写", "写手", 7, 60),
    ("OFFICIAL_MDX_PROMPT", "mdx", "官网 MDX 自动化模板", "主编", 6, 70),
]


# ------------------------------------------------------------
#  种子（首次写入默认；不覆盖用户已编辑内容）
# ------------------------------------------------------------
def seed_automation_prompts(db) -> None:
    """把默认提示词写入 automation_prompt 表（幂等：已存在则跳过，仅补全 default_content）。"""
    from .doubao_studio import (
        EXPERT_TEAM_DESC, SYSTEM_PROMPT, DEEPSEEK_MASTER_PROMPT,
        STAGE_PROMPTS, REVISE_PROMPT, PLANNER_SYSTEM, PLANNER_CLARIFY_PROMPT,
        PLANNER_OUTLINE_PROMPT, PLANNER_REVIEW_PROMPT, PLANNER_DIRECTIVE_PROMPT,
        WRITER_APPLY_PROMPT,
    )
    from .prompt_engine import OFFICIAL_MDX_PROMPT

    value_map = {
        "EXPERT_TEAM_DESC": EXPERT_TEAM_DESC,
        "SYSTEM_PROMPT": SYSTEM_PROMPT,
        "DEEPSEEK_MASTER_PROMPT": DEEPSEEK_MASTER_PROMPT,
        "STAGE_outline": STAGE_PROMPTS.get("outline", ""),
        "STAGE_draft": STAGE_PROMPTS.get("draft", ""),
        "STAGE_depolish": STAGE_PROMPTS.get("depolish", ""),
        "STAGE_geo": STAGE_PROMPTS.get("geo", ""),
        "STAGE_research": _RESEARCH_DEFAULT,
        "STAGE_search_opt": _SEARCH_OPT_DEFAULT,
        "QUALITY_GATE_PROMPT": _QUALITY_GATE_DEFAULT,
        "REVISE_PROMPT": REVISE_PROMPT,
        "PLANNER_SYSTEM": PLANNER_SYSTEM,
        "PLANNER_CLARIFY_PROMPT": PLANNER_CLARIFY_PROMPT,
        "PLANNER_OUTLINE_PROMPT": PLANNER_OUTLINE_PROMPT,
        "PLANNER_REVIEW_PROMPT": PLANNER_REVIEW_PROMPT,
        "PLANNER_DIRECTIVE_PROMPT": PLANNER_DIRECTIVE_PROMPT,
        "WRITER_APPLY_PROMPT": WRITER_APPLY_PROMPT,
        "OFFICIAL_MDX_PROMPT": OFFICIAL_MDX_PROMPT,
    }

    for key, category, name, expert_role, step_no, sort_order in PROMPT_META:
        content = value_map.get(key, "")
        existing = db.query(AutomationPrompt).filter(AutomationPrompt.key == key).first()
        if existing:
            if not existing.default_content:
                existing.default_content = content
            continue
        db.add(AutomationPrompt(
            key=key, category=category, name=name,
            expert_role=expert_role, step_no=step_no,
            content=content, default_content=content, sort_order=sort_order,
        ))
    db.commit()


# ------------------------------------------------------------
#  解析（运行时按 DB 覆盖 + 模式注入）
# ------------------------------------------------------------
def _resolve_expert_team(db) -> str:
    if db is not None:
        row = db.query(AutomationPrompt).filter(
            AutomationPrompt.key == "EXPERT_TEAM_DESC", AutomationPrompt.is_deleted == 0
        ).first()
        if row and row.content:
            return row.content
    from .doubao_studio import EXPERT_TEAM_DESC
    return EXPERT_TEAM_DESC


def _inject_common(text, mode: str, db=None) -> str:
    if not isinstance(text, str):
        return text
    bp = get_brand_policy(mode)
    mg = get_mode_goal(mode)
    et = _resolve_expert_team(db)
    return text.replace("{expert_team}", et).replace("{brand_policy}", bp).replace("{mode_goal}", mg)


def _resolve_single(db, key: str, default_text: str, mode: str) -> str:
    content = default_text
    if db is not None:
        row = db.query(AutomationPrompt).filter(
            AutomationPrompt.key == key, AutomationPrompt.is_deleted == 0
        ).first()
        if row and row.content:
            content = row.content
    return _inject_common(content, mode, db)


def resolve_studio_prompts(mode: str = "geo", db=None) -> dict:
    """返回与 doubao_studio._RAW_PROMPTS 同构的 dict（已注入品牌策略/模式目标/专家团队，并叠加 DB 覆盖）。"""
    from .doubao_studio import (
        SYSTEM_PROMPT, DEEPSEEK_MASTER_PROMPT, REVISE_PROMPT, STAGE_PROMPTS,
        PLANNER_SYSTEM, PLANNER_CLARIFY_PROMPT, PLANNER_OUTLINE_PROMPT,
        PLANNER_REVIEW_PROMPT, PLANNER_DIRECTIVE_PROMPT, WRITER_APPLY_PROMPT,
    )
    stage_keys = ["STAGE_outline", "STAGE_draft", "STAGE_depolish", "STAGE_geo"]
    stage_out = {}
    for k in stage_keys:
        sub = k.split("_", 1)[1]
        stage_out[sub] = _resolve_single(db, k, STAGE_PROMPTS.get(sub, ""), mode)
    return {
        "SYSTEM_PROMPT": _resolve_single(db, "SYSTEM_PROMPT", SYSTEM_PROMPT, mode),
        "DEEPSEEK_MASTER_PROMPT": _resolve_single(db, "DEEPSEEK_MASTER_PROMPT", DEEPSEEK_MASTER_PROMPT, mode),
        "STAGE_PROMPTS": stage_out,
        "REVISE_PROMPT": _resolve_single(db, "REVISE_PROMPT", REVISE_PROMPT, mode),
        "PLANNER_SYSTEM": _resolve_single(db, "PLANNER_SYSTEM", PLANNER_SYSTEM, mode),
        "PLANNER_CLARIFY_PROMPT": _resolve_single(db, "PLANNER_CLARIFY_PROMPT", PLANNER_CLARIFY_PROMPT, mode),
        "PLANNER_OUTLINE_PROMPT": _resolve_single(db, "PLANNER_OUTLINE_PROMPT", PLANNER_OUTLINE_PROMPT, mode),
        "PLANNER_REVIEW_PROMPT": _resolve_single(db, "PLANNER_REVIEW_PROMPT", PLANNER_REVIEW_PROMPT, mode),
        "PLANNER_DIRECTIVE_PROMPT": _resolve_single(db, "PLANNER_DIRECTIVE_PROMPT", PLANNER_DIRECTIVE_PROMPT, mode),
        "WRITER_APPLY_PROMPT": _resolve_single(db, "WRITER_APPLY_PROMPT", WRITER_APPLY_PROMPT, mode),
    }


_DEFAULT_PLANNER = {
    "PLANNER_SYSTEM": None, "PLANNER_CLARIFY_PROMPT": None,
    "PLANNER_OUTLINE_PROMPT": None, "PLANNER_REVIEW_PROMPT": None,
    "PLANNER_DIRECTIVE_PROMPT": None, "WRITER_APPLY_PROMPT": None,
}


def resolve_studio_prompt(db, key: str, mode: str) -> str:
    """单一提示词解析（供 DeepSeek 引擎中直接引用常量的位置使用）。"""
    from .doubao_studio import (
        PLANNER_SYSTEM, PLANNER_CLARIFY_PROMPT, PLANNER_OUTLINE_PROMPT,
        PLANNER_REVIEW_PROMPT, PLANNER_DIRECTIVE_PROMPT, WRITER_APPLY_PROMPT,
    )
    defaults = {
        "PLANNER_SYSTEM": PLANNER_SYSTEM,
        "PLANNER_CLARIFY_PROMPT": PLANNER_CLARIFY_PROMPT,
        "PLANNER_OUTLINE_PROMPT": PLANNER_OUTLINE_PROMPT,
        "PLANNER_REVIEW_PROMPT": PLANNER_REVIEW_PROMPT,
        "PLANNER_DIRECTIVE_PROMPT": PLANNER_DIRECTIVE_PROMPT,
        "WRITER_APPLY_PROMPT": WRITER_APPLY_PROMPT,
    }
    return _resolve_single(db, key, defaults.get(key, ""), mode)


def get_resolved_context(db, mode: str = "geo") -> dict:
    """返回某发布模式下，会被注入到提示词的背景内容（供前端页面展示 / 预览注入后效果）。"""
    from .prompt_engine import get_brand_policy, get_mode_goal
    return {
        "mode": mode,
        "brand_policy": get_brand_policy(mode),
        "mode_goal": get_mode_goal(mode),
        "expert_team": _resolve_expert_team(db),
    }


def resolve_official_mdx_prompt(db=None) -> str:
    """官网 MDX 模板解析（占位符由 prompt_engine.render_prompt 渲染，本层不注入品牌策略）。"""
    if db is not None:
        row = db.query(AutomationPrompt).filter(
            AutomationPrompt.key == "OFFICIAL_MDX_PROMPT", AutomationPrompt.is_deleted == 0
        ).first()
        if row and row.content:
            return row.content
    from .prompt_engine import OFFICIAL_MDX_PROMPT
    return OFFICIAL_MDX_PROMPT


# ------------------------------------------------------------
#  页面接口：列表 / 更新 / 重置
# ------------------------------------------------------------
def get_automation_prompts(db, category: str = None) -> list:
    q = db.query(AutomationPrompt).filter(AutomationPrompt.is_deleted == 0)
    if category:
        q = q.filter(AutomationPrompt.category == category)
    rows = q.order_by(AutomationPrompt.sort_order, AutomationPrompt.id).all()
    out = []
    for r in rows:
        out.append({
            "key": r.key,
            "category": r.category,
            "name": r.name,
            "expert_role": r.expert_role,
            "step_no": r.step_no,
            "content": r.content or "",
            "default_content": r.default_content or "",
            "sort_order": r.sort_order,
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        })
    return out


def get_automation_prompt(db, key: str):
    return db.query(AutomationPrompt).filter(
        AutomationPrompt.key == key, AutomationPrompt.is_deleted == 0
    ).first()


def update_automation_prompt(db, key: str, content: str) -> bool:
    r = get_automation_prompt(db, key)
    if not r:
        return False
    r.content = content
    db.commit()
    return True


def reset_automation_prompt(db, key: str) -> bool:
    r = get_automation_prompt(db, key)
    if not r:
        return False
    r.content = r.default_content or ""
    db.commit()
    return True
