"""
SQLAlchemy 数据模型
所有业务表携带 industry_id 实现行业级数据隔离
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, Index
)
from .database import Base, now


# ============================================================
#  系统表
# ============================================================
class SysUser(Base):
    """系统用户"""
    __tablename__ = "sys_user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password = Column(String(128), nullable=False)
    role = Column(String(32), default="admin")
    industry_perms = Column(Text, default="all")
    status = Column(Integer, default=1)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)


class OperationLog(Base):
    """操作日志"""
    __tablename__ = "operation_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=0)
    module = Column(String(64), default="")
    action = Column(String(64), default="")
    detail = Column(Text, default="")
    ip = Column(String(64), default="")
    create_time = Column(DateTime, default=now)


# ============================================================
#  行业空间（最高隔离单元）
# ============================================================
class Industry(Base):
    """行业表 - 最高隔离单元"""
    __tablename__ = "industry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    description = Column(Text, default="")
    status = Column(Integer, default=1)
    config = Column(Text, default="{}")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  平台 / 账号 / 人设
# ============================================================
class Platform(Base):
    """平台表"""
    __tablename__ = "platform"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    word_count_min = Column(Integer, default=800)
    word_count_max = Column(Integer, default=1500)
    compliance_level = Column(Integer, default=2)
    config = Column(Text, default="{}")
    # GEO 作战增强：平台特性与平台规则（选平台步骤展示，弱化"仅合规等级"）
    characteristics = Column(Text, default="")   # 平台特性：受众/内容形态/分发机制等
    rules = Column(Text, default="")             # 平台规则：合规约束/营销限制/禁区
    # 三模式：geo=强品牌/GEO 模式（自建站/AI 抓取，品牌突出）；platform=平台合规模式（搜狐等内容平台，中性无品牌）；green=绿色吸粉模式
    publish_mode = Column(String(16), default="geo")
    # 产出形态：markdown=常规文章；mdx=官网/Astro 站，按 MDX 模板产出可复制代码
    output_format = Column(String(16), default="markdown")
    site_url = Column(Text, default="")          # 官网/自建站地址（官网模式用）
    publish_prompt = Column(Text, default="")    # 平台自动化发布提示词（官网 MDX 模板等有序存放）
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


class Persona(Base):
    """人设表"""
    __tablename__ = "persona"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    identity = Column(Text, default="")
    tone_style = Column(Text, default="")
    contact_rule = Column(Text, default="")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


class Account(Base):
    """账号表"""
    __tablename__ = "account"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    platform_id = Column(Integer, ForeignKey("platform.id"), default=0)
    persona_id = Column(Integer, ForeignKey("persona.id"), default=0)
    account_name = Column(Text, nullable=False)
    content_track = Column(Text, default="")
    status = Column(Integer, default=1)
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  品牌资产库
# ============================================================
class BrandAsset(Base):
    """品牌资产表"""
    __tablename__ = "brand_asset"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    brand_name = Column(Text, nullable=False)
    official_website = Column(Text, default="")
    contact_phone = Column(Text, default="")
    contact_wechat = Column(Text, default="")
    contact_email = Column(Text, default="")
    slogan = Column(Text, default="")
    core_products = Column(Text, default="")
    unique_selling_points = Column(Text, default="")
    target_keywords = Column(Text, default="")
    brand_story = Column(Text, default="")
    is_default = Column(Integer, default=0)
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  知识库
# ============================================================
class KnowledgeCategory(Base):
    """知识库分类"""
    __tablename__ = "knowledge_category"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    icon = Column(String(64), default="Folder")  # 图标名称
    color = Column(String(32), default="#6366f1")  # 分类主题色
    description = Column(Text, default="")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class KnowledgeItem(Base):
    """知识库条目"""
    __tablename__ = "knowledge_item"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("knowledge_category.id"), default=None)
    title = Column(Text, nullable=False)
    summary = Column(Text, default="")  # 简短摘要（一句话概括）
    content = Column(Text, default="")
    tags = Column(Text, default="")
    source = Column(String(255), default="")  # 知识来源
    importance = Column(String(32), default="normal")  # high/normal/low
    status = Column(String(32), default="published")  # draft/published
    view_count = Column(Integer, default=0)  # 查看次数
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  关键词 / 选题
# ============================================================
class KeywordGroup(Base):
    """关键词分组表"""
    __tablename__ = "keyword_group"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    color = Column(String(32), default="#6366f1")  # 分组主题色
    icon = Column(String(64), default="Collection")  # 图标名称
    description = Column(Text, default="")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class Keyword(Base):
    """关键词表"""
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("keyword_group.id"), default=None)  # 所属分组
    word = Column(Text, nullable=False)
    type = Column(String(32), default="long_tail")  # brand/product/long_tail/question
    priority = Column(Integer, default=2)
    related_product = Column(Text, default="")
    tags = Column(Text, default="")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


class Topic(Base):
    """选题表"""
    __tablename__ = "topic"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    platform_id = Column(Integer, default=0)
    account_id = Column(Integer, default=0)
    keyword_id_list = Column(Text, default="")
    title = Column(Text, nullable=False)
    description = Column(Text, default="")
    plan_date = Column(Date, nullable=True)
    status = Column(String(32), default="pending")  # pending/done
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  提示词库（4 分类）
# ============================================================
class PromptLibraryItem(Base):
    """AI 提示词库条目"""
    __tablename__ = "prompt_library_item"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    category = Column(String(32), nullable=False)  # outline/draft/rewrite/safety/illustration
    content = Column(Text, default="")
    variables = Column(Text, default="[]")  # 自动检测到的变量（JSON）
    variable_schema = Column(Text, default="[]")  # 自定义变量定义（JSON：name/desc/default_value/required）
    description = Column(Text, default="")
    tags = Column(Text, default="")  # 标签（逗号分隔）
    is_default = Column(Integer, default=0)
    usage_count = Column(Integer, default=0)  # 使用次数
    last_used_time = Column(DateTime, nullable=True)  # 最后使用时间
    rating = Column(Integer, default=0)  # 评分 0-5
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  三大规则库
# ============================================================
class RuleLibrary(Base):
    """规则库表"""
    __tablename__ = "rule_library"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    rule_type = Column(String(32), nullable=False)  # ai_seo/anti_ai/compliance
    content = Column(Text, nullable=False)
    platform_ids = Column(Text, default="all")
    status = Column(Integer, default=1)
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  软文生产（7 步流程）
# ============================================================
class ProductionTask(Base):
    """生产任务表"""
    __tablename__ = "production_task"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    title = Column(Text, default="")
    status = Column(String(32), default="draft")  # draft/processing/done/archived
    current_step = Column(Integer, default=1)

    industry_snapshot = Column(Text, default="")
    platform_id = Column(Integer, default=0)
    platform_snapshot = Column(Text, default="")
    account_id = Column(Integer, default=0)
    account_snapshot = Column(Text, default="")
    persona_id = Column(Integer, default=0)
    persona_snapshot = Column(Text, default="")

    # GEO 作战：目标客户画像与意图问题（生成"带信号的 GEO 软文"的锚点）
    target_persona_id = Column(Integer, default=0)   # 关联 GEO 目标画像 TargetPersona（0=未选）
    target_persona_snapshot = Column(Text, default="")
    intent_question_id = Column(Integer, default=0)  # 关联意图问题 IntentQuestion（0=未选）
    intent_question_snapshot = Column(Text, default="")
    geo_score = Column(Integer, default=0)           # 最近一次 GEO 评分（0-100，本地启发式）
    target_needs = Column(Text, default="")           # 第4步「目标客户需求」结构化需求（期望推荐角度/必含品牌信号/必须回应的痛点）JSON 字符串

    keyword_ids = Column(Text, default="")
    knowledge_item_ids = Column(Text, default="")
    rule_ids = Column(Text, default="")  # 选定的规则库规则 id（逗号分隔），用于注入提示词引导 AI 写作
    outline_prompt_id = Column(Integer, default=0)
    outline_content = Column(Text, default="")
    draft_prompt_id = Column(Integer, default=0)
    draft_content = Column(Text, default="")
    rewrite_prompt_id = Column(Integer, default=0)
    rewrite_content = Column(Text, default="")
    safety_prompt_id = Column(Integer, default=0)
    safety_report = Column(Text, default="")
    final_content = Column(Text, default="")
    final_title = Column(Text, default="")   # 第9步「安全发布 & GEO 筛选」产出的最终标题（与 final_content 配对，可直接复制发布到平台）
    publish_url = Column(Text, default="")
    illustration_plan = Column(Text, default="")  # 第8步配图方案（JSON 数组字符串）

    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    plan_date = Column(String(32), default="")  # 内容运营日历：计划发布日期 YYYY-MM-DD
    published_status = Column(String(32), default="")   # 末次发布状态（来自 publish_job：空/published/failed/...）
    last_publish_job_id = Column(Integer, default=0)    # 关联最近一次 publish_job.id
    is_deleted = Column(Integer, default=0)

    # —— P2 并表字段：让浏览器工作室（自动流）直接复用 production_task 统一任务表 ——
    # 与 BrowserStudioRun 同名列对齐（name/platform/log/error 等，不与现有 title/platform_id 冲突），
    # 因此自动流引擎只需把 BrowserStudioRun 替换为 ProductionTask（纯类型替换），逻辑零改动。
    name = Column(Text, default="")                      # 运行名称（与手动流的 title 并存）
    subject = Column(Text, default="")                   # 目标需求（自动流：引导选题方向）
    platform = Column(String(32), default="sohu")        # 发布平台 code（与手动流的 platform_id 并存）
    publish_mode = Column(String(16), default="geo")     # geo / platform / green
    output_format = Column(String(16), default="markdown")  # markdown / mdx
    brand_asset_id = Column(Integer, default=0)
    target_persona_ids = Column(Text, default="")        # 多选目标客户画像 id 列表（逗号）
    intent_question_ids = Column(Text, default="")       # 多选意图问题 id 列表（逗号）
    doubao_credential_id = Column(Integer, default=0)    # 豆包 cookie 凭证
    sohu_credential_id = Column(Integer, default=0)      # 搜狐号 cookie 凭证
    ai_engine = Column(String(32), default="deepseek")   # 创作引擎：deepseek / doubao / mock
    llm_config_id = Column(Integer, default=0)
    mock_doubao = Column(Integer, default=0)
    compliance_result = Column(Text, default="")         # 平台合规自检结果（run_full_check JSON）
    auto_publish = Column(Integer, default=0)            # 1=确认后自动批准并发布
    geo_content = Column(Text, default="")               # GEO 强化稿（AI 返回原文）
    review_result = Column(Text, default="")             # 评审结果（JSON：compliance/geo/mind/diagnosis）
    revise_rounds = Column(Text, default="")             # 整改轮记录（JSON 数组）
    clarified_brief = Column(Text, default="")           # 主编·明晰创作简报
    editor_review = Column(Text, default="")             # 主编·自然语言评审评语
    confirmed = Column(Integer, default=0)               # 人工满意确认闸门
    mdx_filename = Column(Text, default="")              # 官网 MDX 产出文件名
    mdx_images = Column(Text, default="")                # 官网 MDX 建议配图文件名列表（JSON 数组）
    content_asset_id = Column(Integer, default=0)        # 存档目标 ContentAsset.id
    sohu_job_id = Column(Integer, default=0)             # 搜狐号发布任务 PublishJob.id
    error = Column(Text, default="")                     # 末次失败原因（整体）
    log = Column(Text, default="")                       # 运行级累计日志
    # —— 并表簿记字段 ——
    mode = Column(String(16), default="manual")          # manual（手动流）/ auto（浏览器工作室自动流）
    legacy_run_id = Column(Integer, default=0)           # 原 browser_studio_run.id；手动流=0
    legacy_status = Column(String(32), default="")       # 原 browser_studio_run.status（审计保留）


# ============================================================
#  内容版本历史（每次保存内容变化时自动记录）
# ============================================================
class ContentVersion(Base):
    """生产任务内容版本历史"""
    __tablename__ = "content_version"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("production_task.id"), nullable=False, index=True)
    step = Column(String(32), default="outline")  # outline/draft/rewrite/safety/final
    content = Column(Text, default="")
    config_snapshot = Column(Text, default="")  # JSON：当时的 rule_ids/knowledge_item_ids/keyword_ids/prompt_id
    version_no = Column(Integer, default=1)
    create_time = Column(DateTime, default=now)


# ============================================================
#  内容审核 / 资产
# ============================================================
class ContentAsset(Base):
    """内容资产表"""
    __tablename__ = "content_asset"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    topic_id = Column(Integer, default=0)
    platform_id = Column(Integer, default=0)
    account_id = Column(Integer, default=0)
    title = Column(Text, default="")
    content = Column(Text, default="")
    tags = Column(Text, default="")
    review_status = Column(String(32), default="pending")  # pending/pass/reject
    review_detail = Column(Text, default="")
    reject_reason = Column(Text, default="")
    publish_status = Column(String(32), default="pending")  # pending/published/offline
    publish_url = Column(Text, default="")
    publish_time = Column(DateTime, nullable=True)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  效果统计
# ============================================================
# ============================================================
#  LLM 供应商配置（行业级隔离，可多套并存，is_default 标记当前激活）
#  说明：api_key 以明文存储于本地 SQLite（单机本地工具）。如需更高安全级别，
#  后续可在此扩展字段级加密；当前按"本地私有部署"假设权衡，避免过度工程。
# ============================================================
class LlmConfig(Base):
    """LLM 供应商配置（DeepSeek / OpenAI 兼容协议均可）"""
    __tablename__ = "llm_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(String(64), default="默认")
    provider = Column(String(32), default="deepseek")  # deepseek/openai/qwen/moonshot
    api_key = Column(Text, default="")                  # 供应商密钥（明文存储，本地私有部署）
    base_url = Column(Text, default="")                 # 自定义网关/代理；留空用供应商默认地址
    model = Column(String(64), default="deepseek-v4-pro")
    temperature = Column(String(16), default="0.7")     # 存字符串，避免浮点 ALTER 迁移麻烦
    max_tokens = Column(Integer, default=4000)
    timeout = Column(Integer, default=60)
    is_default = Column(Integer, default=0)             # 同行业仅一个为 1
    status = Column(Integer, default=1)                 # 1 启用 / 0 停用
    # 角色路由：一篇文章的自动化创作按任务类型分流到不同 API 配置，
    # 实现「选题调研 / 正文撰写 / 审核优化」三路并行、负载均衡与故障切换。
    # 取值：research(选题调研/大纲) / writing(正文撰写/精修/GEO) / review(审核优化/整改) / general(兜底通用)
    role = Column(String(16), default="general", index=True)
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  平台发布凭证（cookie / 账号密码，明文存储，本地私有部署假设）
#  说明：与 llm_config 同策略——本地单机工具，明文存储避免过度工程；
#  若部署到多用户/公网环境，应在此扩展字段级加密（Fernet/AES）。
#  安全边界：cookie 由用户在本机手动登录后导出上传，系统绝不自动破解 2FA。
# ============================================================
class PlatformCredential(Base):
    """各平台自动发布凭证（知乎/搜狐/网易 等用 Playwright 的 cookie 登录态）"""
    __tablename__ = "platform_credential"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    platform = Column(String(32), default="")          # zhihu / sohu / wangyi / wechat / xiaohongshu ...
    cred_type = Column(String(16), default="cookie")   # cookie | password
    cred_json = Column(Text, default="")               # cookie JSON 数组 或 {"username":..., "password":...}
    status = Column(Integer, default=1)                # 1 正常 / 0 停用
    needs_relogin = Column(Integer, default=0)         # 1 = 登录态失效，需人工续期
    note = Column(Text, default="")
    last_error = Column(Text, default="")
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  发布任务（自动发布流水线 + 人工审核闸门）
#  状态机：draft → pending_review → approved → publishing → published
#                                  ↘ rejected（打回修改）
#                            publishing → failed（可重试）
#  设计：适配器类型 adapter_type = playwright（无 API 平台兜底）/ mock（测试用）
#  官方 Open API 适配器（微信/小红书/百家号/头条）因当前无资质暂缓，抽象层已预留。
# ============================================================
class PublishJob(Base):
    """自动发布任务：一条生产任务 → 一个目标平台 → 一次发布尝试"""
    __tablename__ = "publish_job"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    task_id = Column(Integer, default=0)               # 关联 production_task.id
    title = Column(Text, default="")                   # 待发布标题
    content = Column(Text, default="")                 # 待发布正文（纯文本/HTML）
    cover = Column(Text, default="")                   # 封面图（base64 或 URL，可选）
    platform = Column(String(32), default="")          # zhihu / sohu / wangyi
    adapter_type = Column(String(16), default="playwright")  # playwright | mock
    status = Column(String(32), default="draft")       # draft/pending_review/approved/publishing/published/rejected/failed
    reject_reason = Column(Text, default="")
    scheduled_at = Column(String(32), default="")      # 计划发布时间 YYYY-MM-DD HH:MM:SS（错峰）
    result_url = Column(Text, default="")              # 发布成功后的文章 URL
    error = Column(Text, default="")                   # 失败原因
    tokens = Column(Integer, default=0)                # 预留：发布相关 token 消耗
    log = Column(Text, default="")                     # 执行日志（步骤/截图路径/耗时）
    finished_at = Column(DateTime, nullable=True)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class EffectRecord(Base):
    """效果记录表"""
    __tablename__ = "effect_record"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    keyword_id = Column(Integer, default=0)
    model_type = Column(String(64), default="")
    has_brand = Column(Integer, default=0)
    has_website = Column(Integer, default=0)
    has_contact = Column(Integer, default=0)
    rank = Column(Integer, default=0)
    record_date = Column(Date, nullable=True)
    remark = Column(Text, default="")
    is_deleted = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)




# ============================================================
#  GEO 作战：目标画像与意图问题库（模块①基础）
#  - TargetPersona：目标客户画像（工厂老板 / 技术人员 / 采购…）
#  - IntentQuestion：目标客户会问 AI 的问题 + 期望推荐角度
#  注意：Persona 模型已被「写作人设」占用，目标客户画像必须用 TargetPersona 避免冲突
# ============================================================
class TargetPersona(Base):
    """GEO 目标客户画像（与写作人设 Persona 区分）"""
    __tablename__ = "target_persona"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    role_type = Column(String(32), default="other")  # decision_maker/technical/procurement/other
    description = Column(Text, default="")
    pain_points = Column(Text, default="")      # 痛点（换行分隔）
    cares_about = Column(Text, default="")      # 关注点 / 决策考量（换行分隔）
    decision_weight = Column(Integer, default=2)  # 决策影响力 1-3
    icon = Column(String(64), default="User")   # 图标名称
    color = Column(String(32), default="#6366f1")
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class IntentQuestion(Base):
    """目标客户会向 AI 提出的意图问题 + 期望推荐角度"""
    __tablename__ = "intent_question"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    persona_id = Column(Integer, default=0)  # 关联目标画像（0=未关联，不用外键约束以便软删除后降级）
    question = Column(Text, nullable=False)            # 客户会问 AI 的原话问题
    intent_category = Column(String(32), default="other")  # 意图分类：selection/cost/integration/risk/compliance/other
    expected_recommendation = Column(Text, default="")  # 期望 AI 如何推荐我们（推荐角度/话术要点）
    priority = Column(Integer, default=2)             # 1-3（3最高）
    coverage_status = Column(String(32), default="gap")  # covered(已覆盖)/gap(待覆盖)
    source = Column(String(32), default="manual")     # 来源：manual/interview/support/search/competitor
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  GEO 作战：AI 推荐监测（模块⑥——闭环"AI 是否真的推荐我们"）
#  - GeoMonitor：一次监测任务（目标问题 + 品牌 + 要测的 AI 平台）
#  - GeoMonitorReply：每个 AI 平台的答复 + 解析出的 3 指标（提及/引用长度/情感）
# ============================================================
class GeoMonitor(Base):
    """GEO 监测任务：对标各 AI 平台，确认 AI 认可度（品牌提及率/引用长度/情感倾向）"""
    __tablename__ = "geo_monitor"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(String, default="")            # 监测任务名
    target_query = Column(Text, default="")      # 核心问题/关键词（直接喂给 AI 的提问）
    brand_name = Column(String, default="")      # 要监测是否被提及的品牌
    platforms = Column(Text, default="[]")       # JSON 数组：要测的 AI 平台名（豆包/文心一言/DeepSeek/元宝…）
    note = Column(Text, default="")              # 备注
    sort = Column(Integer, default=0)
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class GeoMonitorReply(Base):
    """某 AI 平台对某监测问题的答复 + 解析出的 AI 认可度 3 指标"""
    __tablename__ = "geo_monitor_reply"
    id = Column(Integer, primary_key=True, autoincrement=True)
    monitor_id = Column(Integer, ForeignKey("geo_monitor.id"), nullable=False, index=True)
    platform = Column(String, default="")        # AI 平台名
    ai_reply = Column(Text, default="")          # 用户粘贴的 AI 答复原文
    mentioned = Column(Integer, default=0)       # 是否提及品牌 0/1
    mention_count = Column(Integer, default=0)   # 提及次数
    citation_length = Column(Integer, default=0) # 提及品牌的相关字数（句子长度之和）
    sentiment = Column(String, default="")       # positive/neutral/negative
    valuable_positive = Column(Integer, default=0)  # 是否"有价值的正面"（带数据/案例）0/1
    recommended = Column(Integer, default=0)     # AI 是否明确"推荐"该品牌 0/1
    snippet = Column(Text, default="")           # 提及品牌的片段
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)


# ============================================================
#  7 大内容平台 + 官网/自建站 预设
#  publish_mode / output_format / site_url / publish_prompt 为新字段（三模式 + MDX 自动化）。
#  官网/自建站：output_format=mdx，按 OFFICIAL_MDX_PROMPT 产出可复制 MDX 代码。
# ============================================================
PLATFORM_PRESETS = [
    {
        "name": "搜狐号",
        "word_count_min": 800, "word_count_max": 1500,
        "compliance_level": 2,
        "config": '{"features":["门户权重","品牌曝光","允许软广"],"ai_weight":"中","marketing":"软广友好"}',
        "characteristics": "门户型内容平台，百度等搜索引擎权重高，适合做品牌背书与长尾收录；对软文营销容忍度较高，读者偏成熟行业人群。",
        "rules": "允许适度软广，但需避免硬广与夸大宣传；文末可自然带出品牌与联系方式；禁止违法违规、医疗敏感与虚假数据内容。",
    },
    {
        "name": "百家号",
        "word_count_min": 800, "word_count_max": 2000,
        "compliance_level": 3,
        "config": '{"features":["百度收录","AI收录高","审核严格"],"ai_weight":"高","marketing":"禁止硬广,需软植入"}',
        "characteristics": "百度生态核心分发渠道，AI 收录与搜索权重极高，专业内容易获得长尾流量，适合建立行业权威。",
        "rules": "审核严格，禁止硬广与诱导；品牌信息需以专业背书形式软植入；标题避免夸张与标题党；敏感行业需资质。",
    },
    {
        "name": "网易号",
        "word_count_min": 800, "word_count_max": 1800,
        "compliance_level": 2,
        "config": '{"features":["门户权重","品牌曝光","允许软广"],"ai_weight":"中","marketing":"软广友好"}',
        "characteristics": "门户资讯平台，品牌曝光能力强，读者偏成熟人群，适合行业观点、案例与干货类内容。",
        "rules": "允许软广，禁止虚假宣传与低俗内容；数据案例需可核查并标注来源；联系方式仅在文末自然出现。",
    },
    {
        "name": "今日头条号",
        "word_count_min": 500, "word_count_max": 2000,
        "compliance_level": 2,
        "config": '{"features":["推荐流量","标题党友好","短平快"],"ai_weight":"中","marketing":"软广为主"}',
        "characteristics": "算法推荐驱动，流量大且起量快，适合短平快、话题性强的内容；标题党友好但需合规。",
        "rules": "禁止标题党与题文不符；软广为主，禁止诱导加微信/外链；敏感行业需资质，医疗类严格受限。",
    },
    {
        "name": "知乎号",
        "word_count_min": 1000, "word_count_max": 3000,
        "compliance_level": 3,
        "config": '{"features":["专业问答","长尾流量","AI收录极高"],"ai_weight":"极高","marketing":"禁止硬广,需专业背书"}',
        "characteristics": "高知用户聚集，专业问答与长文权重高，AI 收录极高，适合建立技术权威与专业背书，长尾价值大。",
        "rules": "禁止硬广，需以专业回答/数据/案例建立可信度；可文末自然提及品牌；反对营销话术与自夸。",
    },
    {
        "name": "微信公众号",
        "word_count_min": 800, "word_count_max": 2500,
        "compliance_level": 2,
        "config": '{"features":["私域沉淀","品牌深度","搜一搜收录"],"ai_weight":"中高","marketing":"软广为主"}',
        "characteristics": "私域沉淀核心，品牌深度内容承载地，搜一搜可收录，适合系统化行业方法论与案例拆解。",
        "rules": "软广为主，禁止诱导分享与过度营销；可放官网与联系方式；注意原创与版权，避免抄袭。",
    },
    {
        "name": "小红书号",
        "word_count_min": 300, "word_count_max": 1000,
        "compliance_level": 3,
        "config": '{"features":["种草图文","年轻女性","短内容"],"ai_weight":"中","marketing":"禁止硬广,需场景化"}',
        "characteristics": "年轻女性为主的种草社区，图文短内容，场景化与真实体验优先，适合生活方式类软植入。",
        "rules": "禁止硬广与医疗违禁词；需场景化、口语化表达；品牌信息自然融入体验；避免夸大功效与绝对化用语。",
    },
    {
        "name": "官网/自建站",
        "word_count_min": 800, "word_count_max": 1500,
        "compliance_level": 1,
        "config": '{"features":["自有阵地","品牌完整表达","GEO友好"],"ai_weight":"高","marketing":"强品牌,完整表达"}',
        "characteristics": "品牌自有官网（基于 Astro 构建，https://www.example.com），栏目：案例·新闻 > 客户案例 / 产品应用 / 行业资讯。自有阵地可完整表达品牌、无营销限制，且对 AI 抓取与 GEO 极友好。",
        "rules": "自有阵地，品牌可完整表达；产出形态为 MDX 代码，按固定模板（Frontmatter + 六段结构 + 4 列数据对比表 + 引用块）生成，严禁 <Image /> 组件与 emoji，严肃工业风。",
        "publish_mode": "geo",
        "output_format": "mdx",
        "site_url": "https://www.example.com",
    },
]


# ============================================================
#  浏览器工作室（浏览器自动化：豆包创作 + 搜狐号发布）
#  一条 Run = 一次完整的「豆包 Web 对话创作 → 回传存档 → 搜狐号自动发布」流水线。
#  BrowserStudioStep = Run 内每一步的状态机，支持状态跟踪 / 失败重试 / 结果回溯。
#  设计要点：
#   - 豆包作为"创作引擎"经由浏览器自动化驱动（无官方 API 时的最稳路径），
#     搜狐号作为"发布引擎"复用既有 PlaywrightAdapter。
#   - 全量上下文（目标需求/品牌/平台/人设/知识库/关键词/规则库/客户画像/意图问题）
#     在创建 Run 时选定并以 id 列表快照，编排时实时从各表拉取最新正文组装 briefing。
#   - 每一步均有 status( pending/running/done/failed ) + attempts + last_error + result_json
#     （存发送给豆包的提示词、豆包原始回复、抽取出的终稿）+ log，确保可回溯。
# ============================================================
class BrowserStudioRun(Base):
    """浏览器工作室运行记录（一次完整创作+发布流水线）

    ⚠️ P2 并表遗留模型：新建运行已改写 production_task(mode='auto')。
    本表仅在「数据未迁移」阶段保留，用于读取/重试历史运行；
    执行 migrations/merge_browser_studio_run.py --apply 后会改名归档为
    _archive_browser_studio_run。代码侧统一通过 get_auto_run() 解析（先查
    production_task，再回退本表），不要在此模型上新增逻辑。
    """
    __tablename__ = "browser_studio_run"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True)
    name = Column(Text, default="")                   # 运行名称（自动生成或用户填写）
    status = Column(String(32), default="created")    # created/running/succeeded/partial/failed
    subject = Column(Text, default="")                # 目标需求（引导豆包选题方向）
    platform = Column(String(32), default="sohu")     # 发布平台 code（默认搜狐号）
    publish_mode = Column(String(16), default="geo")  # 发布模式：geo=强品牌/GEO；platform=平台合规；green=绿色吸粉（派生自平台，可手动覆盖）
    output_format = Column(String(16), default="markdown")  # 产出形态：markdown=常规文章；mdx=官网/Astro 站
    account_id = Column(Integer, default=0)           # 平台账号
    persona_id = Column(Integer, default=0)           # 写作人设
    brand_asset_id = Column(Integer, default=0)       # 品牌资产
    target_persona_id = Column(Integer, default=0)    # GEO 目标客户画像（兼容旧单值）
    intent_question_id = Column(Integer, default=0)   # 意图问题（兼容旧单值）
    target_persona_ids = Column(Text, default="")     # 目标客户画像 id 列表（逗号，支持多选）
    intent_question_ids = Column(Text, default="")    # 意图问题 id 列表（逗号，支持多选）
    keyword_ids = Column(Text, default="")            # 关键词 id 列表（逗号）
    knowledge_item_ids = Column(Text, default="")     # 知识库条目 id 列表（逗号）
    rule_ids = Column(Text, default="")               # 规则库 id 列表（逗号）
    doubao_credential_id = Column(Integer, default=0) # 豆包 cookie 凭证（PlatformCredential.id, platform='doubao'）
    sohu_credential_id = Column(Integer, default=0)   # 搜狐号 cookie 凭证（PlatformCredential.id, platform='sohu')
    ai_engine = Column(String(32), default="deepseek") # 创作引擎：deepseek(LLM API) / doubao(浏览器自动化) / mock(模拟演示)
    llm_config_id = Column(Integer, default=0)        # 指定 LLM 配置（DeepSeek 等）；0=按行业默认自动解析
    mock_doubao = Column(Integer, default=0)          # 1=用模拟豆包适配器（无需浏览器，端到端验证用）
    compliance_result = Column(Text, default="")      # 平台合规自检结果（run_full_check JSON：overall_pass/issues/各项分数）
    auto_publish = Column(Integer, default=0)         # 1=确认后自动批准并发布（绕过发布中心人工审核，需自担风险）
    # —— 9 步流水线的中间产物（每轮 AI 返回都落库，前端可逐段回看）——
    outline_content = Column(Text, default="")        # ② 选题大纲（AI 返回原文）
    draft_content = Column(Text, default="")          # ③ 初稿（AI 返回原文）
    rewrite_content = Column(Text, default="")        # ④ 去AI味精修稿（AI 返回原文）
    geo_content = Column(Text, default="")            # ⑤ GEO 强化稿（AI 返回原文）
    review_result = Column(Text, default="")          # ⑥ 平台过审 + GEO 评分结果（JSON：compliance/geo/mind/diagnosis）
    revise_rounds = Column(Text, default="")          # ⑦ 整改轮记录（JSON 数组：每轮 before/after/issues/评分，可逐轮回看）
    geo_score = Column(Integer, default=0)            # 最终 GEO 评分（0-100，取自 review_result）
    # —— 双智能体（主编规划/评审/整改指令 + 写手落地）专属产物 ——
    clarified_brief = Column(Text, default="")        # ①b 主编·明晰创作简报（选题角/目标读者/GEO信号重点/避坑点）
    editor_review = Column(Text, default="")          # ⑥ 主编·自然语言评审评语（面向人看，解释为什么改）
    confirmed = Column(Integer, default=0)            # ⑧ 人工满意确认闸门：1=已确认并加入内容中心
    final_title = Column(Text, default="")            # 终稿标题
    final_content = Column(Text, default="")          # 终稿正文（纯文本，可直接复制发布）
    mdx_filename = Column(Text, default="")             # 官网 MDX 产出文件名（如 dry-screw-pump-food-factory.mdx，可复制）
    mdx_images = Column(Text, default="")               # 官网 MDX 建议配图文件名列表（JSON 数组）
    content_asset_id = Column(Integer, default=0)     # 存档目标：ContentAsset.id（可回溯）
    sohu_job_id = Column(Integer, default=0)          # 搜狐号发布任务 PublishJob.id
    error = Column(Text, default="")                  # 末次失败原因（整体）
    log = Column(Text, default="")                    # 运行级累计日志（每步追加）
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


class BrowserStudioStep(Base):
    """浏览器工作室运行内的单步状态（5 步流水线）"""
    __tablename__ = "browser_studio_step"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # P2：取消硬外键。统一任务表后，run_id 指向 production_task.id（自动流 mode='auto'），
    # 历史 browser_studio_run 归档案的 run_id 不再有父表。保留索引便于按运行回看步骤。
    run_id = Column(Integer, nullable=False, index=True)
    step_no = Column(Integer, default=0)              # 1..10
    step_key = Column(String(32), default="")         # connect/clarify/outline/draft/depolish/geo/review/revise/confirm/publish
    agent = Column(String(16), default="")            # planner(主编) / writer(写手) / system / dual
    title = Column(Text, default="")                  # 步骤中文名（展示用）
    status = Column(String(32), default="pending")    # pending/running/done/failed/skipped
    attempts = Column(Integer, default=0)             # 重试次数
    last_error = Column(Text, default="")             # 该步末次失败原因
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    result_json = Column(Text, default="")            # 该步产物：发送豆包的提示词 / 豆包原始回复 / 抽取标题正文（可回溯）
    log = Column(Text, default="")                    # 该步步骤日志
    # —— 步骤透明化（让每一步「可复现、可复制、可审计」）——
    request_payload = Column(Text, default="")          # 发送给 API 的完整内容（可直接复制给网页 AI 复现）
    expected_fields = Column(Text, default="")          # 期待 API 返回的字段（JSON 列表，如 ["outline","title"]）
    response_latency_ms = Column(Integer, default=0)    # 实际响应耗时（毫秒）
    api_role = Column(String(16), default="")           # 本次调用的 API 角色（research/writing/review/general/mock）
    api_config_id = Column(Integer, default=0)          # 实际命中的 LlmConfig.id（故障切换后可能是备用）
    api_model = Column(String(64), default="")          # 实际命中的模型名（用于展示「哪个 API 处理的」）
    extracted_result = Column(Text, default="")         # 从响应中提取的关键结果（一句话摘要，给人看）
    next_action = Column(Text, default="")              # 下一步动作描述（给人看，明确「接下来做什么」）
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)


# ============================================================
#  自动化提示词（浏览器工作室「自动化指挥中心」可编辑底座）
#  - 每个流程 / 专家角色用到的提示词都落库，页面可编辑、可复制；
#  - DB 中的 content 覆盖 services/doubao_studio.py 里的默认常量，
#    使页面修改即时生效于后续运行（get_studio_prompts / resolve_studio_prompt）。
#  - key 唯一且稳定；default_content 保存出厂默认，用于「一键重置」。
# ============================================================
class AutomationPrompt(Base):
    """自动化创作提示词（可编辑、覆盖默认常量）"""
    __tablename__ = "automation_prompt"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), nullable=False, unique=True, index=True)  # 稳定键：EXPERT_TEAM_DESC / SYSTEM_PROMPT / STAGE_draft / PLANNER_CLARIFY_PROMPT ...
    category = Column(String(32), default="system")   # team / system / planner / writer / stage / revise / mdx
    name = Column(Text, default="")                   # 展示名（中文）
    expert_role = Column(String(32), default="")      # 负责专家角色：主编/写手/合规官/数据核查员/系统
    step_no = Column(Integer, default=0)              # 关联工作流步骤（0=全局/背景）
    content = Column(Text, default="")                # 当前生效内容（用户可编辑）
    default_content = Column(Text, default="")        # 出厂默认（用于重置）
    sort_order = Column(Integer, default=0)
    updated_at = Column(DateTime, default=now, onupdate=now)
    create_time = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  LLM 调用日志（三 API 调度：每次调用都落库，含响应耗时 / 命中配置 / 成功失败）
#  用途：①负载均衡与故障切换的可观测性；②步骤透明面板展示「哪个 API、耗时多少」；
#        ③mock 模式也落「模拟调用」日志（标注 is_mock=1），便于无密钥时演示完整链路。
# ============================================================
class LlmCallLog(Base):
    """每次 LLM（DeepSeek 等）调用的记录，含响应耗时与命中配置。"""
    __tablename__ = "llm_call_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, default=0, index=True)     # 关联 browser_studio_run.id（0=非运行内调用，如测试）
    step_key = Column(String(32), default="")           # 调用所属步骤（clarify/outline/draft/...）
    role = Column(String(16), default="general")        # research / writing / review / general
    config_id = Column(Integer, default=0)              # 实际命中的 LlmConfig.id
    provider = Column(String(32), default="")
    model = Column(String(64), default="")
    endpoint = Column(Text, default="")
    latency_ms = Column(Integer, default=0)             # 实际响应耗时（毫秒）；失败为 0
    prompt_chars = Column(Integer, default=0)           # 发送 prompt 字符数
    status = Column(Integer, default=1)                 # 1 成功 / 0 失败
    is_mock = Column(Integer, default=0)                # 1=模拟调用（无真实密钥）
    error = Column(Text, default="")                    # 失败原因（status=0 时）
    created_at = Column(DateTime, default=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  平台合规发布策略（各发布平台的格式/禁区/发布模式/AI 抓取优化）
#  - 每个 Platform 对应一条 PublishStrategy（1:1）；
#  - 字段结构化，供「自动化指挥中心」查看/编辑，也供合规闸门与发布器引用。
# ============================================================
class PublishStrategy(Base):
    """各发布平台的合规发布策略（结构化）。"""
    __tablename__ = "publish_strategy"
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey("platform.id"), nullable=False, unique=True, index=True)
    # 文章格式要求
    title_min_len = Column(Integer, default=8)          # 标题最短字数
    title_max_len = Column(Integer, default=30)         # 标题最长字数
    min_words = Column(Integer, default=800)            # 正文最少字数
    max_words = Column(Integer, default=2000)           # 正文最多字数
    structure_rules = Column(Text, default="")          # 正文结构规范（如「≥5 个二级标题 + FAQ≥3 组」）
    paragraph_rules = Column(Text, default="")          # 段落规范（如「每段 ≤ 5 行、首段点题、段间空行」）
    # 禁止标准
    banned_words_rule = Column(Text, default="")        # 违禁词/敏感内容检测规则（引用 rule 库或自定义描述）
    soft_ad_rule = Column(Text, default="")             # 软文/硬广判定规则（如「品牌名≤2 次、禁联系方式」）
    # 发布模式
    publish_mode_type = Column(String(16), default="direct")  # direct=直接发布 / draft=存草稿 / scheduled=定时
    # AI 搜索抓取优化（GEO）
    geo_keyword_density = Column(String(16), default="2-4%")   # 目标关键词密度
    geo_structured_summary = Column(Integer, default=1)        # 1=要求结构化摘要/小标题问答
    geo_title_info = Column(Integer, default=1)                # 1=标题需含信息量（疑问式/数据式）
    geo_notes = Column(Text, default="")                # GEO 额外说明
    notes = Column(Text, default="")                    # 其它备注
    create_time = Column(DateTime, default=now)
    update_time = Column(DateTime, default=now, onupdate=now)
    is_deleted = Column(Integer, default=0)


# ============================================================
#  背景库（实时更新的可投喂 AI 背景资料）
# ============================================================
class BackgroundLibrary(Base):
    """背景库：把一个行业的「品牌资产 + 知识库」沉淀为一份可一键复制、投喂给任意 AI 的背景资料。

    - hard_background：硬性背景，由 AI 结合当前知识库内容生成、用户可编辑，是投喂给 AI 的核心叙述。
    - include_brand：导出时是否包含品牌资产（1=包含）。
    - excluded_item_ids：JSON 数组，记录从导出中排除的知识点 id（默认空=全包含）。
    每个行业唯一一份（industry_id 唯一）。
    """
    __tablename__ = "background_library"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry_id = Column(Integer, ForeignKey("industry.id"), nullable=False, index=True, unique=True)
    hard_background = Column(Text, default="")
    include_brand = Column(Integer, default=1)
    excluded_item_ids = Column(Text, default="[]")
    updated_at = Column(DateTime, default=now, onupdate=now)

