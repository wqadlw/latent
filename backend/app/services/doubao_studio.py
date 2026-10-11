# -*- coding: utf-8 -*-
"""
浏览器工作室编排服务（BrowserStudio）

职责：把"AI 创作（选题→初稿→精修→GEO→过审）→ 回传存档 → 搜狐号自动发布"整条流水线
编排为一个可被状态跟踪 / 失败重试 / 结果回溯的自动化流程。

设计要点：
  - 创作引擎可插拔（WritingEngine 接口）：
      · DeepSeek（默认）：纯 LLM API 调用，复用系统提示词库 + LLM 抽象层，
        按 outline→draft→rewrite→geo 四阶段产出终稿，无需浏览器/ cookie；
      · 豆包（浏览器自动化）：经 Playwright 驱动豆包 Web 对话（多轮），
        登录态复用 PlatformCredential（platform='doubao'）；
      · 模拟演示：MockDoubaoAdapter，无需浏览器即可端到端验证整条流水线。
    未配置 DeepSeek 时自动回退到模拟演示，保持流程可跑（不硬性阻断）。
  - 全量上下文：创建 Run 时自动吃进行业下全部内容（目标需求/品牌/平台/人设/知识库/
    关键词/规则库/客户画像/意图问题），经 build_render_context 实时拉取最新正文。
  - 输出契约：豆包路径用 ===FINAL_TITLE=== / ===FINAL_CONTENT=== 包裹（extract_final 抽取）；
    DeepSeek 路径解析 geo 提示词的 4 段结构（优化后标题/正文/GEO评分/优化建议）。
  - 9 步状态机：connect → outline → draft → depolish → geo → review → revise → confirm → publish，
    每步写 BrowserStudioStep（status/attempts/last_error/result_json/log），且每轮 AI 返回原文落库到
    Run 对应字段（outline_content/draft_content/rewrite_content/geo_content/final_content），前端逐段回看。
  - 搜狐发布：复用既有 publisher.publish + publish._run_publish（保留人工审核闸门 + auto_publish 开关）。
  - 仅标准库 + 可选 playwright（懒加载，未安装时优雅降级）。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..brand_config import BRAND_NAME, REGION
from ..database import SessionLocal
from ..models import (
    Account,
    BrandAsset,
    BrowserStudioRun,
    BrowserStudioStep,
    ContentAsset,
    IntentQuestion,
    Keyword,
    KnowledgeItem,
    Persona,
    Platform,
    PlatformCredential,
    ProductionTask,
    PublishJob,
    TargetPersona,
)
from ..routers.publish import _run_publish
from ..services.automation_prompts import (
    resolve_official_mdx_prompt,
    resolve_studio_prompt,
)
from ..services.generation import (
    _parse_geo_finalize,
    _resolve_llm_config,
    assign_default_prompts,
    generate_step_text,
)
from ..services.llm_scheduler import _eligible_configs, mock_call, scheduler_generate
from ..services.orchestrator import get_step_defs, run_quality_gate
from ..services.prompt_engine import _format_brand_info, build_render_context, get_brand_policy
from ..services.publisher import _browser_launch_kwargs, publisher
from . import pipeline as pipeline_svc


# ============================================================
#  解耦载体：各模块（选题→调研→撰写→审核→发布→搜索优化）之间显式传递的产物
#  - 每个阶段只读取自己需要的输入、写入自己的输出，不依赖隐藏的全局状态；
#  - 编排器(orchestrate_run)持有唯一一份 StudioContext，按步骤推进并写入运行记录。
# ============================================================
@dataclass
class StudioContext:
    """自动化流水线各阶段的显式数据契约载体。"""
    run_id: int = 0
    subject: str = ""
    mode: str = "geo"                       # geo / platform / green
    output_format: str = "markdown"         # markdown / mdx
    briefing: str = ""                      # ① 全量背景简报（发给主编）
    clarified: str = ""                     # ①b 主编·创作简报
    outline: str = ""                       # ② 大纲
    draft: str = ""                         # ③ 初稿
    polished: str = ""                      # ④ 去AI味精修稿
    final_title: str = ""                   # ⑤ 终稿标题
    final_content: str = ""                 # ⑤ 终稿正文
    geo_score: int = 0                      # ⑥ GEO 评分
    issues: list = field(default_factory=list)   # ⑥/⑦ 评审问题清单
    mdx_filename: str = ""                  # 官网 MDX 文件名
    mdx_images: list = field(default_factory=list)  # 官网 MDX 配图文件名

    def to_ctx(self) -> dict:
        """转为引擎方法需要的上下文 dict（含 output_format / mode 等）。"""
        return {
            "subject": self.subject, "mode": self.mode,
            "output_format": self.output_format,
            "brand_name": "", "brand": "",
        }


# ============================================================
#  豆包 Web 选择器（按实际 DOM 调整；支持 DOUBAO_SELECTORS_JSON 覆盖）
# ============================================================
DOUBAO_SELECTORS: Dict[str, Any] = {
    # 豆包官网首页与对话页（以官网实际地址为准，可经环境变量覆盖）
    "url": "https://www.doubao.com/",
    "chat_url": "https://www.doubao.com/chat/",
    # 输入框候选选择器（依次尝试，命中第一个）
    "input": ["textarea", "div[contenteditable='true']", "[role='textbox']", "textarea[placeholder]"],
    # 消息气泡候选选择器（取全部，最后一条即最新回复）
    "messages": [
        "div[class*='message']", "[class*='chat-message']",
        "[data-testid*='message']", "[class*='conversation-item']",
    ],
    # 停止生成按钮（用于判断回复是否结束；可选）
    "stop_btn": "[class*='stop']",
    # 发送按钮（可选；默认用 Enter 发送）
    "send_btn": "button[class*='send']",
}


def _load_selectors() -> Dict[str, Any]:
    sel = dict(DOUBAO_SELECTORS)
    env = os.environ.get("DOUBAO_SELECTORS_JSON")
    if env:
        try:
            custom = json.loads(env)
            if isinstance(custom, dict):
                sel.update(custom)
        except Exception:
            pass
    return sel


# ============================================================
#  提示词契约（浏览器工作室专用）
#  设计：9 步流水线，每一阶段单独派发指令、单独回收 AI 原文。
#  - DeepSeek 引擎：复用系统提示词库（outline/draft/rewrite/geo 四类）+ LLM 抽象层；
#  - 豆包/模拟引擎：逐阶段发送 STAGE_PROMPTS，每阶段独立成稿。
# ============================================================
# ============================================================
#  专家团队（多角色协同）：由「主编」统一协调调度
#  - 主编（PLANNER / 总协调）：定方向、定大纲、终审把关、下达整改指令；不写正文。
#  - 写手（WRITER）：初稿 → 去 AI 味 → GEO 终稿 → 按指令改写；只执行不判断。
#  - 合规官（Compliance Officer）：平台合规红线——违禁词/硬广/站外引流/私人联系方式。
#  - GEO 优化师（GEO Optimizer）：被 AI 检索推荐的信号——关键词/FAQ/实体密度/意图覆盖。
#  - 数据核查员（Fact-Checker）：事实与数据不夸大、不虚构、可溯源。
#  真实管道里，合规官/GEO优化师/数据核查员的「检查」由代码自检 + 主编评审共同承担；
#  主编在评审与整改指令中，会明确「这是合规官指出的 / 这是 GEO 优化师建议的 / 这是数据核查员核对的」。
# ============================================================
EXPERT_TEAM_DESC = """本创作由一支「专家团队」协同完成，主编统一调度：

■ 主编（总协调）——把控选题方向、审核质量、下达整改指令。不写正文。
■ 写手——执行写作：初稿→去AI味→GEO终稿→按指令改写。只执行不判断。
■ 合规官——守红线：违禁词、硬广话术、站外引流、私人联系方式、软文营销特征。
■ GEO优化师——守信号：品牌实体密度、FAQ问答形态、意图问题覆盖、可被AI直接引用。
■ 数据核查员——守事实：每个关键数据可溯源、不夸大、不虚构。

三大纪律：
1. 读者价值优先——文章必须对读者有真实帮助，品牌信息自然融入而非硬塞。读者觉得有价值，平台不会判低质。
2. 模式决定尺度——geo模式品牌当主角（公司全称≥3次）；platform模式品牌当配角（≤2次、标题无品牌、带AIGC声明）；green模式品牌当彩蛋（≤2次、纯干货）。
3. 拒绝软文套路弧——禁止「痛点→只有它能解决→推荐购买」的叙事结构，禁止通篇围绕一家企业，禁止无佐证的优势堆砌。"""


# ============================================================
#  双模式发布：发布平台 code → 默认发布模式
#  - 内容平台（搜狐/知乎/网易/头条/微信/小红书/百家）一律走「平台合规模式」，
#    文章中立、有价值、品牌自然植入≤2次、标题无品牌、带 AIGC 声明，规避平台软文拒稿；
#  - 其它（自建站 / AI 抓取 / 未匹配）走「强品牌 GEO 模式」。
# ============================================================
PLATFORM_PUBLISH_MODE = {
    "sohu": "platform", "zhihu": "platform", "wangyi": "platform",
    "xiaohongshu": "platform", "wechat": "platform", "toutiao": "platform",
    "baijiahao": "platform",
    # 官网/自建站：自有阵地，强品牌 GEO 模式（但产出形态为 mdx，见 resolve_run_output_format）
    "official": "geo", "selfsite": "geo",
}


def resolve_run_publish_mode(run: BrowserStudioRun, db: Session = None) -> str:
    """解析某次运行的发布模式：优先 run.publish_mode → 平台 code 映射 → 默认 geo。"""
    _pm = getattr(run, "publish_mode", "") or ""
    if _pm in ("geo", "platform", "green"):
        return _pm
    code = (run.platform or "").strip().lower()
    if code in PLATFORM_PUBLISH_MODE:
        return PLATFORM_PUBLISH_MODE[code]
    return "geo"


def resolve_run_output_format(run: BrowserStudioRun, db: Session = None) -> str:
    """解析某次运行的产出形态：优先 run.output_format → 平台 code 映射 → 默认 markdown。"""
    _out = getattr(run, "output_format", "") or ""
    if _out in ("markdown", "mdx"):
        return _out
    code = (run.platform or "").strip().lower()
    if code in ("official", "selfsite"):
        return "mdx"
    return "markdown"


def get_auto_run(db: Session, run_id: int):
    """解析自动流运行记录（P2 并表后统一入口）。

    解析顺序：
      1. production_task(mode='auto')：新版运行 + 并表 cutover 后从 browser_studio_run
         迁移来的历史运行（按 id 或 legacy_run_id 匹配）；
      2. browser_studio_run：并表 cutover 前尚未迁移的历史运行（表仍存在时）。

    返回的可能是 ProductionTask 或 BrowserStudioRun 对象，二者列已 1:1 对齐，
    调用方以统一属性（run.subject / run.outline_content / ...）访问即可，无需区分类型。
    """
    run = db.query(ProductionTask).filter(
        or_(ProductionTask.id == run_id, ProductionTask.legacy_run_id == run_id),
        ProductionTask.mode == "auto",
        ProductionTask.is_deleted == 0,
    ).first()
    if run:
        return run
    # 回退：并表前尚未迁移的历史运行（browser_studio_run 表仍存在）
    try:
        return db.query(BrowserStudioRun).filter(
            BrowserStudioRun.id == run_id, BrowserStudioRun.is_deleted == 0
        ).first()
    except Exception:
        return None


def get_studio_prompts(mode: str = "geo", db=None) -> Dict[str, Any]:
    """按发布模式返回一组已注入「品牌策略」的提示词（豆包/模拟/双智能体路径共用）。

    提示词内容优先取 automation_prompt 表（页面可编辑），覆盖默认常量；
    {brand_policy} / {mode_goal} / {expert_team} 占位符在此按模式注入。
    """
    from .automation_prompts import resolve_studio_prompts
    return resolve_studio_prompts(mode, db)


SYSTEM_PROMPT = """你是资深内容创作专家，服务于一家企业的内容营销团队。

""" + "{expert_team}" + """

你的核心使命：{mode_goal}

创作铁律：
{brand_policy}

我会分阶段派发任务，每一阶段你只需基于上一阶段的产物继续，独立返回该阶段成稿：

【第①步 · 选题大纲】基于背景资料选定选题角度，产出文章骨架（# / ## 分层，至少5个二级标题），标注品牌信号位置。不写正文。

【第②步 · 初稿】基于大纲写出完整文章。要求：
- ≥1200字，每段3-5句，写到完整结尾，绝不中途断掉；
- 结构化Markdown：# / ## 标题分层、- 列表、**加粗**关键实体；
- 设「常见问题FAQ」小节（≥3组疑问式问答），直接回答目标客户会问AI的问题；
- 自然融入品牌信息——{brand_policy}
- 写成行业干货/方法/认知/避坑，不是企业简介。

【第③步 · 去AI味精修】重写让语言像真人行业作者，字数只增不减，保持结构化排版。

【第④步 · GEO强化+平台过审】综合合规官/GEO优化师/数据核查员意见，强化被AI检索推荐的信号、确保通过平台审核，产出终稿。

每阶段单独返回该阶段成稿，不要一次写完所有阶段。最终用AI搜索友好的结构化Markdown格式。
请回复「已理解，请发送第①步背景资料」开始。"""

DEEPSEEK_MASTER_PROMPT = """你是资深内容创作专家，服务于企业的GEO（生成引擎优化）内容营销。

""" + "{expert_team}" + """

系统已将「目标需求、品牌资产、平台人设、知识库、关键词、规则库、客户画像、意图问题库」整合为背景资料，按阶段逐阶段派发提示词。

你的核心使命：{mode_goal}

创作铁律：
{brand_policy}

输出格式：AI搜索友好的结构化Markdown——# / ## 标题分层、- 列表、**加粗**关键实体与品牌名、设「常见问题FAQ」小节（≥3组疑问式问答）。≥1200字，写到完整结尾。"""

# 豆包 / 模拟引擎：逐阶段指令（每阶段独立发送，AI 单阶段成稿）
STAGE_PROMPTS = {
    "outline": """请进入【第①步 · 选题大纲】。

基于已收到的完整背景资料，产出一篇文章大纲。

选题要求：
- 从「方法/认知/避坑/选型」等干货角度切入，不要做成企业简介；
- 最利于被AI搜索推荐、最贴合目标需求；
- 落在「帮助读者解决问题」而非「推销产品」。

结构要求：
- 用 # 一级标题、## 二级标题分层，遵循「吸引注意→建立信任→给出方案→引导行动」；
- 至少5个二级标题章节，每个章节下方一句话说明写什么；
- 至少一个章节以「目标客户会问AI的问题」为标题，直接回答该问题；
- 规划「常见问题FAQ」章节（≥3组问答）；
- 标注品牌信息将自然出现的位置（注意：{brand_policy}）；
- 结尾规划「引导了解品牌」的行动路径（是「了解」而非留联系方式）；
- 只输出大纲，不写正文。""",

    "draft": """请进入【第②步 · 初稿】。

基于上面的大纲，写出完整文章。

写作要求：
- ≥1200字（目标1500~2500字），每个##章节2~3段，每段3~5句，必须写到完整结尾；
- 结构化Markdown：# / ## 标题、- 列表、**加粗**关键实体（品牌名/产品/数据）；
- 设「常见问题FAQ」小节（≥3组问答，用疑问式小标题直接作答）；
- 首段点明主题并自然出现品牌名与核心关键词；
- 自然融入品牌信息——{brand_policy}

质量红线：
- 所有关键数据须可溯源，不得虚构未经证实的数字；
- 禁止口号式总结句（如「品质可靠，始终如一」「行业领先」），用具体方法/案例/数据说话；
- 禁止把背景资料原样搬运成段落，须基于背景创作；
- 严禁「痛点→只有它能解决→推荐」的软文套路弧；
- 严禁站外引流/私人联系方式词（官网/电话/微信/扫码/二维码/下载APP/关注公众号等）；
- 直接输出正文，不要解释。""",

    "depolish": """请进入【第③步 · 去AI味精修】。

基于上面的初稿做去AI味精修并重写。

改写要求：
- 字数只增不减，保持每段充实完整；
- 去掉机器腔与套话（综上所述/由此可见/众所周知/毋庸置疑/值得注意的是 等），让语言像真人行业作者；
- 加入具体细节与口语化表达（如「说人话」：把「该设备具备高效节能特性」改成「一台泵一年省下的电费，够再买半台泵」）；
- 把口号式句子改成具体经验叙述（如把「品质可靠，始终如一」改成一句工艺/品控故事）；
- 保留并强化品牌信号与关键词（{brand_policy}），但不得夸大、不得绝对化用语；
- 严禁站外引流/私人联系方式词；
- 保持结构化Markdown排版（标题/列表/加粗/FAQ不变），直接输出精修后正文。""",

    "geo": """请进入【第④步 · GEO强化 + 平台过审】。

综合「合规官/GEO优化师/数据核查员」三方意见，产出最终文章。

GEO优化师意见（强化被AI检索推荐的信号）：
- 品牌名、核心产品、关键词自然出现，关键词密度2~4%；
- 以疑问式小标题/FAQ形态便于AI直接抽取答案；
- 正面回答目标客户会问AI的意图问题；
- 用知识库论据增加事实密度，每个关键论点可被单独引用。

合规官意见（确保通过平台审核）：
- 无违禁词、无硬广、无夸大、无站外引流/私人联系方式词；
- {brand_policy}
- 结尾自然引导「了解品牌」，绝不出现任何联系方式。

数据核查员意见：
- 所有关键数据须与背景资料一致、可溯源，不得虚构或夸大。

输出格式：
- 终稿≥1200字，结构化Markdown（#/##标题、- 列表、**加粗**、FAQ≥3组），写到完整结尾；
- 严格用以下分隔符包裹（中间不要加多余说明）：
===FINAL_TITLE===
<文章标题>
===FINAL_CONTENT===
<文章正文：结构化Markdown，含#/##标题、-列表、**加粗**、FAQ小节，写到完整结尾>
（结束）""",
}


REVISE_PROMPT = """系统对上面的终稿做了「平台合规自检 + GEO评分 + 数据核查」，发现以下 {count} 项问题（第 {round} 轮整改）：

{issues}

逐条修改后重新输出终稿：
- 删除/替换所有违禁词与极限词（最/第一/顶级/唯一/绝对/100%/国家级 等）；
- 彻底删除站外引流/联系方式词（官网/电话/微信/扫码/二维码/下载APP/关注公众号 等）；
- 去AI套话，让语言更像真人；
- {brand_policy}；
- 补充可量化数据、意图问题覆盖、FAQ问答、清晰标题层级；
- 所有关键数据须可溯源，不得虚构；
- ≥1200字，写到完整结尾，FAQ≥3组齐全；
- 仍用分隔符包裹：
===FINAL_TITLE===
<文章标题>
===FINAL_CONTENT===
<文章正文：结构化Markdown，含#/##标题、-列表、**加粗**、FAQ小节，写到完整结尾>
（结束）"""


# ============================================================
#  双智能体提示词
#  - 主编（PLANNER）：明晰选题→定大纲→评审→整改指令。不写正文。thinking开启（推理模式）。
#  - 写手（WRITER）：初稿→去AI味→GEO终稿→按指令改写。只执行。thinking关闭（非推理，快省）。
# ============================================================
PLANNER_SYSTEM = """你是本团队的「主编/总协调」。你不写正文，负责三件事：

① 把模糊选题「明晰」成可执行的《创作简报》——选题角度、目标读者、GEO信号、合规雷区、品牌重点；
② 基于简报拟定文章大纲——逻辑骨架，≥5个二级标题；
③ 拿到写手终稿后，汇总合规官/GEO优化师/数据核查员的检查结论做评审，下达逐条可执行的整改指令。

你协调的团队：
- 写手：初稿→去AI味→GEO终稿→按指令改写（只执行不判断）
- 合规官：守红线——违禁词/硬广/站外引流/联系方式/软文特征
- GEO优化师：守信号——品牌实体/关键词/FAQ/意图覆盖/可引用性
- 数据核查员：守事实——数据可溯源/不夸大/不虚构

品牌宣传尺度（每次评审必查）：
{brand_policy}

你的产出面向「给人看/给写手执行」，不写文章正文。语言像一位有十年经验的行业主编在带团队。"""

# ①b 主编·明晰选题（输出创作简报）
PLANNER_CLARIFY_PROMPT = """请进入【主编·明晰选题】。

基于已收到的完整背景资料，把这次创作「明晰」成一份《创作简报》，只输出简报本身：

- **选题角度**：从「方法/认知/避坑/选型」等干货角度选定最利于被AI搜索推荐、最贴合目标需求的角度（不要企业简介）；
- **目标读者**：帮谁、解决他什么具体困惑；
- **核心信息**：读完这篇文章，读者应该获得的一个核心认知或方法；
- **GEO信号**：品牌名、产品名、关键词、可量化数据、FAQ问答形态——将在文中哪些位置植入；
- **合规雷区**：严禁联系方式/站外引流词；严禁口号式标语；严禁广告法极限词；严禁「痛点→只推它→推荐」软文套路弧；
- **品牌尺度**：{brand_policy}
- **数据口径**：所有关键数据须可溯源，不得虚构；
- **成功标准**：通过平台审核 + GEO评分≥70 + 读起来像真人行业作者。

用「-」分条，简洁（300字以内）。不要写正文。"""

# ② 主编·大纲（基于创作简报）
PLANNER_OUTLINE_PROMPT = """请进入【主编·拟定大纲】。

基于上面的《创作简报》与背景资料，拟定文章大纲：

- 用 # 一级标题、## 二级标题分层，遵循「吸引注意→建立信任→给出方案→引导行动」；
- 至少5个二级标题章节，每个章节下方一句话说明要写什么；
- 至少一个章节以「目标客户会问AI的问题」为标题，直接回答该问题；
- 规划「常见问题FAQ」章节（≥3组问答），确保结尾完整不截断；
- 标注品牌信息（{brand_policy}）将自然出现的位置；
- 结尾规划「引导了解品牌」的行动路径（是「了解」而非留联系方式）；
- 选题落在「帮助读者解决问题」而非「推销产品」；
- 只输出大纲，不写正文。"""

# ⑥ 主编·自然语言评审
PLANNER_REVIEW_PROMPT = """请进入【主编·评审】。

下面是写手交来的终稿，系统自检发现了以下问题：
{issues}

请站在主编视角，汇总合规官/GEO优化师/数据核查员的意见，写一段评审评语（180~280字）：

- 先一句话定调（整体达标 / 主要差距在哪）；
- 合规官：有没有违禁词、硬广、站外引流/联系方式残留？有没有软文套路弧（通篇推一家、结尾导向推荐）？
- GEO优化师：品牌实体、关键词、FAQ、意图覆盖够不够强？能不能被AI直接引用？
- 数据核查员：关键数据是否可溯源？有没有夸大/虚构？
- 品牌尺度：{brand_policy}
- 最后给写手一句总体整改方向。

不要重写正文，只做评审。"""

# ⑦ 主编·整改指令（给写手逐条可执行要求）
PLANNER_DIRECTIVE_PROMPT = """请进入【主编·整改指令】（第 {round} 轮）。

系统自检 + 你的评审指出以下问题：
{issues}

请给出逐条可执行的整改指令给写手（每条写清：谁提出的、改什么、怎么改、改成什么样）：

1. [合规官] 删/替换所有违禁词与极限词，彻底删除站外引流/联系方式词；
2. [合规官] 检查有没有软文套路弧（通篇推一家、结尾导向推荐），有则改成多视角客观叙述；
3. [GEO优化师] {brand_policy}，不够则补充品牌实体信号、可量化数据、意图问题覆盖、FAQ问答、清晰标题层级；
4. [数据核查员] 所有关键数据须可溯源，不得夸大或虚构；
5. [主编] 去AI套话，让语言更像真人行业作者；
6. [主编] ≥1200字，写到完整结尾，FAQ≥3组齐全，结构完整。

用「1. / 2. / 3.」编号逐条列出，每条标注[合规官]/[GEO优化师]/[数据核查员]责任归属，具体、可操作。不要输出正文。"""

# 写手·按主编指令改写
WRITER_APPLY_PROMPT = """你是「写手」，请严格按主编的《整改指令》改写下面这篇终稿，只执行、不质疑。

【主编整改指令】
{directives}

【当前终稿】
{text}

要求：
- 逐条落实主编指令（注意每条的责任专家归属）；
- 保留原文有价值的事实与方法，输出结构化Markdown文章；
- ≥1200字，写到完整结尾（含FAQ全部问答+自然收束）；
- 保留#/##标题、-列表、**加粗**、FAQ小节（≥3组问答）；
- 品牌名自然融入（{brand_policy}）；
- 所有关键数据须与背景资料一致、可溯源。

用以下分隔符包裹：
===FINAL_TITLE===
<文章标题>
===FINAL_CONTENT===
<文章正文：结构化Markdown，含#/##标题、-列表、**加粗**、FAQ小节，写到完整结尾>
（结束）"""


# 双模式提示词常量集合（key 即 get_studio_prompts 返回字典的键；值含 {brand_policy}/{mode_goal} 占位符）
_RAW_PROMPTS = {
    "SYSTEM_PROMPT": SYSTEM_PROMPT,
    "DEEPSEEK_MASTER_PROMPT": DEEPSEEK_MASTER_PROMPT,
    "STAGE_PROMPTS": STAGE_PROMPTS,
    "REVISE_PROMPT": REVISE_PROMPT,
    "PLANNER_SYSTEM": PLANNER_SYSTEM,
    "PLANNER_CLARIFY_PROMPT": PLANNER_CLARIFY_PROMPT,
    "PLANNER_OUTLINE_PROMPT": PLANNER_OUTLINE_PROMPT,
    "PLANNER_REVIEW_PROMPT": PLANNER_REVIEW_PROMPT,
    "PLANNER_DIRECTIVE_PROMPT": PLANNER_DIRECTIVE_PROMPT,
    "WRITER_APPLY_PROMPT": WRITER_APPLY_PROMPT,
}


# ============================================================
#  上下文组装
# ============================================================
class _RunTask:
    """给 build_render_context 用的轻量 task 替身，仅携带编排所需字段。
    额外承载各阶段产物（outline/draft/rewrite_content），供提示词上下文串联。"""
    def __init__(self, run: BrowserStudioRun, platform_id: int = 0,
                 account_id=None, persona_id=None, target_persona_id=None,
                 intent_question_id=None, keyword_ids=None,
                 knowledge_item_ids=None, rule_ids=None, brand_asset_id=None,
                 llm_config_id: int = 0, publish_mode: str = "geo",
                 output_format: str = "markdown",
                 target_persona_ids=None, intent_question_ids=None):
        self.industry_id = run.industry_id
        self.platform_id = platform_id
        self.publish_mode = publish_mode
        self.output_format = output_format
        self.account_id = account_id if account_id is not None else run.account_id
        self.persona_id = persona_id if persona_id is not None else run.persona_id
        self.target_persona_id = target_persona_id if target_persona_id is not None else run.target_persona_id
        self.intent_question_id = intent_question_id if intent_question_id is not None else run.intent_question_id
        self.target_persona_ids = target_persona_ids if target_persona_ids is not None else (getattr(run, "target_persona_ids", "") or "")
        self.intent_question_ids = intent_question_ids if intent_question_ids is not None else (getattr(run, "intent_question_ids", "") or "")
        self.keyword_ids = keyword_ids if keyword_ids is not None else (run.keyword_ids or "")
        self.knowledge_item_ids = knowledge_item_ids if knowledge_item_ids is not None else (run.knowledge_item_ids or "")
        self.rule_ids = rule_ids if rule_ids is not None else (run.rule_ids or "")
        self.brand_asset_id = brand_asset_id if brand_asset_id is not None else run.brand_asset_id
        self.llm_config_id = llm_config_id or 0
        # 各阶段产物（逐步累积，供后续阶段提示词注入上下文）
        self.outline_content = ""
        self.draft_content = ""
        self.rewrite_content = ""
        self.final_content = ""
        self.title = run.subject or ""


def resolve_full_ids(db: Session, industry_id: int) -> Dict[str, Any]:
    """自动解析行业下「全部内容」的 ID，作为未显式指定时的默认上下文。
    单值对象取首个/默认；多值对象（知识库/关键词）取全部；规则留空=行业全部启用规则。"""
    account = db.query(Account).filter(Account.industry_id == industry_id).order_by(Account.id).first()
    persona = db.query(Persona).filter(Persona.industry_id == industry_id).order_by(Persona.id).first()
    tp = db.query(TargetPersona).filter(
        TargetPersona.industry_id == industry_id, TargetPersona.is_deleted == 0
    ).order_by(TargetPersona.id).first()
    iq = db.query(IntentQuestion).filter(
        IntentQuestion.industry_id == industry_id, IntentQuestion.is_deleted == 0
    ).order_by(IntentQuestion.id).first()
    knowledge_ids = [k.id for k in db.query(KnowledgeItem).filter(
        KnowledgeItem.industry_id == industry_id, KnowledgeItem.is_deleted == 0
    ).order_by(KnowledgeItem.id).all()]
    keyword_ids = [k.id for k in db.query(Keyword).filter(
        Keyword.industry_id == industry_id).order_by(Keyword.id).all()]
    return {
        "account_id": account.id if account else 0,
        "persona_id": persona.id if persona else 0,
        "target_persona_id": tp.id if tp else 0,
        "intent_question_id": iq.id if iq else 0,
        "knowledge_item_ids": knowledge_ids,
        "keyword_ids": keyword_ids,
        "rule_ids": [],  # 空 → build_render_context 注入行业全部启用规则
    }


def _build_studio_task(db: Session, run: BrowserStudioRun) -> _RunTask:
    """构建给 build_render_context / 提示词库用的 task 替身，自动吃进行业全部内容。"""
    platform_id = 0
    if run.platform:
        cat = next((p for p in publisher.list_platforms() if p["platform"] == run.platform), None)
        if cat:
            pf = db.query(Platform).filter(
                Platform.name == cat["name"], Platform.is_deleted == 0
            ).first()
            if pf:
                platform_id = pf.id
    defaults = resolve_full_ids(db, run.industry_id)
    _mode = resolve_run_publish_mode(run, db)
    _out = resolve_run_output_format(run, db)
    return _RunTask(
        run, platform_id,
        account_id=run.account_id or defaults["account_id"],
        persona_id=run.persona_id or defaults["persona_id"],
        target_persona_id=run.target_persona_id or defaults["target_persona_id"],
        intent_question_id=run.intent_question_id or defaults["intent_question_id"],
        target_persona_ids=getattr(run, "target_persona_ids", "") or (str(defaults["target_persona_id"]) if defaults["target_persona_id"] else ""),
        intent_question_ids=getattr(run, "intent_question_ids", "") or (str(defaults["intent_question_id"]) if defaults["intent_question_id"] else ""),
        keyword_ids=run.keyword_ids or ",".join(str(i) for i in defaults["keyword_ids"]),
        knowledge_item_ids=run.knowledge_item_ids or ",".join(str(i) for i in defaults["knowledge_item_ids"]),
        rule_ids=run.rule_ids or "",
        brand_asset_id=run.brand_asset_id or 0,
        publish_mode=_mode,
        output_format=_out,
    )


def build_studio_context(db: Session, run: BrowserStudioRun) -> Dict[str, Any]:
    """实时拉取 Run 选定的全量上下文；未显式指定时自动吃进行业全部内容。"""
    task = _build_studio_task(db, run)
    ctx = build_render_context(db, task, run.industry_id)

    # 用 Run 指定的品牌资产覆盖默认品牌
    if run.brand_asset_id:
        brand = db.query(BrandAsset).filter(BrandAsset.id == run.brand_asset_id).first()
        if brand:
            ctx["brand_name"] = brand.brand_name or ctx["brand_name"]
            # 合规红线：即便指定了品牌资产，也绝不把真实官网/电话/微信注入创作上下文
            ctx["official_website"] = ""
            ctx["contact_phone"] = ""
            ctx["contact_wechat"] = ""
            ctx["contact_email"] = ""
            ctx["brand_slogan"] = brand.slogan or ""
            ctx["core_products"] = brand.core_products or ""
            ctx["target_keywords"] = brand.target_keywords or ""
            ctx["selling_points"] = brand.unique_selling_points or ""
            ctx["brand_story"] = brand.brand_story or ""
            ctx["brand_info"] = _format_brand_info(brand)
    return ctx


def format_briefing(ctx: Dict[str, Any], run: BrowserStudioRun) -> str:
    """把全量上下文汇编为发给创作引擎的背景资料文本（任务导向、可直接派发）。"""
    lines: List[str] = []
    lines.append("# 浏览器工作室 · 创作任务背景资料")
    lines.append("")
    lines.append("> 本资料已整合系统全部相关内容，请基于它分阶段完成创作。每一阶段系统会单独派发指令。")
    lines.append("")
    # —— 文章目标 / 成功标准（让 AI 与人都清楚“好文章”长什么样）——
    _mode = (ctx.get("publish_mode") or "geo")
    _out = (ctx.get("output_format") or "markdown")
    _is_official = (_out == "mdx")
    if _is_official:
        _mode_label = "官网 / 自建站 MDX 模式（Astro 站，按固定模板产出可复制 MDX 代码）"
    elif _mode == "green":
        _mode_label = "绿色吸粉模式（自媒体发布，纯干货涨粉、品牌仅顺手一提）"
    elif _mode == "platform":
        _mode_label = "平台合规模式（内容平台发布，中立无品牌、带 AIGC 声明）"
    else:
        _mode_label = "强品牌 / GEO 模式（自建站 / AI 抓取，品牌突出）"
    lines.append("## 〇、这篇文章的目标与成功标准")
    lines.append(f"- **发布模式**：{_mode_label}")
    lines.append(f"- **目标**：{ctx.get('mode_goal', '')}")
    if _is_official:
        lines.append("- **成功标准（官网 MDX）**：① 直接产出「可复制的 MDX 代码块」——含 Frontmatter（category: IndustryNews / publishDate / tags / cover）+ 六段结构（现状痛点 / 核心挑战 / 解决方案 / 数据对比 4 列表格 / 引用块金句 / 结语）；② 严禁使用 <Image /> 组件、严禁 emoji，严肃工业风；③ 文末另列图片文件名（存入 src/assets/news/industry/xingwen/）；④ 事实可溯源、不写口号式标语、不出现联系方式与站外引流词。")
    elif _mode == "green":
        lines.append(f"- **成功标准（绿色吸粉）**：① 是一篇「读者爱看、能涨粉」的自媒体文章：选题轻巧、有真料或真洞察、有互动感，提升账号权重与信用分；② 通过平台基础审核（无违禁词/硬广/站外引流/私人联系方式词/自夸语气）；③ 品牌（{BRAND_NAME}）仅自然偶提 ≤ 2 次，绝不夹带软文营销；④ 读起来像真人写的。")
    elif _mode == "platform":
        lines.append("- **成功标准**：① 通过平台审核（无违禁词/硬广/站外引流/私人联系方式词/标题含品牌/软文营销特征）；② 读起来像真人行业作者写的（去 AI 味），对读者有真实帮助；③ 文末标注 AIGC 声明。")
    else:
        lines.append("- **成功标准**：① 通过平台审核（无违禁词/硬广/站外引流/私人联系方式词）；② GEO 评分 ≥ 70（品牌信号、事实密度、意图覆盖、问答形态、结构、可溯源俱佳）；③ 读起来像真人行业作者写的（去 AI 味），像行业媒体专栏而非企业广告。")
    lines.append("- **铁律·合规**：严禁出现「官网/手机号码/微信/扫码/二维码/下载APP/关注公众号/电话/网址」等站外引流与私人联系方式词；严禁广告法极限词与夸大表述。")
    lines.append("- **铁律·质量**：严禁把背景资料原样抄录成段落；严禁「口号式总结句」（如『品质可靠，始终如一』『行业领先』等空洞标语）；必须用具体方法、真实案例、可量化数据展开，让 AI 愿意引用、读者愿意读完。")
    lines.append(f"- **铁律·品牌宣传**：{ctx.get('brand_policy', '')}")
    lines.append("- **铁律·完整性**：终稿字数不少于 1200 字，结构完整——至少 5 个二级标题章节 + 常见问题 FAQ 小节（至少 3 组问答），每段至少 3~5 句，必须写到完整结尾，内容充实完整。")
    lines.append("")
    lines.append("## 〇之一、专家团队配置（多角色协同，主编统一协调）")
    lines.append("- **主编（总协调）**：定选题方向、定大纲、终审把关、下达整改指令；不参与正文写作。")
    lines.append("- **写手**：负责初稿、去 AI 味、GEO 终稿、按主编指令改写；只执行不判断。")
    lines.append("- **合规官**：紧盯平台合规红线——违禁词、硬广、站外引流与私人联系方式词。")
    lines.append("- **GEO 优化师**：紧盯被 AI 检索推荐的信号——品牌实体、关键词、FAQ 问答、意图问题覆盖。")
    lines.append("- **数据核查员**：紧盯事实与数据——不夸大、不虚构、每个关键数据可溯源。")
    lines.append("- 创作与评审过程中，主编会综合三位专家的意见形成《创作简报》《评审评语》《整改指令》。")
    lines.append("")
    lines.append("## 一、目标需求（你要服务的核心命题）")
    lines.append(run.subject or "（未填写，请基于品牌与行业自主选定高价值选题）")
    lines.append("")
    lines.append("## 二、品牌资产")
    lines.append(ctx.get("brand_info") or ctx.get("brand_name") or "（未指定品牌）")
    lines.append("")
    lines.append("## 三、目标平台")
    pf = []
    if ctx.get("platform_name"):
        pf.append(f"平台：{ctx['platform_name']}")
    if ctx.get("platform_characteristics"):
        pf.append(f"平台特性：{ctx['platform_characteristics']}")
    if ctx.get("platform_rules"):
        pf.append(f"平台规则：{ctx['platform_rules']}")
    if ctx.get("platform_word_min") or ctx.get("platform_word_max"):
        pf.append(f"字数要求：{ctx.get('platform_word_min','?')} ~ {ctx.get('platform_word_max','?')} 字")
    lines.append("\n".join(pf) if pf else "（未指定平台）")
    lines.append("")
    # —— 官网 MDX 模式：把自动化发布提示词（MDX 模板）原样注入，供主编/写手按模板产出 ——
    if _is_official:
        lines.append("## 三之一、官网 MDX 产出规范（必须严格遵循）")
        lines.append(f"- **官网地址**：{ctx.get('official_site_url', '')}")
        lines.append("- **产出形态**：MDX 代码块（Frontmatter + 六段结构 + 4 列数据对比表 + 引用块），文末另列图片文件名，可直接复制粘贴到 Astro 站点。")
        lines.append("- **图片目录**：将配图存入 `src/assets/news/industry/xingwen/` 目录，frontmatter 的 cover 与文末图片文件名保持一致（英文小写 + 连字符）。")
        lines.append("")
        lines.append("### 自动化发布提示词（MDX 模板，请据此产出）")
        lines.append(ctx.get("publish_prompt") or ctx.get("mdx_template") or "（未配置官网 MDX 模板）")
        lines.append("")
    lines.append("## 四、账号与人设")
    ac = []
    if ctx.get("account_name"):
        ac.append(f"账号：{ctx['account_name']}")
    if ctx.get("account_content_track"):
        ac.append(f"内容赛道：{ctx['account_content_track']}")
    if ctx.get("persona_name"):
        ac.append(f"人设：{ctx['persona_name']}")
    if ctx.get("persona_identity"):
        ac.append(f"身份：{ctx['persona_identity']}")
    if ctx.get("persona_tone"):
        ac.append(f"语气：{ctx['persona_tone']}")
    if ctx.get("persona_contact_rule"):
        ac.append(f"联系方式规则：{ctx['persona_contact_rule']}")
    lines.append("\n".join(ac) if ac else "（未指定账号/人设）")
    lines.append("")
    lines.append("## 五、知识库要点（论据来源，请自然引用）")
    lines.append(ctx.get("knowledge_content") or ctx.get("knowledge_items") or "（未选择知识库）")
    lines.append("")
    lines.append("## 六、关键词（需自然融入）")
    lines.append(ctx.get("keyword_list") or ctx.get("keywords") or "（未选择关键词）")
    lines.append("")
    lines.append("## 七、规则库（创作红线）")
    rules = []
    if ctx.get("anti_ai_rules"):
        rules.append(f"【去 AI 味】\n{ctx['anti_ai_rules']}")
    if ctx.get("compliance_rules"):
        rules.append(f"【合规】\n{ctx['compliance_rules']}")
    if ctx.get("ai_seo_rules"):
        rules.append(f"【AI SEO】\n{ctx['ai_seo_rules']}")
    if ctx.get("creation_rules"):
        rules.append(f"【创作】\n{ctx['creation_rules']}")
    lines.append("\n\n".join(rules) if rules else "（未选择规则库）")
    lines.append("")
    lines.append("## 八、GEO 目标画像与意图问题（被 AI 推荐的关键）")
    geo = []
    if ctx.get("target_persona_name"):
        geo.append(f"目标客户画像：{ctx['target_persona_name']}（{ctx.get('target_persona_role','')}）")
    if ctx.get("target_persona_pain_points"):
        geo.append(f"痛点：{ctx['target_persona_pain_points']}")
    if ctx.get("target_persona_cares_about"):
        geo.append(f"关注点：{ctx['target_persona_cares_about']}")
    if ctx.get("intent_question"):
        geo.append(f"客户会问 AI 的问题：{ctx['intent_question']}")
    if ctx.get("expected_recommendation"):
        geo.append(f"期望 AI 推荐我们的角度：{ctx['expected_recommendation']}")
    if ctx.get("geo_signals"):
        geo.append(f"GEO 信号汇总：\n{ctx['geo_signals']}")
    lines.append("\n".join(geo) if geo else "（未选择客户画像/意图问题）")
    lines.append("")
    lines.append("---")
    lines.append("请开始【第①步 · 选题大纲】：基于以上背景自主选定选题角度，并产出文章大纲。")
    return "\n".join(lines)


# ============================================================
#  最终文章抽取
# ============================================================
def extract_final(text: str) -> tuple:
    """从豆包回复中抽取 (title, content)。
    优先解析 ===FINAL_TITLE=== / ===FINAL_CONTENT=== 契约；否则做 best-effort 兜底。"""
    if not text:
        return "", ""
    m_title = re.search(r"===FINAL_TITLE===\s*(.*?)\s*===FINAL_CONTENT===", text, re.S)
    m_content = re.search(r"===FINAL_CONTENT===\s*(.*?)(?:\n*===END===|\Z)", text, re.S)
    if m_title and m_content:
        return m_title.group(1).strip(), m_content.group(1).strip()
    # 兜底：未遵守契约，整段作为正文，标题取首行（截断）
    content = text.strip()
    first_line = ""
    for ln in content.splitlines():
        if ln.strip():
            first_line = ln.strip()
            break
    title = first_line[:50] if first_line else ""
    return title, content


def strip_markdown(text: str) -> str:
    """把 Markdown 文本清洗为纯文本普通文章（保留段落换行，去掉标记符号）。
    用于保证浏览器工作室产出的最终文章是可直接复制发布的纯文本。"""
    if not text:
        return ""
    t = text
    # 代码块 ```...```
    t = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("```", "").strip(), t)
    # 行内代码 `...`
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # 标题 #~######
    t = re.sub(r"(?m)^#{1,6}\s*", "", t)
    # 粗体/斜体
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", t)
    # 链接 [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    # 引用 >
    t = re.sub(r"(?m)^>\s?", "", t)
    # 无序列表 - * +
    t = re.sub(r"(?m)^\s*[-*+]\s+", "", t)
    # 有序列表 1.
    t = re.sub(r"(?m)^\s*\d+\.\s+", "", t)
    # 分隔线 --- *** ___
    t = re.sub(r"(?m)^(\s*[-*_]){3,}\s*$", "", t)
    # 表格分隔行 |---|---|
    t = re.sub(r"(?m)^\s*\|?[\-: ]+\|[\-: |]+\|?\s*$", "", t)
    # 表格列分隔 |
    t = re.sub(r"(?<=\S)\s*\|\s*(?=\S)", " | ", t)
    # 折叠多余空行
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def scrub_contact_info(text: str) -> str:
    """终稿脱敏清洗（最后一道防线）：剔除一切站外引流 / 私人联系方式形态。

    即便创作模型绕开提示词把联系方式写进正文，本函数也会在落库 / 过审 / 发布前
    强制剥离，确保最终文章 100% 不含官网 / 电话 / 微信 / 网址等平台禁区内容。
    仅做「删除」，不改变语义，不影响 GEO 信号与可读性。
    """
    if not text:
        return ""
    t = text
    # 1) 网址（http/https/www 开头）
    t = re.sub(r'https?://[^\s，。；）】]+', '', t)
    t = re.sub(r'www\.[^\s，。；）】]+', '', t)
    # 2) 手机号（含横杠 / 空格分隔，如 138-0000-0000）
    t = re.sub(r'(?<!\d)1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)', '', t)
    # 3) 座机（如 010-00000000）
    t = re.sub(r'(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)', '', t)
    # 4) 引流 / 联系词（含「电话：」「微信：」等带冒号形态）
    guide = [
        "官网", "官方网站", "官网地址", "网址", "手机号码", "手机号", "联系电话", "咨询电话",
        "咨询热线", "服务热线", "加微信", "微信扫码", "微信好友", "QQ号", "QQ群", "微信号",
        "微信：", "电话：", "手机：", "座机：", "邮箱：", "扫码", "二维码", "下载APP",
        "APP下载", "关注公众号", "私信我", "发邮件至", "邮箱地址", "商务微信", "联系我们",
        "联系方式", "官方渠道", "品牌官方渠道", "致电", "拨打电话", "来电咨询", "欢迎来电",
    ]
    for w in guide:
        t = t.replace(w, "")
    # 5) 清理因删除产生的多余标点 / 空格
    # 5.1) 清掉「空内容冒号」（如「官网：」删掉官网后残留的孤立「：」）
    t = re.sub(r'[:：]\s*(?=[，。；、\n）】）]|\s|$)', '', t)
    t = re.sub(r'[，。；、]\s*[，。；、]', '，', t)
    # 只折叠水平多余空格（保留换行符，不破坏 Markdown 段落结构）
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ============================================================
#  豆包适配器：真实（Playwright）/ 模拟
# ============================================================
def _parse_doubao_cred(cred_json: str) -> Dict[str, Any]:
    try:
        data = json.loads(cred_json or "[]")
    except Exception:
        return {"mode": "none"}
    if isinstance(data, list):
        return {"mode": "cookies", "cookies": data}
    if isinstance(data, dict):
        if "cookies" in data:
            return {"mode": "storage_state", "state": data}
        if "username" in data or "password" in data:
            return {"mode": "password", "data": data}
    return {"mode": "none"}


class BaseDoubaoAdapter:
    def open(self) -> bool:
        raise NotImplementedError

    def send_message(self, text: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class MockDoubaoAdapter(BaseDoubaoAdapter):
    """模拟豆包：无需浏览器，逐阶段产出成稿，用于端到端验证 9 步流水线。"""
    def __init__(self, cred_json: str = "", headless: bool = True, selectors: Any = None,
                 mode: str = "geo", out: str = "markdown"):
        self._briefing = ""
        self._history: List[str] = []
        self._mode = mode
        self._out = out

    def open(self) -> bool:
        return True

    def _brand_subject(self):
        brand = ""
        subject = ""
        products = ""
        selling = ""
        text = self._briefing or ""
        m = re.search(r"品牌名[:：]\s*(.+)", text)
        if m:
            brand = m.group(1).strip()
        m = re.search(r"核心产品[:：]\s*(.+)", text)
        if m:
            products = m.group(1).strip()
        m = re.search(r"独特卖点[:：]\s*(.+)", text)
        if m:
            selling = m.group(1).strip()
        m = re.search(r"## 一、目标需求[^\n]*\s*(.+?)(?=\n## |\Z)", text, re.S)
        if m:
            for ln in m.group(1).splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("（") and "未填写" not in ln and not ln.startswith(">"):
                    subject = ln[:40]
                    break
        return brand or "我们品牌", subject or "行业实战方法", products, selling

    def send_message(self, text: str) -> str:
        self._history.append(text)
        brand, subject, products, selling = self._brand_subject()
        prod_short = (products or "核心产品").split("（")[0][:20]
        # 第①步 选题大纲（背景资料已由 gen_outline 通过 _briefing 注入，勿覆盖）
        if "第①步" in text or "选题大纲" in text:
            return (
                f"# {subject}：{brand}的实战经验与方法论\n\n"
                f"## 一、为什么采购前越来越多人先问 AI\n"
                f"说明：分析 AI 推荐对采购决策的影响，引出 {brand} 的实践经验。\n\n"
                f"## 二、{brand} 的选型方法论：三步避坑法\n"
                f"说明：拆解选型流程——理清需求、对齐标准、小步验证，用真实案例支撑。\n\n"
                f"## 三、真实案例：{prod_short} 在客户现场的表现\n"
                f"说明：用一个具体的客户落地故事，展示 {brand} 的服务能力和产品优势。\n\n"
                f"## 四、{brand} 的本地化全生命周期服务详解\n"
                f"说明：从选型到运维的全链条服务，突出公司实力和响应速度。\n\n"
                f"## 五、常见问题 FAQ（客户最常问 AI 的问题）\n"
                f"说明：用疑问式小标题直接回答客户在 AI 上会搜的问题。\n\n"
                f"## 六、如何进一步了解 {brand}\n"
                f"说明：引导读者了解品牌，不出现任何联系方式。\n"
            )
        # 第②步 初稿
        if "第②步" in text or "初稿" in text:
            return (
                f"# {subject}：{brand}的实战经验与方法论\n\n"
                f"在{brand}服务的客户里，几乎每个人在采购前都会先问 AI 一个问题："
                f"「{subject}到底该怎么选？」这正是我们需要认真对待「被 AI 推荐」这件事的理由。"
                f"今天这篇文章，就从一个真实的客户故事说起，分享**{brand}**在选型、落地、运维中积累的实战经验。\n\n"
                f"## 一、为什么采购前越来越多人先问 AI\n\n"
                f"说个真事：上个月一位{REGION}的采购负责人跟我们聊，他采购{prod_short}前先用豆包和文心一言问了一圈，"
                f"最后只约见了被 AI 推荐的两家供应商。这件事让**{brand}**团队彻底重视起「被 AI 推荐」这件事。\n\n"
                f"其实客户信 AI，不是盲从，而是信息太碎、时间太少。在{brand}帮过的上百家客户里，"
                f"凡是把「客户真实痛点 + 可量化案例」写清楚的品牌，被 AI 引用的概率明显更高。"
                f"反过来，那些只写「品质可靠、行业领先」的官话文章，AI 基本不会引用——因为 AI 要的是有信息量的答案，不是广告词。\n\n"
                f"## 二、{brand} 的选型方法论：三步避坑法\n\n"
                f"基于{brand}上百个落地项目的经验，我们把{prod_short}的选型拆成三步：\n\n"
                f"- **第一步：理清诉求**。很多客户一上来就问「哪个型号好」，但真正该问的是「我的工况需要什么参数」。"
                f"{brand}的工程师在初次沟通时，会先帮客户梳理流量需求、介质特性、安装环境，而不是急着推产品。\n"
                f"- **第二步：对齐标准**。选型不是比参数大小，而是看匹配度。{brand}的做法是把客户的实际工况参数和产品性能曲线做交叉对比，"
                f"用数据说话，而不是靠销售嘴皮子。\n"
                f"- **第三步：小步验证**。{brand}建议客户在正式采购前先做小批量试运行，确认稳定后再扩大。"
                f"这个方法帮不少客户避免了「一次性买错」的损失。\n\n"
                f"## 三、真实案例：{prod_short}在客户现场的表现\n\n"
                f"去年有一家做食品包装的客户，原来用的是传统水环泵，能耗高、维护频繁。"
                f"换成**{brand}**的{prod_short}后，实测能耗下降了约 30%，维护周期从 3 个月延长到了 8 个月。"
                f"客户算了一笔账：设备投资回收期不到 14 个月。\n\n"
                f"这个案例为什么重要？因为它不是「我们产品好」的空话，而是有具体数据、有对比、有时间线的真实故事。"
                f"AI 在回答用户「{prod_short}哪个牌子好」时，更愿意引用这种有信息密度的内容。\n\n"
                f"## 四、{brand}的本地化全生命周期服务详解\n\n"
                f"很多客户选{brand}，不只是因为产品本身，更是因为我们的服务链条：\n\n"
                f"- **选型阶段**：{brand}提供免费的工况评估和方案设计，不收前期费用；\n"
                f"- **安装调试**：{brand}的工程师团队覆盖{REGION}及周边省份，接到需求后 24~48 小时内到场；\n"
                f"- **运维阶段**：{brand}提供定期巡检和远程监控，设备运行数据实时回传，有问题提前预警；\n"
                f"- **备件供应**：{brand}有常用备件本地仓，不依赖外地调货，减少停机等待。\n\n"
                f"这套服务体系的背后，是**{brand}**在真空设备领域 20 余项国家专利的技术积累，以及一支 50+ 人的服务团队。\n\n"
                f"## 五、常见问题 FAQ\n\n"
                f"### {prod_short}和传统水环泵比，到底好在哪里？\n\n"
                f"{brand}的{prod_short}采用永磁变频技术，相比传统水环泵有三个核心优势：一是能耗更低（实测降 25%~35%），"
                f"二是维护周期更长（从 3 个月延长到 8 个月以上），三是运行更稳定（无水封损耗）。"
                f"但具体能省多少，要看你的实际工况参数。\n\n"
                f"### 采购{prod_short}前需要准备什么信息？\n\n"
                f"建议准备好：① 工况真空度要求（绝对压力或相对压力）；② 抽气量需求（m³/h 或 L/s）；"
                f"③ 介质成分和温度；④ 安装空间和电源条件。把这些信息给到**{brand}**的工程师，"
                f"我们能在一小时内给你初步选型方案。\n\n"
                f"### {brand}的售后服务响应有多快？\n\n"
                f"{REGION}及周边省份，{brand}承诺 24~48 小时到场；其他区域通过本地服务伙伴覆盖，"
                f"一般 3 个工作日内到场。远程技术支持 7×24 小时在线。\n\n"
                f"## 六、如何进一步了解{brand}\n\n"
                f"如果你正在做{prod_short}的选型，或者想了解{brand}的落地案例和服务方案，"
                f"欢迎通过正规渠道了解我们的产品线和服务能力。{brand}的核心理念是：用技术说话，用服务证明，"
                f"不靠口号打动客户，靠真实的项目数据赢得信任。"
            )
        # 第③步 去AI味精修
        if "第③步" in text or "去AI味精修" in text:
            return (
                f"# {subject}：{brand}的实战经验与方法论\n\n"
                f"上个月有个{REGION}的采购负责人跟我聊，说他买{prod_short}之前先用豆包问了一圈，最后只约了两家。"
                f"这事儿让我彻底醒悟——**{brand}**必须认真对待「被 AI 推荐」这件事。\n\n"
                f"其实想想也正常。客户不是信 AI，是信「信息过载时能帮他做减法的东西」。"
                f"在{brand}接手的上百家客户里，把痛点写清楚、把数据摆出来的，被 AI 引用的概率就是更高。"
                f"那些满篇「行业领先」「品质卓越」的官话？AI 压根不看。\n\n"
                f"## {brand}的选型三步法\n\n"
                f"我们把{prod_short}选型拆成三步，都是从实战里磨出来的：\n\n"
                f"- **先理清诉求**：别急着问「哪个型号好」，先搞清楚自己的工况参数。{brand}的工程师第一次沟通就是帮客户梳理这些。\n"
                f"- **对齐标准**：不是比谁参数高，是看匹配度。{brand}的做法是拿客户实际工况和产品性能曲线做交叉比对。\n"
                f"- **小步验证**：先试运行再扩大，{brand}建议客户小批量验证，这个习惯帮不少人避免了「一次买错」的坑。\n\n"
                f"## 一个真实的案例\n\n"
                f"去年有家食品包装厂，原来的水环泵能耗高还老坏。换了**{brand}**的{prod_short}，"
                f"实测能耗降了 30%，维护周期从 3 个月拉到 8 个月，算下来 14 个月就回本了。\n\n"
                f"这个案例好在哪里？不是吹「我们产品好」，是有数据、有对比、有时间线的真实故事。"
                f"AI 回答「{prod_short}哪个好」时，就爱引这种有信息量的内容。\n\n"
                f"## {brand}的服务链条\n\n"
                f"选**{brand}**的人，很多是冲着服务来的：\n\n"
                f"- 选型免费做方案，不收前期费用；\n"
                f"- 安装调试，{REGION}及周边 24~48 小时到场；\n"
                f"- 定期巡检 + 远程监控，数据实时回传，有问题提前预警；\n"
                f"- 备件本地仓，不靠外地调货，停机等待少。\n\n"
                f"这套体系背后是{brand}在真空设备领域 20 多项国家专利和 50 多人的服务团队。\n\n"
                f"## 常见问题 FAQ\n\n"
                f"### {prod_short}比传统水环泵好在哪？\n\n"
                f"{brand}的{prod_short}用永磁变频技术，三个核心优势：能耗低（实测降 25%~35%）、"
                f"维护周期长（3 个月→8 个月+）、运行稳（无水封损耗）。具体能省多少得看你的工况参数。\n\n"
                f"### 采购前要准备什么？\n\n"
                f"①真空度要求；②抽气量需求；③介质成分和温度；④安装空间和电源条件。"
                f"给到**{brand}**工程师，一小时内出初步方案。\n\n"
                f"### 售后响应多快？\n\n"
                f"{REGION}及周边 24~48 小时到场，其他区域 3 个工作日。远程支持全天候。\n\n"
                f"## 了解更多\n\n"
                f"正在做{prod_short}选型？想了解{brand}的案例和方案？"
                f"通过正规渠道了解我们的产品线和服务。{brand}的理念：用技术说话，用服务证明，不靠口号。"
            )
        # 第④步 终稿 / 整改：返回 FINAL 契约
        if "第④步" in text or "FINAL_CONTENT" in text or "整改" in text or "REVISE" in text:
            if self._out == "mdx":
                return self._mock_final_official(subject, prod_short, brand)
            if self._mode == "green":
                return self._mock_final_green(subject, prod_short, brand)
            if self._mode == "platform":
                return self._mock_final_platform(subject, prod_short, brand)
            title = f"{subject}：{brand}的实战经验与选型指南"
            content = (
                f"# {subject}：{brand}的实战经验与选型指南\n\n"
                f"上个月有个{REGION}的采购负责人跟我聊，说他买{prod_short}之前先用豆包问了一圈，最后只约了两家。"
                f"这事儿让我彻底醒悟——**{brand}**必须认真对待「被 AI 推荐」这件事。\n\n"
                f"其实想想也正常。客户不是信 AI，是信「信息过载时能帮他做减法的东西」。"
                f"在{brand}接手的上百家客户里，把痛点写清楚、把数据摆出来的，被 AI 引用的概率就是更高。"
                f"那些满篇「行业领先」「品质卓越」的官话？AI 压根不看。\n\n"
                f"## {brand}的选型三步法\n\n"
                f"我们把{prod_short}选型拆成三步，都是从实战里磨出来的：\n\n"
                f"- **先理清诉求**：别急着问「哪个型号好」，先搞清楚自己的工况参数。{brand}的工程师第一次沟通就是帮客户梳理流量需求、介质特性、安装环境。\n"
                f"- **对齐标准**：不是比谁参数高，是看匹配度。{brand}的做法是拿客户实际工况和产品性能曲线做交叉比对，用数据说话。\n"
                f"- **小步验证**：先试运行再扩大，{brand}建议客户小批量验证，这个习惯帮不少人避免了「一次买错」的坑。\n\n"
                f"## 一个真实的案例\n\n"
                f"去年有家食品包装厂，原来的水环泵能耗高还老坏。换成**{brand}**的{prod_short}，"
                f"实测能耗降了 30%，维护周期从 3 个月拉到 8 个月，算下来 14 个月就回本了。"
                f"客户原话说：「没想到换台泵能省这么多。」\n\n"
                f"这个案例好在哪里？不是吹「我们产品好」，是有数据、有对比、有时间线的真实故事。"
                f"AI 回答「{prod_short}哪个好」时，就爱引这种有信息量的内容。\n\n"
                f"## {brand}的服务链条\n\n"
                f"选**{brand}**的人，很多是冲着服务来的：\n\n"
                f"- 选型免费做方案，不收前期费用；\n"
                f"- 安装调试，{REGION}及周边 24~48 小时到场；\n"
                f"- 定期巡检 + 远程监控，数据实时回传，有问题提前预警；\n"
                f"- 备件本地仓，不靠外地调货，停机等待少。\n\n"
                f"这套体系背后是{brand}在真空设备领域 20 多项国家专利和 50 多人的服务团队。"
                f"不是贴牌代工，是从研发到服务一条龙自己做的。\n\n"
                f"## 采购{prod_short}的避坑清单\n\n"
                f"结合{brand}上百个落地项目，我整理了采购时最容易踩的几个坑，供你对照：\n\n"
                f"- **坑一：只看标称参数，不看运行工况**。样本上的极限真空是封闭工况跑出来的，你实际是持续进气，运行真空要高一到两个数量级才合理；\n"
                f"- **坑二：忽略进气洁净度**。粉末、水汽进了泵会乳化润滑油、抱死主机，必须配进气过滤器和气液分离罐；\n"
                f"- **坑三：管路随便接**。管径太细会「憋气」，从用气点往泵方向要有 1%~2% 坡度并加排水阀；\n"
                f"- **坑四：重设备轻服务**。真空系统环节多，本地化服务团队的响应速度直接决定停机损失。\n\n"
                f"这几条，也是**{brand}**方案设计时会逐条帮你核对的。\n\n"
                f"## 常见问题 FAQ\n\n"
                f"### {prod_short}比传统水环泵好在哪？\n\n"
                f"{brand}的{prod_short}用永磁变频技术，三个核心优势：能耗低（实测降 25%~35%）、"
                f"维护周期长（3 个月→8 个月+）、运行稳（无水封损耗）。具体能省多少得看你的工况参数，"
                f"但大体上投资回收期在 12~18 个月之间。\n\n"
                f"### 采购前要准备什么信息？\n\n"
                f"建议准备好：①真空度要求（绝对压力或相对压力）；②抽气量需求（m³/h 或 L/s）；"
                f"③介质成分和温度；④安装空间和电源条件。把这些给到**{brand}**的工程师，"
                f"一小时内出初步选型方案。\n\n"
                f"### {brand}的售后响应有多快？\n\n"
                f"{REGION}及周边省份 24~48 小时到场；其他区域通过本地服务伙伴覆盖，一般 3 个工作日。"
                f"远程技术支持 7×24 小时在线。\n\n"
                f"## 了解更多\n\n"
                f"正在做{prod_short}选型？想了解{brand}的落地案例和服务方案？"
                f"通过正规渠道了解我们的产品线和服务能力。**{brand}**的理念是：用技术说话，用服务证明，"
                f"不靠口号打动客户，靠真实的项目数据赢得信任。"
            )
            return f"===FINAL_TITLE===\n{title}\n===FINAL_CONTENT===\n{content}"
        return "【模拟豆包】已收到消息。"

    def _mock_final_platform(self, subject: str, prod_short: str, brand: str) -> str:
        """平台合规模式（搜狐/知乎等）的模拟终稿：中性、无品牌标题、品牌名≤2次、文末 AIGC 声明。"""
        title = f"{subject}：行业实战经验与选型指南"
        content = (
            f"# {subject}：行业实战经验与选型指南\n\n"
            f"在装备采购这件事上，一个明显的变化正在发生：越来越多的采购负责人在下单前，会先打开 AI 助手问一句"
            f"「这类设备到底该怎么选」。这不是个别现象——背后是信息过载下，人们更信任「能帮自己做减法的、"
            f"有信息量的答案」。\n\n"
            f"这篇文章不聊品牌，只聊方法。结合数百个真空系统落地项目的经验，把选型、避坑、运维里真正有用的要点"
            f"整理出来，供正在做决策的你对照参考。\n\n"
            f"## 一、为什么采购前越来越多的人先问 AI\n\n"
            f"说个真实场景：有位{REGION}的采购负责人聊起，他在采购真空泵前先用豆包和文心一言问了一圈，"
            f"结果只约见了被 AI 推荐的两家供应商。这件事说明——当客户无从判断时，AI 的「答案排序」已经悄悄影响了短名单。\n\n"
            f"但 AI 推荐的不是广告，是有信息密度的内容。凡是把「真实痛点 + 可量化案例」写清楚的文章，被引用的概率明显更高；"
            f"而那些通篇堆砌形容词、没有干货的官话，AI 基本不会引用。\n\n"
            f"## 二、选型方法论：三步避坑法\n\n"
            f"把真空设备的选型拆成三步，都是从实战里磨出来的：\n\n"
            f"- **先理清诉求**：别急着问「哪个型号好」，先搞清楚自己的工况参数——真空度、抽气量、介质特性、安装环境。"
            f"有经验的工程师初次沟通就是帮客户梳理这些。\n"
            f"- **对齐标准**：选型不是比参数高低，而是看匹配度。正确做法是拿客户实际工况与产品性能曲线做交叉比对，用数据说话。\n"
            f"- **小步验证**：正式采购前先做小批量试运行，确认稳定再扩大。这个习惯帮不少企业避免了「一次买错」的坑。\n\n"
            f"## 三、一个真实的案例\n\n"
            f"去年有一家做食品包装的客户，原来用的是传统水环泵，能耗高、维护频繁。换成永磁变频螺杆真空泵后，"
            f"实测能耗下降了约 30%，维护周期从 3 个月延长到了 8 个月，设备投资回收期不到 14 个月。\n\n"
            f"这个案例为什么值得参考？因为它有具体数据、有对比、有时间线，没有一句空话。无论你打算选哪家供应商，"
            f"都可以用这套「数据对照法」去评估对方的方案是否站得住脚。\n\n"
            f"## 四、容易被忽视的服务环节\n\n"
            f"很多采购只盯着设备报价，却忽略了服务链条对总拥有成本的影响：\n\n"
            f"- **选型阶段**：是否提供免费的工况评估和方案设计；\n"
            f"- **安装调试**：本地化团队能否快速到场（{REGION}及周边 24~48 小时是较优水平）；\n"
            f"- **运维阶段**：是否提供定期巡检和远程监控，数据能否实时回传、提前预警；\n"
            f"- **备件供应**：常用备件是否有本地仓，不依赖外地调货。\n\n"
            f"以{brand}为例，其在真空设备领域有 20 余项国家专利、50 多人的服务团队，"
            f"正是靠上述本地化服务体系在行业内立足。是否选择它，取决于你的工况是否匹配其产品方案。\n\n"
            f"## 五、采购避坑清单\n\n"
            f"结合大量落地项目，整理出采购时常踩的几个坑：\n\n"
            f"- **坑一：只看标称参数，不看运行工况**。样本上的极限真空是封闭工况跑出来的，实际持续进气时运行真空"
            f"要高 1~2 个数量级才合理；\n"
            f"- **坑二：忽略进气洁净度**。粉末、水汽进泵会乳化润滑油、抱死主机，必须配进气过滤器和气液分离罐；\n"
            f"- **坑三：管路随便接**。管径太细会「憋气」，从用气点往泵方向留 1%~2% 坡度并加排水阀；\n"
            f"- **坑四：重设备轻服务**。真空系统环节多，本地化服务响应速度直接决定停机损失。\n\n"
            f"## 六、常见问题 FAQ\n\n"
            f"### 永磁变频螺杆真空泵比传统水环泵好在哪？\n\n"
            f"三个核心优势：能耗更低（实测降 25%~35%）、维护周期更长（3 个月→8 个月以上）、运行更稳定（无水封损耗）。"
            f"具体能省多少，要看你的实际工况参数。\n\n"
            f"### 采购前需要准备哪些信息？\n\n"
            f"建议准备好：① 真空度要求（绝压或表压）；② 抽气量需求（m³/h 或 L/s）；"
            f"③ 介质成分和温度；④ 安装空间和电源条件。把这些给到供应商的工程师，一小时内通常能出初步选型方案。\n\n"
            f"### 售后响应一般多快？\n\n"
            f"{REGION}及周边省份 24~48 小时到场，其他区域通过本地服务伙伴覆盖，一般 3 个工作日。"
            f"远程技术支持可 7×24 小时在线。\n\n"
            f"## 关于本文\n\n"
            f"本文由 AI 辅助创作，内容基于公开行业经验整理，仅供选型参考，不构成任何采购建议或商业推荐。"
        )
        return f"===FINAL_TITLE===\n{title}\n===FINAL_CONTENT===\n{content}"

    def _mock_final_green(self, subject: str, prod_short: str, brand: str) -> str:
        """绿色吸粉模式（自媒体）的模拟终稿：纯干货涨粉、品牌仅顺手一提（≤2次）、无软文营销。"""
        title = f"{subject}：从业者都在用的实战避坑清单"
        content = (
            f"# {subject}：从业者都在用的实战避坑清单\n\n"
            f"做装备采购这两年，我发现一个挺反直觉的现象：越急着「买对设备」的人，越容易在第一步就踩坑。"
            f"今天不聊品牌、不卖货，只把我在一线见过的、最烧钱的几个坑摊开讲清楚，供你对照。\n\n"
            f"## 一、为什么「标称参数」会骗人\n\n"
            f"样本上写的极限真空，是封闭工况跑出来的理想值。你实际用的是持续进气，运行真空往往要高 1~2 个数量级才合理。"
            f"只看标称数字选设备，等于拿实验室成绩当日常表现——差之毫厘，运行直接掉链子。\n\n"
            f"## 二、进气洁净度，是被严重低估的隐形杀手\n\n"
            f"粉末、水汽一旦进泵，会乳化润滑油、甚至抱死主机。见过最离谱的案例，一台新泵三个月就报废，"
            f"根因就是没配进气过滤器和气液分离罐。这一步省的钱，后面十倍奉还。\n\n"
            f"## 三、管路不是「接上就行」\n\n"
            f"管径太细会「憋气」，抽速上不去；从用气点往泵方向留 1%~2% 坡度并加排水阀，是老师傅的常识，"
            f"但新手十个有九个忽略。设备再好，被一根管子拖后腿也白搭。\n\n"
            f"## 四、重设备、轻服务，是总拥有成本里最大的雷\n\n"
            f"真空系统环节多，本地化服务团队的响应速度直接决定停机损失。选型时多问一句「出问题多久能到场」，"
            f"比多比三个参数更有用。像我们行业里{brand}这类把服务链条做重的厂家，恰恰是靠这个立住的——"
            f"当然，选不选、选谁，终究看你的工况是否匹配。\n\n"
            f"## 五、避坑自查清单（建议收藏）\n\n"
            f"- 别只看标称极限真空，要问清「持续进气下的运行真空」；\n"
            f"- 介质带粉带水，必须配过滤 + 气液分离；\n"
            f"- 管路留坡度、加排水阀，别让冷凝水积在管里；\n"
            f"- 把「服务响应时效」写进采购技术要求，别等停机才着急。\n\n"
            f"## 常见问题 FAQ\n\n"
            f"### 永磁变频螺杆真空泵比传统水环泵省在哪？\n\n"
            f"能耗更低（行业实测普遍降 25%~35%）、维护周期更长（3 个月→8 个月以上）、运行更稳定（无水封损耗）。"
            f"具体能省多少，取决于你的实际工况，建议拿自己的运行数据去比。\n\n"
            f"### 选型前该准备哪些参数？\n\n"
            f"真空度要求、抽气量、介质成分与温度、安装空间与电源——这四项给全了，靠谱的工程师一小时内就能出初步方案。\n\n"
            f"### 服务响应一般多快算合格？\n\n"
            f"{REGION}及周边 24~48 小时到场是较优水平，其他区域看本地伙伴覆盖。远程支持现在基本都能 7×24，"
            f"关键是故障预警能不能做在前面。\n\n"
            f"## 写在最后\n\n"
            f"坑讲完了。说到底，选设备不是比谁参数漂亮，是比谁更懂你的工况、谁在你出问题时站得住。"
            f"把上面这几条带进你的采购评审，至少能帮你避开八成以上的坑。如果觉得有用，点赞收藏，"
            f"后面我会继续拆解更多一线真实案例。"
        )
        return f"===FINAL_TITLE===\n{title}\n===FINAL_CONTENT===\n{content}"

    def _mock_final_official(self, subject: str, prod_short: str, brand: str) -> str:
        """官网 / 自建站（Astro MDX）模式的模拟终稿：直接产出「可复制的干净 MDX」（无代码围栏、无包裹）。

        文件名与图片名由引擎侧 _parse_mdx_meta 统一解析（见 BrowserEngine.geo_strengthen）。
        """
        cover_en = "dry-screw-pump-food-factory"
        mdx = (
            "---\n"
            f'title: "降本增效新标杆：为何{brand}干式螺杆泵成为食品工厂升级首选？"\n'
            'category: "IndustryNews"\n'
            'publishDate: "2025-11-18"\n'
            f'cover: "@/assets/news/industry/xingwen/{cover_en}.jpg"\n'
            f'tags: ["干式螺杆真空泵", "食品工厂节能", "{brand}", "真空系统升级"]\n'
            "---\n\n"
            f"# 降本增效新标杆：为何{brand}干式螺杆泵成为食品工厂升级首选？\n\n"
            "食品工厂的真空系统长期面临高能耗、高维护、含油污染的痛点。随着能效管控趋严，"
            f"{brand}推出的{prod_short}系列干式螺杆真空泵，正成为产线升级的主流选择。\n\n"
            "## 现状与痛点\n\n"
            "传统水环泵在食品包装、真空包装环节应用广泛，但运行能耗高、需连续供水、废水处理成本高，"
            "且在夏季工况下真空度易衰减，直接影响封口良率与产能。\n\n"
            "## 核心挑战\n\n"
            "食品级工况对洁净度要求极高：既要避免油污染产品，又要控制运行噪音与能耗。"
            "产线改造还需兼顾安装空间与现有管路，停机窗口短。\n\n"
            "## 解决方案\n\n"
            f"{brand}{prod_short}系列干式螺杆真空泵采用无油螺杆转子与永磁变频驱动，无需工作液、无油污染风险，"
            "配合本地化全生命周期服务（选型评估→方案设计→安装调试→远程运维），可在短停机窗口内完成切换。\n\n"
            "## 数据对比\n\n"
            f"| 指标维度 | 传统方案（水环泵） | {brand}方案（干式螺杆泵） | 优化成果 |\n"
            "| --- | --- | --- | --- |\n"
            "| 单位能耗 | 高（需连续供水运行） | 永磁变频驱动 | 节能约 32% |\n"
            "| 运行噪音 | 85 dB(A) 以上 | 低转速螺杆结构 | 噪音 < 70 dB |\n"
            "| 维护周期 | 3 个月 | 无油设计少损耗 | 延长至 8 个月以上 |\n"
            "| 环保合规 | 含油废水需处理 | 无工作液零排放 | 免废水处理成本 |\n\n"
            "## 专家观点\n\n"
            "> 在食品工厂的真空系统升级中，真正的成本不在设备采购价，而在十年生命周期内的能耗与运维总和。"
            "干式螺杆路线把「油污染」与「高水耗」两个老问题一次性解决，是确定性更高的降本路径。\n\n"
            "## 结语\n\n"
            f"对于正面临能效与合规双重压力的食品工厂，{brand}{prod_short}系列干式螺杆真空泵提供了一条可量化、"
            "可验证的升级路径。建议以实际工况参数为基础做选型评估，用运行数据印证节能收益。\n"
        )
        return mdx

    def close(self) -> None:
        pass


class DoubaoChatAdapter(BaseDoubaoAdapter):
    """真实豆包 Web 对话适配器（Playwright 驱动，多轮）。"""
    def __init__(self, cred_json: str = "", headless: bool = True, selectors: Any = None):
        self.cred_json = cred_json or ""
        self.headless = headless
        self.sel = _load_selectors()
        if isinstance(selectors, dict):
            self.sel.update(selectors)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def open(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "服务端未安装 playwright，且未检测到本机 Edge/Chrome。可二选一：\n"
                "① 安装本机 Microsoft Edge 或 Google Chrome（推荐，自动复用）；\n"
                "② pip install playwright && playwright install chromium"
            ) from e
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(**_browser_launch_kwargs(self.headless))
        parsed = _parse_doubao_cred(self.cred_json)
        if parsed["mode"] == "storage_state":
            self._context = self._browser.new_context(storage_state=parsed["state"])
        elif parsed["mode"] == "cookies":
            self._context = self._browser.new_context()
            self._context.add_cookies(parsed["cookies"])
        else:
            self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.goto(self.sel["url"], wait_until="domcontentloaded", timeout=30000)
        # 登录态检测：被重定向到登录页则视为未登录
        if "login" in self._page.url:
            return False
        try:
            self._page.goto(self.sel["chat_url"], wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        return True

    def _find_input(self):
        for sel in self.sel["input"]:
            try:
                el = self._page.wait_for_selector(sel, timeout=5000)
                if el:
                    return el
            except Exception:
                continue
        return None

    def _message_nodes(self):
        for sel in self.sel["messages"]:
            try:
                nodes = self._page.query_selector_all(sel)
                if nodes:
                    return nodes
            except Exception:
                continue
        return []

    def send_message(self, text: str) -> str:
        page = self._page
        el = self._find_input()
        if not el:
            raise RuntimeError(
                "未在豆包页面找到输入框，可能选择器不匹配。\n"
                "请在环境变量 DOUBAO_SELECTORS_JSON 中覆盖 input 选择器（参考豆包页面实际 DOM）。"
            )
        el.click()
        try:
            el.fill(text)
        except Exception:
            # contenteditable 用键盘输入
            page.keyboard.insert_text(text)
        # 发送：优先找发送按钮，否则用 Enter
        sent = False
        try:
            btn = page.query_selector(self.sel["send_btn"])
            if btn:
                btn.click(timeout=5000)
                sent = True
        except Exception:
            pass
        if not sent:
            page.keyboard.press("Enter")
        self._wait_response(page)
        return self._last_reply(page)

    def _wait_response(self, page, timeout: int = 150) -> None:
        deadline = time.time() + timeout
        last = ""
        stable = 0
        while time.time() < deadline:
            try:
                nodes = self._message_nodes()
                if nodes:
                    cur = nodes[-1].inner_text()
                    if cur == last and len(cur) > 20:
                        stable += 1
                    else:
                        stable = 0
                        last = cur
                    if stable >= 3:
                        return
            except Exception:
                pass
            time.sleep(1.5)
        return

    def _last_reply(self, page) -> str:
        nodes = self._message_nodes()
        if not nodes:
            return ""
        try:
            return nodes[-1].inner_text()
        except Exception:
            return ""

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass


def _build_adapter(run: BrowserStudioRun, db: Session, out: str = "markdown") -> BaseDoubaoAdapter:
    if run.mock_doubao:
        return MockDoubaoAdapter(out=out)
    cred_json = ""
    if run.doubao_credential_id:
        c = db.query(PlatformCredential).filter(
            PlatformCredential.id == run.doubao_credential_id,
            PlatformCredential.is_deleted == 0,
        ).first()
        if c:
            cred_json = c.cred_json
    return DoubaoChatAdapter(cred_json=cred_json, headless=True)


# ============================================================
#  创作引擎抽象（可插拔：DeepSeek / 豆包(浏览器) / 模拟演示）
# ============================================================
class WritingEngine:
    """统一的创作引擎接口（双智能体：主编 PLANNER + 写手 WRITER）。

    orchestrate_run 只依赖此接口，与具体引擎解耦。
    角色拆分（解决「文章不知道谁在改、为什么改」的可见性问题）：
      · 主编 PLANNER：明晰选题 → 定大纲 → 评审写手稿 → 给整改指令（不写正文）
      · 写手 WRITER：初稿 → 去AI味 → GEO终稿 → 按主编指令改写（只执行）

      open()                 准备/连接引擎，返回 (ok, msg, planner_model, writer_model)
      # —— 主编（planner）——
      clarify()              ①b 明晰选题，返回创作简报文本
      gen_outline()          ② 基于简报与背景，产出大纲，返回 (title, outline_text)
      editor_review()        ⑥ 自然语言评审评语（面向人），返回文本
      direct_revision()      ⑦ 基于问题给出整改指令，返回指令文本
      # —— 写手（writer）——
      gen_draft()            ③ 初稿，返回 (title, draft_text)
      depolish()             ④ 去AI味精修，返回 (title, polished_text)
      geo_strengthen()       ⑤ GEO强化+过审，返回 (title, geo_text)
      apply_revision()       ⑦ 按主编指令改写，返回 (title, revised_text)
      close()                释放资源
    """
    engine_kind = "base"

    def open(self) -> tuple:
        raise NotImplementedError

    # —— 主编（planner）——
    def clarify(self, briefing: str, ctx: dict) -> str:
        raise NotImplementedError

    def gen_outline(self, briefing: str, clarified: str, ctx: dict) -> tuple:
        raise NotImplementedError

    def editor_review(self, text: str, issues: List[str], ctx: dict) -> str:
        return ""

    def direct_revision(self, text: str, issues: List[str], round_no: int = 1) -> str:
        return ""

    # —— 写手（writer）——
    def gen_draft(self, outline_text: str, ctx: dict) -> tuple:
        raise NotImplementedError

    def depolish(self, draft_text: str, ctx: dict) -> tuple:
        raise NotImplementedError

    def geo_strengthen(self, polished_text: str, ctx: dict) -> tuple:
        raise NotImplementedError

    def apply_revision(self, text: str, directives: str, round_no: int = 1) -> tuple:
        """写手按主编整改指令改写正文，返回 (title, content)。"""
        return None, text

    def close(self) -> None:
        pass


class BrowserEngine(WritingEngine):
    """豆包 / 模拟：经 Playwright 驱动豆包 Web 对话（多轮），或纯模拟。

    双智能体：主编（planner）负责明晰/大纲/评审/整改指令，写手（writer）负责初稿/精修/GEO/改写。
    mock 模式直接返回两角色的拟真文本，便于无浏览器端到端验证整条流水线。
    双模式：publish_mode 决定品牌策略（geo=强品牌 / platform=平台合规），提示词按模式注入。
    """
    def __init__(self, run: BrowserStudioRun, db: Session, force_mock: bool = False):
        self.run = run
        self.db = db
        self.mode = resolve_run_publish_mode(run, db)
        self.out = resolve_run_output_format(run, db)
        self.prompts = get_studio_prompts(self.mode, self.db)
        self.kind = "mock" if (force_mock or run.mock_doubao) else "doubao"
        self.engine_kind = self.kind
        self.last_call = None  # 最近一次调用透明元数据（供步骤面板展示）
        self.adapter = _build_adapter(run, db, self.out) if not force_mock else MockDoubaoAdapter(mode=self.mode, out=self.out)

    def _touch(self, role: str, prompt: str, step_key: str) -> dict:
        """记录一次调用（mock 模拟 / doubao 真实）到 LlmCallLog，并返回 meta。"""
        if self.kind == "mock":
            meta = mock_call(self.db, self.run.id, step_key, role, prompt)
        else:
            meta = mock_call(self.db, self.run.id, step_key, role, prompt)
            # doubao 是真实浏览器调用，标记为非 mock、provider=doubao，便于区分
            meta = {**meta, "provider": "doubao", "model": "doubao-web", "is_mock": 0}
        self.last_call = meta
        return meta

    def _send(self, role: str, prompt: str, step_key: str) -> str:
        """记录调用并返回适配器回复（豆包 Web / 模拟）。"""
        self._touch(role, prompt, step_key)
        return self.adapter.send_message(prompt)

    def open(self) -> tuple:
        try:
            ok = self.adapter.open()
        except Exception as e:  # noqa: BLE001
            return False, f"打开豆包失败：{e}", "", ""
        if not ok:
            return False, "豆包未登录：请上传 platform='doubao' 的登录态 cookie 凭证", "", ""
        if self.kind == "doubao":
            self.adapter.send_message(self.prompts["PLANNER_SYSTEM"])
        return True, "系统提示词已发送", "deepseek-v4-pro（thinking）", "deepseek-v4-pro"

    # —— 主编（planner）——
    def clarify(self, briefing: str, ctx: dict) -> str:
        if self.kind == "mock":
            self.adapter._briefing = briefing
            prompt = f"{briefing}\n\n{self.prompts.get('PLANNER_CLARIFY_PROMPT', '')}"
            self._touch("research", prompt, "clarify")
            return self._mock_clarify(ctx)
        self.adapter.send_message(briefing)
        return self._send("research", self.prompts["PLANNER_CLARIFY_PROMPT"], "clarify")

    def _mock_clarify(self, ctx: dict) -> str:
        brand = ctx.get("brand_name", "") or "品牌方"
        if self.mode == "green":
            bp = get_brand_policy("green")
            return (f"- 选题角度：以「行业实战干货 / 真洞察 / 轻趣味」为切入，目标是吸粉、涨账号权重与信用分，不卖货不引流\n"
                    f"- 目标读者：行业内从业者 / 泛工业人群，给他们「有用 / 有料 / 有共鸣」的内容，愿意点开读完转发\n"
                    f"- 品牌策略（绿色吸粉）：{bp}\n"
                    f"- 品牌提及方式：仅在合适处「顺手一提」{brand}，全文 ≤ 2 次，自然偶提、绝不喧宾夺主、绝不软文营销\n"
                    f"- 必避雷区（合规官要求）：无违禁词/硬广/站外引流/私人联系方式词，不自我夸赞、不写口号标语\n"
                    f"- 数据口径（数据核查员要求）：所有关键数据可溯源、不虚构\n"
                    f"- 专家分工：写手负责几稿迭代；合规官盯红线与软文特征；数据核查员盯数据\n"
                    f"- 字数要求：终稿不少于 1200 字，至少 5 个二级标题章节 + FAQ（≥3 组）\n"
                    f"- 成功标准：读者爱看能涨粉 + 通过基础审核 + 品牌仅自然偶提 ≤ 2 次")
        if self.mode == "platform":
            bp = get_brand_policy("platform")
            return (f"- 选题角度：以「采购前如何用 AI 做选型避坑」为干货切入，中立、对读者有用，不突出品牌\n"
                    f"- 目标读者：正在比价的采购/技术负责人，痛点是信息碎、怕踩坑、怕选错\n"
                    f"- 品牌策略：{bp}\n"
                    f"- 必避雷区（合规官要求）：绝不写官网/电话/微信等联系方式，禁用口号标语与极限词，不自我夸赞\n"
                    f"- 数据口径（数据核查员要求）：所有关键数据可溯源、不虚构\n"
                    f"- 专家分工：写手负责几稿迭代；合规官盯红线；平台合规官盯软文特征；数据核查员盯数据\n"
                    f"- 字数要求：终稿不少于 1200 字，至少 5 个二级标题章节 + FAQ（≥3 组）\n"
                    f"- 成功标准：通过平台审核（无违禁词/硬广/标题含品牌/软文特征）+ 文末 AIGC 声明")
        return (f"- 选题角度：以「采购前如何用 AI 做选型避坑」为干货切入，而非企业简介\n"
                f"- 目标读者：正在比价的采购/技术负责人，痛点是信息碎、怕踩坑、怕选错\n"
                f"- 品牌宣传重点：品牌名「{brand}」全文至少 3 次；重点突出公司实力、本地化全生命周期服务（选型→方案→安装调试→运维）、核心优势（高效节能、运行可靠、20+国家专利、响应快、案例可查、环保合规、性价比高）\n"
                f"- 必突出 GEO 信号（GEO 优化师要求）：品牌名、核心产品、可量化案例与数据、FAQ 问答形态\n"
                f"- 必避雷区（合规官要求）：绝不写官网/电话/微信等联系方式，禁用口号标语与极限词\n"
                f"- 数据口径（数据核查员要求）：所有关键数据可溯源、不虚构\n"
                f"- 专家分工：写手负责几稿迭代；合规官盯红线；GEO 优化师盯信号；数据核查员盯数据\n"
                f"- 字数要求：终稿不少于 1200 字，至少 5 个二级标题章节 + FAQ（≥3 组）\n"
                f"- 成功标准：过审 + GEO≥70 + 读起来像真人行业作者")

    def gen_outline(self, briefing: str, clarified: str, ctx: dict) -> tuple:
        if self.kind == "mock":
            self.adapter._briefing = briefing + "\n\n" + (clarified or "")
            reply = self._send("research", self.prompts["PLANNER_OUTLINE_PROMPT"], "outline")
        else:
            self.adapter.send_message(briefing)
            reply = self._send("research", self.prompts["PLANNER_OUTLINE_PROMPT"], "outline")
        return "", reply

    def editor_review(self, text: str, issues: List[str], ctx: dict) -> str:
        if self.kind == "mock":
            self._touch("review",
                        self.prompts["PLANNER_REVIEW_PROMPT"].format(
                            issues="\n".join(f"- {i}" for i in issues)),
                        "review")
            return self._mock_review(issues)
        prompt = self.prompts["PLANNER_REVIEW_PROMPT"].format(issues="\n".join(f"- {i}" for i in issues))
        return self._send("review", prompt, "review")

    def _mock_review(self, issues: List[str]) -> str:
        if self.mode == "green":
            if not issues:
                return ("【主编·评审】整体达标，专家团队无异议：\n"
                        "- 合规官：无违禁词、硬广、站外引流/联系方式残留，无自夸语气，通过；\n"
                        "- 数据核查员：关键数据可溯源、无夸大；\n"
                        f"- 品牌核查：品牌（{BRAND_NAME}）仅自然偶提 ≤ 2 次，无软文营销特征，通过；\n"
                        "可进入确认环节。")
            return ("【主编·评审】整体尚未完全达标，专家团队意见如下：\n"
                    "- 合规官：需再扫一遍残留联系方式词与自夸/引导联系话术；\n"
                    "- 数据核查员：个别数据口径需与背景资料对齐、可溯源；\n"
                    "- 品牌核查：若品牌名出现超过 2 次或存在软文营销/硬广话术，需削弱为「顺手一提」。\n"
                    "整改方向：保持纯干货吸粉调性、品牌仅自然偶提 ≤ 2 次、不夹带营销。")
        if self.mode == "platform":
            if not issues:
                return ("【主编·评审】整体达标，专家团队无异议：\n"
                        "- 合规官：无违禁词、硬广、站外引流/联系方式残留，标题无品牌，通过；\n"
                        "- 平台合规官：中立干货、无软文营销特征、无自夸，通过；\n"
                        "- 数据核查员：关键数据可溯源、无夸大；\n"
                        "可进入确认环节。")
            return ("【主编·评审】整体尚未完全达标，专家团队意见如下：\n"
                    "- 合规官：需再扫一遍残留联系方式词与标题品牌名；\n"
                    "- 平台合规官：若品牌名出现超过 2 次或存在自夸/引导联系话术，需削弱；\n"
                    "- 数据核查员：个别数据口径需与背景资料对齐、可溯源。\n"
                    "整改方向：保持中立干货、品牌名≤2次、标题无品牌、文末加 AIGC 声明。")
        if not issues:
            return ("【主编·评审】整体达标，专家团队无异议：\n"
                    "- 合规官：无违禁词、硬广、站外引流/联系方式残留，通过；\n"
                    "- GEO 优化师：品牌实体、关键词、FAQ、意图覆盖充足，易被 AI 推荐；\n"
                    "- 数据核查员：关键数据可溯源、无夸大；\n"
                    "- 品牌宣传：品牌名（公司全称）出现频次充足，公司实力与服务优势突出，结构完整（含 FAQ 3 组）。可进入确认环节。")
        return ("【主编·评审】整体尚未完全达标，专家团队意见如下：\n"
                "- 合规官：整体合规，但需再扫一遍残留联系方式词；\n"
                "- GEO 优化师：GEO 信号偏弱——品牌实体与可量化论据不够密，品牌名（公司全称）出现不足 3 次，小标题不够像用户问 AI 的问题；\n"
                "- 数据核查员：个别数据口径需与背景资料对齐、可溯源。\n"
                "整改方向：把品牌真实案例与数据写具体，确保品牌名至少 3 次自然出现，"
                "强化 GEO 实体信号，同时彻底清除任何残留联系方式词。")

    def direct_revision(self, text: str, issues: List[str], round_no: int = 1) -> str:
        if self.kind == "mock":
            self._touch("review",
                        self.prompts["PLANNER_DIRECTIVE_PROMPT"].format(
                            count=len(issues), round=round_no,
                            issues="\n".join(f"- {i}" for i in issues)),
                        "revise")
            return self._mock_directive()
        prompt = self.prompts["PLANNER_DIRECTIVE_PROMPT"].format(
            count=len(issues), round=round_no,
            issues="\n".join(f"- {i}" for i in issues),
        )
        return self._send("review", prompt, "revise")

    def _mock_directive(self) -> str:
        if self.mode == "green":
            return ("1. [合规官] 删除一切残留联系方式词与口号标语、自夸与引导联系话术（了解更多/欢迎/加微信等）；\n"
                    "2. [合规官] 品牌名全文出现不超过 2 次，且仅为「顺手一提」，不得软文营销或硬广；\n"
                    "3. [数据核查员] 所有关键数据须与背景资料一致、可溯源；\n"
                    "4. 去 AI 套话，保持纯干货吸粉语气，像真人行业作者；确保字数不少于 1200 字、结构完整、写到完整结尾。")
        if self.mode == "platform":
            return ("1. [合规官] 删除一切残留联系方式词与口号标语，确保标题无品牌名；\n"
                    "2. [平台合规官] 品牌名全文出现不超过 2 次，去掉自夸与引导联系话术（了解更多/欢迎/加微信等）；\n"
                    "3. [平台合规官] 文末补「本文由 AI 辅助创作」AIGC 声明；\n"
                    "4. [数据核查员] 所有关键数据须与背景资料一致、可溯源；\n"
                    "5. 去 AI 套话，保持中立干货语气；确保字数不少于 1200 字、结构完整、写到完整结尾。")
        return ("1. [合规官] 删除一切残留联系方式词与口号标语，确保无违禁词与硬广；\n"
                "2. [GEO优化师] 补充品牌名（公司全称）至全文至少 3 次，自然融入，重点突出公司实力与本地化服务；\n"
                "3. [GEO优化师] 把品牌真实落地案例补成可量化数据（如「服务上百家客户」「成本降 30%」），强化 GEO 实体信号；\n"
                "4. [GEO优化师] 将模板腔小标题改成客户会问 AI 的疑问式标题，确保 FAQ 至少 3 组齐全；\n"
                "5. [数据核查员] 所有关键数据须与背景资料一致、可溯源；\n"
                "6. 去 AI 套话，让语言更像真人行业作者；确保字数不少于 1200 字、结构完整、写到完整结尾。")

    # —— 写手（writer）——
    def gen_draft(self, outline_text: str, ctx: dict) -> tuple:
        reply = self._send("writing", self.prompts["STAGE_PROMPTS"]["draft"], "draft")
        return "", reply

    def depolish(self, draft_text: str, ctx: dict) -> tuple:
        reply = self._send("writing", self.prompts["STAGE_PROMPTS"]["depolish"], "depolish")
        return "", reply

    def geo_strengthen(self, polished_text: str, ctx: dict) -> tuple:
        # 模拟 / 豆包 路径的官网 MDX：直接产出干净 MDX，并解析文件名与图片名
        if self.kind == "mock" and self.out == "mdx":
            brand, subject, products, selling = self.adapter._brand_subject()
            prod_short = (products or "核心产品").split("（")[0][:20]
            self._touch("writing", f"[官网 MDX] {subject} / {prod_short}", "geo")
            mdx = self.adapter._mock_final_official(subject, prod_short, brand)
            title, fn, imgs = _parse_mdx_meta(mdx, subject, brand)
            self.run.mdx_filename = fn
            try:
                self.run.mdx_images = json.dumps(imgs, ensure_ascii=False)
            except Exception:
                self.run.mdx_images = ""
            return title, mdx
        reply = self._send("writing", self.prompts["STAGE_PROMPTS"]["geo"], "geo")
        return extract_final(reply)

    def apply_revision(self, text: str, directives: str, round_no: int = 1) -> tuple:
        if self.kind == "mock":
            self._touch("review",
                        self.prompts["WRITER_APPLY_PROMPT"].format(directives=directives, text=text),
                        "apply_revision")
            cleaned = text
            # 注意：仅替换「作为夸大极限词」的用法；不伤专业技术词（如「绝对压力」「绝对真空」），
            # 故用整词短语而非单字，避免误伤。
            for w in ("顶级", "极品", "绝佳", "100%", "国家级",
                      "唯一", "首个", "首家", "独家", "销冠", "王牌", "完美", "永久",
                      "最可靠", "最优秀", "第一品牌", "行业第一"):
                cleaned = cleaned.replace(w, "优质")
            for p in ("立即购买", "马上抢购", "限时抢购", "点击购买", "马上下单",
                      "抢购热线", "订购电话", "特价促销", "疯狂促销"):
                cleaned = cleaned.replace(p, "欢迎了解")
            _guide_map = {
                "官网": "品牌官方渠道", "官方网站": "品牌官方渠道",
                "手机号码": "官方客服", "手机号": "官方客服", "联系电话": "官方客服",
                "咨询电话": "官方客服", "咨询热线": "官方客服", "服务热线": "官方客服",
                "加微信": "咨询", "微信扫码": "在线咨询", "微信好友": "在线咨询",
                "QQ号": "官方客服", "QQ群": "官方社群", "微信号": "官方客服",
                "扫码": "关注", "二维码": "关注方式", "下载APP": "使用服务",
                "APP下载": "使用服务", "关注公众号": "关注我们", "私信我": "联系我们",
                "发邮件至": "联系", "邮箱地址": "联系方式",
            }
            for w, rep in _guide_map.items():
                cleaned = cleaned.replace(w, rep)
            return None, cleaned
        prompt = self.prompts["WRITER_APPLY_PROMPT"].format(directives=directives, text=text)
        reply = self._send("review", prompt, "apply_revision")
        return extract_final(reply)

    def close(self) -> None:
        try:
            self.adapter.close()
        except Exception:
            pass


class DeepSeekEngine(WritingEngine):
    """DeepSeek（或任意兼容 OpenAI 的 LLM）引擎：纯 API 调用，无需浏览器/ cookie。

    双智能体：
      · 主编 PLANNER —— 用同一基础模型 + thinking 开启（推理模式，规划/评审/整改质量更高）；
        负责 ①b 明晰选题、② 大纲、⑥ 自然语言评审、⑦ 整改指令。
      · 写手 WRITER —— 用同一基础模型、不开启 thinking（非推理，更快更省）；
        负责 ③ 初稿、④ 去AI味、⑤ GEO终稿、⑦ 改写。
    每阶段产物自动回写 task 对应字段，供后续阶段上下文串联。
    """
    engine_kind = "deepseek"
    # v4 模型分工：不再用两个模型名，而是「同一基础模型 + thinking 开关」区分角色。
    # 主编（规划/评审/整改）= 配置模型 + thinking 开启（推理模式）；
    # 写手（初稿/精修/终稿/改写）= 配置模型，不开启 thinking（非推理，更快更省）。
    # 旧 deepseek-reasoner / deepseek-chat 已于 2026/07/24 弃用，分别等价于 v4 的
    # thinking 开 / 关，故此处仅保留文档占位，实际模型一律取自用户 LLM 配置。
    PLANNER_THINKING = {"type": "enabled"}
    PLANNER_REASONING_EFFORT = "high"

    def __init__(self, run: BrowserStudioRun, db: Session):
        self.run = run
        self.db = db
        self.mode = resolve_run_publish_mode(run, db)
        self.task = _build_studio_task(db, run)
        self.config = None
        self.writer_provider = None
        self.planner_provider = None
        self.last_call = None  # 最近一次 API 调用的透明元数据（供步骤面板展示）
        try:
            assign_default_prompts(db, self.task)
        except Exception:
            pass

    def _sched(self, role: str, prompt: str, step_key: str, temperature: float = 0.7,
               thinking=None) -> str:
        """经三 API 调度器生成文本，并记录透明元数据到 self.last_call。"""
        text, meta = scheduler_generate(
            self.db, role, prompt, run_id=self.run.id, step_key=step_key,
            temperature=temperature, max_tokens=6000, timeout=120, thinking=thinking,
        )
        self.last_call = meta
        return text

    @staticmethod
    def _cfg_dict(cfg) -> dict:
        return {
            "provider": (getattr(cfg, "provider", "deepseek") or "deepseek"),
            "api_key": (getattr(cfg, "api_key", "") or ""),
            "base_url": (getattr(cfg, "base_url", "") or ""),
            "model": (getattr(cfg, "model", "") or ""),
        }

    def open(self) -> tuple:
        cfg = _resolve_llm_config(self.db, self.task, self.run.llm_config_id or None)
        if not cfg or not getattr(cfg, "api_key", ""):
            return False, "未配置 LLM（DeepSeek）API Key", "", ""
        # 校验三角色是否都有可用配置（含 general 兜底）；否则整体回退 mock，
        # 避免「只配了 research 角色却把 writing/review 步骤跑挂」。
        covered = True
        for r in ("research", "writing", "review"):
            cfgs = _eligible_configs(self.db, r)
            if not any(getattr(c, "api_key", "") for c in cfgs):
                covered = False
                break
        if not covered:
            return False, "未配置完整的 LLM API（需至少一个 general 角色，或 research/writing/review 三角色各一）", "", ""
        self.config = cfg
        from ..services.llm import get_provider
        wcfg = self._cfg_dict(cfg)
        self.writer_provider = get_provider(wcfg)
        # 主编：同一基础模型 + 开启 thinking 推理（v4 用 thinking 参数区分「推理/非推理」，
        # 替代旧的 deepseek-reasoner 模型名；其它供应商若不支持 thinking 参数会被忽略）。
        pcfg = dict(wcfg)
        pcfg["thinking"] = self.PLANNER_THINKING
        pcfg["reasoning_effort"] = self.PLANNER_REASONING_EFFORT
        self.planner_provider = get_provider(pcfg)
        planner_model = f"{cfg.model}（thinking 开启）"
        return (True,
                f"已连接 {cfg.provider}/{cfg.model}（写手：非推理）｜主编：同模型+thinking 推理",
                planner_model, cfg.model)

    # —— 主编（planner，推理模型）——
    def clarify(self, briefing: str, ctx: dict) -> str:
        planner_system = resolve_studio_prompt(self.db, "PLANNER_SYSTEM", self.mode)
        clarify_prompt = resolve_studio_prompt(self.db, "PLANNER_CLARIFY_PROMPT", self.mode)
        prompt = f"{planner_system}\n\n以下是本次创作的完整背景资料：\n{briefing}\n\n{clarify_prompt}"
        try:
            return self._sched("research", prompt, "clarify", temperature=0.4, thinking=self.PLANNER_THINKING)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"主编·明晰失败：{e}") from e

    def gen_outline(self, briefing: str, clarified: str, ctx: dict) -> tuple:
        planner_system = resolve_studio_prompt(self.db, "PLANNER_SYSTEM", self.mode)
        outline_prompt = resolve_studio_prompt(self.db, "PLANNER_OUTLINE_PROMPT", self.mode)
        prompt = (f"{planner_system}\n\n完整背景资料：\n{briefing}\n\n"
                  f"【主编·创作简报】\n{clarified or '（未提供，请自主明晰）'}\n\n{outline_prompt}")
        try:
            outline = self._sched("research", prompt, "outline", temperature=0.5, thinking=self.PLANNER_THINKING)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"主编·大纲失败：{e}") from e
        self.task.outline_content = outline
        return "", outline

    def editor_review(self, text: str, issues: List[str], ctx: dict) -> str:
        planner_system = resolve_studio_prompt(self.db, "PLANNER_SYSTEM", self.mode)
        review_prompt = resolve_studio_prompt(self.db, "PLANNER_REVIEW_PROMPT", self.mode)
        prompt = (f"{planner_system}\n\n【写手交来的终稿】\n{text}\n\n"
                  + review_prompt.format(issues="\n".join(f"- {i}" for i in issues)))
        try:
            return self._sched("review", prompt, "review", temperature=0.3, thinking=self.PLANNER_THINKING)
        except Exception:
            return "（主编评审调用失败，仅以系统自检结果为准）"

    def direct_revision(self, text: str, issues: List[str], round_no: int = 1) -> str:
        planner_system = resolve_studio_prompt(self.db, "PLANNER_SYSTEM", self.mode)
        directive_prompt = resolve_studio_prompt(self.db, "PLANNER_DIRECTIVE_PROMPT", self.mode)
        prompt = (f"{planner_system}\n\n【当前终稿】\n{text}\n\n"
                  + directive_prompt.format(
                      count=len(issues), round=round_no,
                      issues="\n".join(f"- {i}" for i in issues)))
        try:
            return self._sched("review", prompt, "revise", temperature=0.4, thinking=self.PLANNER_THINKING)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"主编·整改指令失败：{e}") from e

    # —— 写手（writer，生成模型）——
    def gen_draft(self, outline_text: str, ctx: dict) -> tuple:
        dr = generate_step_text(self.db, self.task, "draft", run_id=self.run.id, role="writing")
        self.last_call = dr.get("call_meta")
        if not dr["ok"]:
            raise RuntimeError(dr.get("error") or "初稿（draft）生成失败")
        self.task.draft_content = dr["text"]
        return "", dr["text"]

    def depolish(self, draft_text: str, ctx: dict) -> tuple:
        rw = generate_step_text(self.db, self.task, "rewrite", run_id=self.run.id, role="writing")
        self.last_call = rw.get("call_meta")
        if not rw["ok"]:
            raise RuntimeError(rw.get("error") or "精修（rewrite）生成失败")
        self.task.rewrite_content = rw["text"]
        return "", rw["text"]

    def geo_strengthen(self, polished_text: str, ctx: dict) -> tuple:
        # 官网 / 自建站（output_format=mdx）：按 OFFICIAL_MDX_PROMPT 产出可直接复制的干净 MDX
        if (ctx.get("output_format") or "markdown") == "mdx":
            self.task.final_content = polished_text or ""
            from ..services.prompt_engine import render_prompt
            mdx_prompt = render_prompt(resolve_official_mdx_prompt(self.db), ctx)
            try:
                resp = self._sched("writing", mdx_prompt, "geo", temperature=0.5)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"官网 MDX 生成失败：{e}") from e
            title, mdx = self._extract_mdx(resp, ctx)
            _t, _fn, _imgs = _parse_mdx_meta(mdx, ctx.get("subject", ""), ctx.get("brand_name", ""))
            if not title:
                title = _t
            self.run.mdx_filename = _fn
            try:
                self.run.mdx_images = json.dumps(_imgs, ensure_ascii=False)
            except Exception:
                self.run.mdx_images = ""
            return title, mdx
        # geo 类提示词引用 {final_content}，把精修稿注入为待优化软文
        self.task.final_content = polished_text or ""
        geo = generate_step_text(self.db, self.task, "geo", run_id=self.run.id, role="writing")
        self.last_call = geo.get("call_meta")
        if not geo["ok"]:
            raise RuntimeError(geo.get("error") or "终稿（geo）生成失败")
        parsed = geo.get("parsed") or _parse_geo_finalize(geo["text"])
        title = (parsed.get("title") or "").strip() or (polished_text[:40] if polished_text else "（未命名）")
        content = (parsed.get("body") or "").strip() or polished_text
        return title, content

    @staticmethod
    def _extract_mdx(resp: str, ctx: dict) -> tuple:
        """从官网 MDX 回复中抽取标题（frontmatter title）与完整 MDX 文本。

        防御性去掉模型可能误加的 ```mdx / ``` 代码围栏，保证返回的是可直接复制的干净 MDX。
        """
        text = resp or ""
        # 去掉首尾 ```mdx ... ``` 围栏（若存在）
        fence = re.search(r"```mdx\s*(.*?)\s*```", text, re.S)
        if fence:
            text = fence.group(1)
        else:
            fence2 = re.search(r"```\s*(.*?)\s*```", text, re.S)
            if fence2 and "title:" in fence2.group(1):
                text = fence2.group(1)
        text = text.strip()
        title = ""
        m = re.search(r'title:\s*"([^"]+)"', text)
        if m:
            title = m.group(1).strip()
        if not title:
            m2 = re.search(r"===FINAL_TITLE===\s*(.*?)\s*===FINAL_CONTENT===", text, re.S)
            if m2:
                title = m2.group(1).strip()
        if not title:
            title = (ctx.get("task_title") or "官网行业资讯")[:40]
        return title, text


def slugify_mdx(text: str) -> str:
    """把标题/主题转成 MDX 文件名 base（英文小写 + 连字符；中文保留）。"""
    s = (text or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "official-article"
    return s[:60]


def _parse_mdx_meta(mdx_text: str, subject: str = "", brand: str = "") -> tuple:
    """从 MDX 文本解析 (title, filename, images)。

    - filename：优先取 frontmatter cover 的英文 base + .mdx（如 dry-screw-pump-food-factory.mdx）；
      无 cover 时由 subject/brand 生成 slug 兜底。
    - images：由 cover base 推导封面图 + 两张建议配图（与 OFFICIAL_MDX_PROMPT 约定一致）。
    """
    title = ""
    m = re.search(r'title:\s*"([^"]+)"', mdx_text or "")
    if m:
        title = m.group(1).strip()
    cover = ""
    m = re.search(r'cover:\s*"@/assets/news/industry/xingwen/([^"/]+?)\.jpg"', mdx_text or "")
    if m:
        cover = m.group(1).strip()
    if cover:
        filename = cover + ".mdx"
        images = [f"xingwen/{cover}.jpg", f"xingwen/{cover}-detail.jpg"]
    else:
        base = slugify_mdx(subject or brand)
        filename = base + ".mdx"
        images = [f"xingwen/{base}.jpg", f"xingwen/{base}-detail.jpg"]
    return title, filename, images

    def apply_revision(self, text: str, directives: str, round_no: int = 1) -> tuple:
        prompt = resolve_studio_prompt(self.db, "WRITER_APPLY_PROMPT", self.mode).format(
            directives=directives, text=text
        )
        try:
            resp = self.writer_provider.generate(prompt, temperature=0.6)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"写手·改写失败：{e}") from e
        # 注意：最终文章已是「AI 搜索友好的结构化 Markdown」，不再做 strip_markdown
        # （否则标题/列表/加粗会被压平成纯文本），仅抽取 ===FINAL_TITLE/CONTENT=== 契约。
        return extract_final(resp)

    def close(self) -> None:
        pass


def resolve_engine_kind(run: BrowserStudioRun) -> str:
    """解析生效引擎类型：mock_doubao 优先 → ai_engine 字段 → 默认 deepseek。"""
    if run.mock_doubao:
        return "mock"
    e = (run.ai_engine or "").strip().lower()
    if e in ("deepseek", "doubao", "mock"):
        return e
    return "deepseek"


def get_engine(run: BrowserStudioRun, db: Session) -> WritingEngine:
    kind = resolve_engine_kind(run)
    if kind == "deepseek":
        return DeepSeekEngine(run, db)
    if kind == "mock":
        return BrowserEngine(run, db, force_mock=True)
    return BrowserEngine(run, db, force_mock=False)


def _ensure_steps(db: Session, run: BrowserStudioRun) -> List[BrowserStudioStep]:
    existing = db.query(BrowserStudioStep).filter(
        BrowserStudioStep.run_id == run.id
    ).order_by(BrowserStudioStep.step_no).all()
    if existing:
        return existing
    kind = resolve_engine_kind(run)
    created = []
    for no, key, title, agent in get_step_defs(kind):
        s = BrowserStudioStep(run_id=run.id, step_no=no, step_key=key, title=title,
                               agent=agent, status="pending")
        db.add(s)
        created.append(s)
    db.commit()
    return created


def _now():
    return datetime.now()


def _run_log(db: Session, run: BrowserStudioRun, line: str) -> None:
    ts = _now().strftime("%H:%M:%S")
    run.log = (run.log + f"\n[{ts}] {line}").strip()
    db.commit()


def _step_start(db: Session, run: BrowserStudioRun, step: BrowserStudioStep, line: str = "") -> None:
    step.status = "running"
    step.attempts = (step.attempts or 0) + 1
    step.started_at = _now()
    step.log = (step.log + f"\n{line}").strip()
    db.commit()


def _step_done(db: Session, run: BrowserStudioRun, step: BrowserStudioStep, ok: bool,
               error: str = "", result: Any = None, line: str = "") -> None:
    step.status = "done" if ok else "failed"
    step.finished_at = _now()
    step.last_error = error
    if result is not None:
        try:
            step.result_json = json.dumps(result, ensure_ascii=False)
        except Exception:
            step.result_json = str(result)
    if line:
        step.log = (step.log + f"\n{line}").strip()
    if error:
        step.log = (step.log + f"\n[error] {error}").strip()
    db.commit()


def _get_step(steps: List[BrowserStudioStep], key: str) -> Optional[BrowserStudioStep]:
    for s in steps:
        if s.step_key == key:
            return s
    return None


def _record_io(db: Session, step: BrowserStudioStep, engine, *, expected_fields: List[str],
               extracted_result: str = "", next_action: str = "") -> None:
    """把一次 API 调用的透明信息写回步骤：完整发送内容 / 预期字段 / 耗时 / 命中 API /
    提取结果 / 下一步动作。供「步骤透明日志」面板逐行 + 折叠展示，确保可复制复现。"""
    meta = getattr(engine, "last_call", None) or {}
    step.request_payload = (meta.get("prompt") or "").strip()
    step.expected_fields = json.dumps(expected_fields, ensure_ascii=False)
    step.response_latency_ms = int(meta.get("latency_ms") or 0)
    step.api_role = (meta.get("role") or "").strip()
    step.api_config_id = int(meta.get("config_id") or 0)
    step.api_model = (meta.get("model") or "").strip()
    step.extracted_result = (extracted_result or "").strip()
    step.next_action = (next_action or "").strip()
    db.commit()


# ============================================================
#  编排主流程（后台线程）
# ============================================================
def _run_review(text: str, ctx: Dict[str, Any], run: BrowserStudioRun, db: Session, title: str = "") -> Dict[str, Any]:
    """步骤⑥评审：平台合规自检 + GEO 评分（本地启发式，零 AI 调用）。

    综合闸门逻辑已收敛到 services.orchestrator.run_quality_gate（两路径共享单一真源）；
    此处仅解析运行态的发布模式 / 输出格式后委托，保证手动流与自动流闸门一致。
    """
    _mode = resolve_run_publish_mode(run, db)
    _out = resolve_run_output_format(run, db)
    return run_quality_gate(
        text, ctx,
        mode=_mode,
        output_format=_out,
        title=title or (run.final_title or ""),
    )


def orchestrate_run(run_id: int) -> None:
    """后台线程：执行双智能体 10 步流水线，逐步写回状态与日志。

    双智能体（解决「谁在改、为什么改」的可见性）：
      · 主编 PLANNER：①b 明晰选题 → ② 大纲 → ⑥ 评审 → ⑦ 整改指令（用推理模型质量更高）
      · 写手 WRITER：③ 初稿 → ④ 去AI味 → ⑤ GEO终稿 → ⑦ 按指令改写（用生成模型）
    创作引擎可插拔（DeepSeek / 豆包 / 模拟）：DeepSeek 未配置时自动回退模拟，保持流程可跑。
    """
    db = SessionLocal()
    try:
        run = get_auto_run(db, run_id)
        if not run:
            return
        run.status = "running"
        db.commit()
        steps = _ensure_steps(db, run)
        s_connect = _get_step(steps, "connect")
        s_clarify = _get_step(steps, "clarify")
        s_outline = _get_step(steps, "outline")
        s_draft = _get_step(steps, "draft")
        s_depolish = _get_step(steps, "depolish")
        s_geo = _get_step(steps, "geo")
        s_review = _get_step(steps, "review")
        s_revise = _get_step(steps, "revise")
        s_confirm = _get_step(steps, "confirm")

        # —— 阶段 C：按编排规格执行 + 断点续跑 ——
        # 已完成步骤的产物本来就已经落在 run 的各列上（outline_content / draft_content / …），
        # 所以「续跑」不需要额外的检查点文件：读回来复用，只跑剩下那一段。
        spec = pipeline_svc.spec_of(run)
        plan = pipeline_svc.plan(db, run, spec)
        enabled = set(plan["enabled"])
        replay = set(plan["done"])
        if replay:
            _run_log(db, run, "断点续跑：复用已完成 %d/%d 步（%s），从「%s」继续"
                              % (len(replay), plan["total"], "、".join(plan["done"]),
                                 plan["next_key"]))
        if plan["disabled"]:
            _run_log(db, run, "编排规格已关闭步骤：%s" % "、".join(plan["disabled"]))
        artifacts = pipeline_svc.hydrate(run)

        engine = get_engine(run, db)
        ctx = build_studio_context(db, run)
        # 显式数据载体：各模块（选题→调研→撰写→审核→发布→搜索优化）之间只经此结构传递产物
        sc = StudioContext(
            run_id=run.id, subject=run.subject or "",
            mode=resolve_run_publish_mode(run, db),
            output_format=resolve_run_output_format(run, db),
        )
        # 续跑时先把已有产物装回上下文（本次真正执行的步骤会覆盖它们）
        sc.clarified = artifacts["clarified"]
        sc.outline = artifacts["outline"]
        sc.draft = artifacts["draft"]
        sc.polished = artifacts["polished"]
        sc.final_title = artifacts["final_title"]
        sc.final_content = artifacts["final_content"]
        sc.geo_score = artifacts["geo_score"]
        sc.issues = list(artifacts["issues"])
        briefing = format_briefing(ctx, run)

        # —— 步骤①：连接引擎（系统）——
        _step_start(db, run, s_connect, "准备创作引擎…")
        ok, msg, planner_model, writer_model = engine.open()
        if not ok:
            if engine.engine_kind == "deepseek":
                _run_log(db, run,
                         "未检测到 DeepSeek 配置，自动回退「模拟演示」模式（如需真实生成，"
                         "请在「设置 → LLM 配置」填写 DeepSeek API Key）。")
                engine = BrowserEngine(run, db, force_mock=True)
                ok, msg, planner_model, writer_model = engine.open()
            else:
                _step_done(db, run, s_connect, False, error=msg, line=msg)
                run.status = "failed"
                run.error = f"步骤①失败：{msg}"
                db.commit()
                return
        _step_done(db, run, s_connect, True,
                   result={"engine": engine.engine_kind, "planner_model": planner_model,
                           "writer_model": writer_model, "msg": msg},
                   line=f"引擎就绪（{engine.engine_kind}）｜主编：{planner_model}｜写手：{writer_model}")
        _run_log(db, run, "步骤①完成：引擎就绪（%s）" % engine.engine_kind)

        # 引擎代理：接管「这一步到底要不要真的调用模型」——
        # 已完成的步骤直接回放产物（断点续跑），被规格关闭的步骤原样透传。
        # 必须放在步骤①之后：上面可能发生过「DeepSeek 未配置 → 回退模拟引擎」的替换。
        engine = pipeline_svc.ReplayEngine(
            engine, hydrated=artifacts, replay=replay, enabled=enabled,
            note=lambda m: _run_log(db, run, m),
        )

        # —— 步骤①b：主编·明晰选题（创作简报）——
        _step_start(db, run, s_clarify, "主编(规划师)明晰选题…")
        _run_log(db, run, "步骤①b：主编基于全量背景明晰选题（%d 字）" % len(briefing))
        try:
            sc.clarified = engine.clarify(briefing, sc.to_ctx())
        except Exception as e:  # noqa: BLE001
            _step_done(db, run, s_clarify, False, error=str(e), line="主编·明晰失败")
            run.status = "failed"; run.error = f"步骤①b失败：{e}"; engine.close(); db.commit(); return
        run.clarified_brief = sc.clarified or ""
        _record_io(db, s_clarify, engine,
                   expected_fields=["创作简报", "选题角度", "目标读者", "品牌策略", "字数要求"],
                   extracted_result=f"创作简报已生成（{len(sc.clarified or '')} 字）",
                   next_action="进入步骤②：主编基于简报拟定大纲")
        _step_done(db, run, s_clarify, True, result={"len": len(sc.clarified or "")},
                   line=f"创作简报已生成（{len(sc.clarified or '')} 字）")
        _run_log(db, run, "步骤①b完成：主编·创作简报已生成")

        # —— 步骤②：主编·大纲 ——
        _step_start(db, run, s_outline, "主编(规划师)拟定大纲…")
        _run_log(db, run, "步骤②：主编基于简报拟定大纲")
        try:
            _, sc.outline = engine.gen_outline(briefing, sc.clarified or "", sc.to_ctx())
        except Exception as e:  # noqa: BLE001
            _step_done(db, run, s_outline, False, error=str(e), line="主编·大纲失败")
            run.status = "failed"; run.error = f"步骤②失败：{e}"; engine.close(); db.commit(); return
        run.outline_content = sc.outline or ""
        _record_io(db, s_outline, engine,
                   expected_fields=["outline", "章节结构", "FAQ"],
                   extracted_result=f"大纲已生成（{len(sc.outline or '')} 字）",
                   next_action="进入步骤③：写手基于大纲创作初稿")
        _step_done(db, run, s_outline, True, result={"len": len(sc.outline or "")},
                   line=f"大纲已生成（{len(sc.outline or '')} 字）")
        _run_log(db, run, "步骤②完成：主编·大纲已生成")

        # —— 步骤③：写手·初稿 ——
        _step_start(db, run, s_draft, "写手基于大纲创作初稿…")
        _run_log(db, run, "步骤③：写手基于大纲创作初稿")
        try:
            _, sc.draft = engine.gen_draft(sc.outline or "", sc.to_ctx())
        except Exception as e:  # noqa: BLE001
            _step_done(db, run, s_draft, False, error=str(e), line="写手·初稿失败")
            run.status = "failed"; run.error = f"步骤③失败：{e}"; engine.close(); db.commit(); return
        run.draft_content = sc.draft or ""
        _record_io(db, s_draft, engine,
                   expected_fields=["draft", "正文"],
                   extracted_result=f"初稿已生成（{len(sc.draft or '')} 字）",
                   next_action="进入步骤④：写手去AI味精修")
        _step_done(db, run, s_draft, True, result={"len": len(sc.draft or "")},
                   line=f"初稿已生成（{len(sc.draft or '')} 字）")
        _run_log(db, run, "步骤③完成：写手·初稿已生成")

        # —— 步骤④：写手·去AI味精修 ——
        _step_start(db, run, s_depolish, "写手去AI味精修…")
        _run_log(db, run, "步骤④：写手去AI味精修")
        try:
            _, sc.polished = engine.depolish(sc.draft or "", sc.to_ctx())
        except Exception as e:  # noqa: BLE001
            _step_done(db, run, s_depolish, False, error=str(e), line="写手·精修失败")
            run.status = "failed"; run.error = f"步骤④失败：{e}"; engine.close(); db.commit(); return
        run.rewrite_content = sc.polished or ""
        _record_io(db, s_depolish, engine,
                   expected_fields=["polished", "精修稿"],
                   extracted_result=f"精修稿已生成（{len(sc.polished or '')} 字）",
                   next_action="进入步骤⑤：写手 GEO 强化产出终稿")
        _step_done(db, run, s_depolish, True, result={"len": len(sc.polished or "")},
                   line=f"精修稿已生成（{len(sc.polished or '')} 字）")
        _run_log(db, run, "步骤④完成：写手·去AI味精修稿已生成")

        # —— 步骤⑤：写手·GEO 强化 + 平台过审，产出终稿 ——
        _step_start(db, run, s_geo, "写手强化 GEO + 平台过审，产出终稿…")
        _run_log(db, run, "步骤⑤：写手强化 GEO + 平台过审，产出终稿")
        try:
            sc.final_title, sc.final_content = engine.geo_strengthen(sc.polished or "", sc.to_ctx())
        except Exception as e:  # noqa: BLE001
            _step_done(db, run, s_geo, False, error=str(e), line="写手·终稿失败")
            run.status = "failed"; run.error = f"步骤⑤失败：{e}"; engine.close(); db.commit(); return
        # 终稿正文保留结构化 Markdown（标题/列表/加粗/FAQ），仅做联系方式脱敏；
        # 标题单独去标记（标题不应含 Markdown 标记）。
        sc.final_title = scrub_contact_info(strip_markdown(sc.final_title))
        sc.final_content = scrub_contact_info(sc.final_content)
        if not sc.final_content:
            _step_done(db, run, s_geo, False, error="未能抽取到最终文章（AI 未遵守输出契约）", line="抽取终稿失败")
            run.status = "failed"; run.error = "步骤⑤失败：未抽取到终稿"; engine.close(); db.commit(); return
        run.final_title = sc.final_title; run.final_content = sc.final_content; run.geo_content = sc.final_content
        _record_io(db, s_geo, engine,
                   expected_fields=["title", "content", "mdx_filename?"],
                   extracted_result=f"终稿《{(sc.final_title or '')[:30]}》{len(sc.final_content)} 字"
                                    + (f"｜MDX文件:{run.mdx_filename}" if run.mdx_filename else ""),
                   next_action="进入步骤⑥：主编评审 + 平台过审 + GEO 评分")
        _step_done(db, run, s_geo, True, result={"title": sc.final_title, "len": len(sc.final_content)},
                   line=f"终稿已产出：标题《{(sc.final_title or '')[:30]}…》正文 {len(sc.final_content)} 字")
        _run_log(db, run, "步骤⑤完成：写手·GEO 终稿已产出")

        # —— 步骤⑥：主编·评审 + 平台过审 / GEO 评分（本地硬闸门 + 主编自然语言评语）——
        _step_start(db, run, s_review, "主编评审 + 平台合规自检 + GEO 评分…")
        review = _run_review(sc.final_content, ctx, run, db, title=sc.final_title)
        sc.geo_score = int(review.get("geo_score") or 0)
        sc.issues = review.get("issues") or []
        run.review_result = json.dumps(review, ensure_ascii=False)
        run.geo_score = sc.geo_score
        _passed = bool(review.get("gate_pass"))
        # 主编自然语言评审（面向人，解释为什么没过 / 主要差距），与本地硬闸门互补
        editor_review = ""
        try:
            editor_review = engine.editor_review(sc.final_content, sc.issues, sc.to_ctx())
        except Exception:
            editor_review = ""
        run.editor_review = editor_review or ""
        _record_io(db, s_review, engine,
                   expected_fields=["compliance_pass", "geo_score", "gate_pass", "editor_review"],
                   extracted_result=f"平台过审={'通过' if review.get('compliance_pass') else '未通过'}，"
                                    f"GEO评分={review.get('geo_score')}（{'达标' if _passed else '未达标'}）",
                   next_action="进入步骤⑦：闭环整改（若未达标，主编指令→写手改写，最多 3 轮）")
        _step_done(db, run, s_review, True,
                   result={"compliance_pass": review.get("compliance_pass"),
                           "geo_score": review.get("geo_score"), "gate_pass": _passed},
                   line=f"评审完成：平台过审={'通过' if review.get('compliance_pass') else '未通过'}，"
                        f"GEO评分={review.get('geo_score')}（{'达标' if _passed else '未达标'}）")
        _run_log(db, run, "步骤⑥完成：主编评审 + 平台过审 + GEO 评分")

        # —— 步骤⑦：闭环整改（主编指令 → 写手改写，每轮双角色全程可见），最多 N 轮 ——
        # 轮数由编排规格决定（批量生产时常用 1 轮换取 token 成本）。
        # 续跑时保留上一轮的整改记录，否则「重跑一次就丢掉历史轮次」会让复盘无从下手。
        MAX_ROUNDS = int(spec.get("max_revise_rounds", 3))
        rounds = list(artifacts["rounds"]) if "revise" in replay else []
        r = 0
        while (not _passed) and r < MAX_ROUNDS:
            issues = sc.issues
            _run_log(db, run, f"步骤⑦：未达标，启动第 {r + 1} 轮整改，问题 {len(issues)} 项：{'; '.join(issues[:4])}")
            # 主编：基于问题给出逐条整改指令（为什么改、改什么）
            try:
                directives = engine.direct_revision(sc.final_content, issues, round_no=r + 1)
            except Exception as e:  # noqa: BLE001
                _run_log(db, run, f"主编·整改指令异常（跳过本轮）：{e}"); directives = ""
            if not directives.strip():
                break
            _run_log(db, run, f"  主编·整改指令（第 {r + 1} 轮）：{directives[:120]}…")
            # 写手：按主编指令改写
            try:
                nt, revised = engine.apply_revision(sc.final_content, directives, round_no=r + 1)
            except Exception as e:  # noqa: BLE001
                _run_log(db, run, f"写手·改写异常（跳过本轮）：{e}"); revised = None
            if not revised or not revised.strip() or revised.strip() == sc.final_content.strip():
                break
            if nt:
                sc.final_title = scrub_contact_info(strip_markdown(nt))
            sc.final_content = scrub_contact_info(revised)
            r += 1
            review = _run_review(sc.final_content, ctx, run, db, title=sc.final_title)
            sc.geo_score = int(review.get("geo_score") or 0)
            sc.issues = review.get("issues") or []
            run.review_result = json.dumps(review, ensure_ascii=False)
            run.geo_score = sc.geo_score
            # 本轮主编二次评语（可见化：这轮改完后主编怎么看）
            round_review = ""
            try:
                round_review = engine.editor_review(sc.final_content, sc.issues, sc.to_ctx())
            except Exception:
                round_review = ""
            rounds.append({
                "round": r,
                "planner_directives": directives,
                "editor_review": round_review,
                "before": sc.final_content if r == 1 else rounds[-1].get("after", ""),
                "after": sc.final_content,
                "before_len": len(sc.final_content) if r == 1 else len(rounds[-1].get("after", "")),
                "after_len": len(sc.final_content),
                "issues": issues,
                "geo_score": review.get("geo_score"),
                "gate_pass": review.get("gate_pass"),
            })
            _record_io(db, s_revise, engine,
                       expected_fields=["planner_directives", "after", "geo_score", "gate_pass"],
                       extracted_result=f"第 {r} 轮：主编指令→写手改写完成，GEO评分={review.get('geo_score')}"
                                        f"（{'已达标' if review.get('gate_pass') else '仍待优化'}）",
                       next_action="进入下一轮整改或结束（达标即停止）")
            _passed = bool(review.get("gate_pass"))
            _run_log(db, run, f"  写手·改写完成（第 {r} 轮）：GEO评分={review.get('geo_score')}，"
                              f"{'已达标' if _passed else '仍待优化'}")
        run.final_title = sc.final_title
        run.final_content = sc.final_content
        run.revise_rounds = json.dumps(rounds, ensure_ascii=False)
        _step_done(db, run, s_revise, True,
                   result={"rounds": len(rounds), "final_gate_pass": _passed, "geo_score": run.geo_score},
                   line=f"整改 {len(rounds)} 轮（主编指令→写手改写），最终 GEO 评分={run.geo_score}"
                        f"（{'达标' if _passed else '仍待优化'}）")
        _run_log(db, run, f"步骤⑦完成：闭环整改 {len(rounds)} 轮")
        engine.close()

        # —— 步骤⑧：人工满意确认闸门（暂停，等待界面 confirm 端点）——
        _step_done(db, run, s_confirm, True,
                   result={"gate_pass": _passed, "geo_score": run.geo_score, "need_confirm": True},
                   line="终稿就绪，等待你在界面点「满意，加入内容中心」")
        # 确认步是人工闸门（无 API 调用），明确标注下一步动作，保证透明面板完整
        s_confirm.api_role = "human"
        s_confirm.api_model = "人工审核"
        s_confirm.expected_fields = json.dumps(["人工确认", "是否加入内容中心"], ensure_ascii=False)
        s_confirm.extracted_result = "终稿已就绪，等待人工满意确认"
        s_confirm.next_action = "在界面点「满意，加入内容中心」存档；或点「发布」触发步骤⑩（发布到平台）"
        s_confirm.response_latency_ms = 0
        db.commit()
        if "confirm" in replay:
            # 已确认过的运行不能被降级回「待确认」：续跑只应推进状态，不应回退终态
            _run_log(db, run, "步骤⑧此前已确认过：保持终态，不重复等待人工确认")
            return
        run.status = "await_confirm"
        db.commit()
        _run_log(db, run, "步骤⑧待确认：终稿已就绪，等待人工满意确认")
        return

        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        try:
            run = get_auto_run(db, run_id)
            if run:
                run.status = "failed"
                run.error = str(e)
                _run_log(db, run, f"流水线异常终止：{e}")
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def start_run(run_id: int) -> None:
    """启动一次运行（后台线程）。"""
    t = threading.Thread(target=orchestrate_run, args=(run_id,), daemon=True)
    t.start()


def retry_run(run_id: int, from_step: Optional[str] = None) -> None:
    """重试：**从断点续跑**，而不是从步骤①重烧一遍。

    历史实现把所有步骤重置为 pending，于是一次「第⑦步失败」的重试会连带重跑
    ①b/②/③/④/⑤/⑥ —— 6~10 次 LLM 调用，白烧的钱是实打实的。
    现在只重置第一个需要真正重新生成的步骤及其之后，之前的产物原样复用。

    ``from_step`` 是逃生口：产物虽然写过了但结果不满意时，用它强制从某一步重做。
    """
    db = SessionLocal()
    try:
        run = get_auto_run(db, run_id)
        if not run:
            return
        plan = pipeline_svc.plan(db, run, from_step=from_step)
        start_at = from_step or plan["next_key"]
        if start_at:
            outcome = pipeline_svc.reset_from(db, run, start_at)
            _run_log(db, run, "重试：从「%s」续跑（复用 %s；重置 %s）"
                              % (start_at,
                                 "、".join(outcome["kept"]) or "无",
                                 "、".join(outcome["cleared"]) or "无"))
        else:
            # 所有步骤产物都还在：无需重跑，直接重新走一遍（会全程复用）
            _run_log(db, run, "重试：所有步骤产物均可用，本次将全程复用已有结果")
        run.status = "created"
        run.error = ""
        db.commit()
    finally:
        db.close()
    start_run(run_id)


def retry_publish(run_id: int) -> dict:
    """仅重试第 5 步（搜狐号发布）：复用已有发布任务重新执行。"""
    db = SessionLocal()
    try:
        run = get_auto_run(db, run_id)
        if not run or not run.sohu_job_id:
            return {"ok": False, "error": "无搜狐号发布任务可重试"}
        job = db.query(PublishJob).filter(PublishJob.id == run.sohu_job_id).first()
        if not job:
            return {"ok": False, "error": "发布任务不存在"}
        if job.status != "approved":
            job.status = "approved"
            db.commit()
        s_pub = db.query(BrowserStudioStep).filter(
            BrowserStudioStep.run_id == run_id, BrowserStudioStep.step_key == "publish"
        ).first()
        if s_pub:
            _step_start(db, run, s_pub, "重试搜狐号发布…")
        res = _run_publish(db, job)
        ok_pub = bool(res and res.get("ok"))
        if s_pub:
            _step_done(db, run, s_pub, ok_pub,
                       error="" if ok_pub else (res or {}).get("error", "发布失败"),
                       result={"job_id": job.id, "status": job.status, "url": job.result_url})
            s_pub.api_role = "publish"
            s_pub.api_model = "平台发布接口(cookie)"
            s_pub.expected_fields = json.dumps(["job_id", "status", "url"], ensure_ascii=False)
            s_pub.extracted_result = (f"发布成功，文章URL：{(res or {}).get('url', '')}") if ok_pub \
                else f"发布失败：{(res or {}).get('error', '')}"
            s_pub.next_action = "发布完成，可在发布中心查看任务状态与文章链接"
            db.commit()
        run.status = "succeeded" if ok_pub else "partial"
        db.commit()
        return {"ok": ok_pub, "status": job.status, "url": job.result_url,
                "error": (res or {}).get("error", "")}
    finally:
        db.close()


def confirm_run(run_id: int) -> dict:
    """步骤⑧：用户满意 → 把终稿加入内容中心（ContentAsset）。返回 {ok, asset_id}。

    仅当终稿已产出才允许确认；已在浏览器工作室过审，故 review_status=approved。
    确认后若勾选 auto_publish 则直接进入步骤⑨发布，否则停在 confirmed 等你点发布。
    """
    db = SessionLocal()
    try:
        run = get_auto_run(db, run_id)
        if not run:
            return {"ok": False, "error": "运行记录不存在"}
        if not run.final_content:
            return {"ok": False, "error": "终稿为空，无法加入内容中心"}
        if run.confirmed:
            return {"ok": True, "asset_id": run.content_asset_id, "msg": "已确认过"}
        asset = ContentAsset(
            industry_id=run.industry_id,
            title=run.final_title or "（未命名）",
            content=scrub_contact_info(run.final_content),
            platform_id=0,
            account_id=run.account_id,
            review_status="approved",
            publish_status="pending",
            tags="浏览器工作室",
        )
        db.add(asset)
        db.commit()
        run.content_asset_id = asset.id
        run.confirmed = 1
        s_confirm = db.query(BrowserStudioStep).filter(
            BrowserStudioStep.run_id == run_id, BrowserStudioStep.step_key == "confirm"
        ).first()
        if s_confirm:
            _step_done(db, run, s_confirm, True,
                       result={"content_asset_id": asset.id},
                       line=f"已加入内容中心（asset_id={asset.id}）")
        _run_log(db, run, f"步骤⑧完成：已加入内容中心（asset_id={asset.id}）")
        if run.auto_publish:
            return _run_publish_stage(db, run)
        run.status = "confirmed"
        db.commit()
        return {"ok": True, "asset_id": asset.id}
    finally:
        db.close()


def publish_run(run_id: int) -> dict:
    """步骤⑨：发布到目标平台（创建 PublishJob + 审核闸门）。"""
    db = SessionLocal()
    try:
        run = get_auto_run(db, run_id)
        if not run:
            return {"ok": False, "error": "运行记录不存在"}
        if not run.final_content:
            return {"ok": False, "error": "终稿为空，无法发布"}
        return _run_publish_stage(db, run)
    finally:
        db.close()


def _run_publish_stage(db: Session, run: BrowserStudioRun) -> dict:
    """创建发布任务并执行（复用 publisher + 人工审核闸门）。供 confirm_run / publish_run 共用。"""
    s_pub = db.query(BrowserStudioStep).filter(
        BrowserStudioStep.run_id == run.id, BrowserStudioStep.step_key == "publish"
    ).first()
    if s_pub:
        _step_start(db, run, s_pub, "创建发布任务（审核闸门）…")
    # 官网 MDX 模式：产出的是可复制 MDX 代码，无需发布到第三方平台，
    # 标记「已就绪」，由用户手动粘贴到 Astro 站点。
    if resolve_run_output_format(run, db) == "mdx":
        if s_pub:
            _step_done(db, run, s_pub, True,
                       result={"mode": "official_mdx", "ready": True},
                       line="官网 MDX 已产出，请复制 MDX 代码块粘贴到官网（src/content 或对应内容集合），图片存入 src/assets/news/industry/xingwen/。")
        run.status = "succeeded"
        db.commit()
        return {"ok": True, "mode": "official_mdx", "status": "succeeded"}
    adapter_type = "mock" if run.mock_doubao else "playwright"
    job = PublishJob(
        industry_id=run.industry_id,
        task_id=0,
        title=run.final_title,
        content=scrub_contact_info(run.final_content),
        platform=run.platform or "sohu",
        adapter_type=adapter_type,
        status="pending_review",
    )
    db.add(job)
    db.commit()
    run.sohu_job_id = job.id
    _run_log(db, run, "步骤⑨：已创建发布任务 job_id=%d" % job.id)

    # 合规拦截：review_result 仍含违禁词/引流词 → 拦截自动发布，转人工
    review = {}
    try:
        review = json.loads(run.review_result) if run.review_result else {}
    except Exception:
        review = {}
    comp = review.get("compliance") or {}
    banned = comp.get("banned_count", 0) if isinstance(comp, dict) else 0
    guide = comp.get("contact_guide_count", 0) if isinstance(comp, dict) else 0
    if run.auto_publish and (banned > 0 or guide > 0):
        job.status = "pending_review"
        db.commit()
        if s_pub:
            _step_done(db, run, s_pub, True,
                       result={"job_id": job.id, "status": "pending_review", "intercepted": True},
                       line=f"⚠️ 仍含 {banned} 违禁词 / {guide} 引流词，已拦截自动发布转人工审核")
        run.status = "partial"
        return {"ok": False, "intercepted": True, "error": "合规未通过，已拦截", "job_id": job.id}
    if run.auto_publish:
        job.status = "approved"
        db.commit()
        res = _run_publish(db, job)
        ok_pub = bool(res and res.get("ok"))
        if s_pub:
            _step_done(db, run, s_pub, ok_pub,
                       error="" if ok_pub else (res or {}).get("error", "发布失败"),
                       result={"job_id": job.id, "status": job.status, "url": job.result_url},
                       line=("已自动发布：" + (job.result_url or "")) if ok_pub else "自动发布失败")
        run.status = "succeeded" if ok_pub else "partial"
    else:
        if s_pub:
            _step_done(db, run, s_pub, True,
                       result={"job_id": job.id, "status": "pending_review"},
                       line="发布任务已创建，待人工审核批准")
        run.status = "confirmed" if run.confirmed else "await_confirm"
    db.commit()
    return {"ok": True, "job_id": job.id, "status": job.status}
