"""三大规则库管理路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrandAsset, Industry, RuleLibrary
from ..utils import to_dict

router = APIRouter(prefix="/api/rule", tags=["规则库"])


class RuleIn(BaseModel):
    industry_id: int
    rule_type: str  # ai_seo / anti_ai / compliance / creation
    content: str
    platform_ids: str = "all"
    status: int = 1
    sort: int = 0


@router.get("")
def list_rules(industry_id: int, rule_type: Optional[str] = None,
               platform_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(RuleLibrary).filter(
        RuleLibrary.industry_id == industry_id,
        RuleLibrary.is_deleted == 0
    )
    if rule_type:
        q = q.filter(RuleLibrary.rule_type == rule_type)
    items = q.order_by(RuleLibrary.sort.asc()).all()
    result = []
    for r in items:
        d = to_dict(r)
        if platform_id and r.platform_ids and r.platform_ids != "all":
            pids = [int(x) for x in r.platform_ids.split(",") if x.strip().isdigit()]
            d["_matched"] = platform_id in pids
        else:
            d["_matched"] = True
        result.append(d)
    return {"code": 0, "data": result}


@router.post("")
def create_rule(payload: RuleIn, db: Session = Depends(get_db)):
    it = RuleLibrary(**payload.dict())
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"code": 0, "data": to_dict(it), "msg": "创建成功"}


@router.put("/{item_id}")
def update_rule(item_id: int, payload: RuleIn, db: Session = Depends(get_db)):
    it = db.query(RuleLibrary).filter(RuleLibrary.id == item_id).first()
    if not it:
        raise HTTPException(404, "规则不存在")
    for k, v in payload.dict().items():
        setattr(it, k, v)
    db.commit()
    return {"code": 0, "msg": "更新成功"}


@router.delete("/{item_id}")
def delete_rule(item_id: int, db: Session = Depends(get_db)):
    it = db.query(RuleLibrary).filter(RuleLibrary.id == item_id).first()
    if not it:
        raise HTTPException(404, "规则不存在")
    it.is_deleted = 1
    db.commit()
    return {"code": 0, "msg": "已删除"}


@router.patch("/{item_id}/status")
def toggle_status(item_id: int, status: int = 1, db: Session = Depends(get_db)):
    it = db.query(RuleLibrary).filter(RuleLibrary.id == item_id).first()
    if not it:
        raise HTTPException(404, "规则不存在")
    it.status = status
    db.commit()
    return {"code": 0, "msg": "状态已更新"}


@router.post("/sort")
def sort_rules(items: List[dict], db: Session = Depends(get_db)):
    for i, it in enumerate(items):
        db.query(RuleLibrary).filter(RuleLibrary.id == it["id"]).update({"sort": i})
    db.commit()
    return {"code": 0, "msg": "排序已更新"}


@router.post("/batch_import")
def batch_import(payload: dict, db: Session = Depends(get_db)):
    industry_id = payload.get("industry_id")
    rule_type = payload.get("rule_type")
    contents = payload.get("contents", [])
    platform_ids = payload.get("platform_ids", "all")
    count = 0
    for i, c in enumerate(contents):
        if not c.strip():
            continue
        db.add(RuleLibrary(
            industry_id=industry_id, rule_type=rule_type,
            content=c.strip(), platform_ids=platform_ids,
            status=1, sort=i
        ))
        count += 1
    db.commit()
    return {"code": 0, "msg": f"已导入 {count} 条规则"}


# ========== 一键灌入默认模板 ==========
# GEO 双信任规则：
# - ai_seo 侧重「算法信任」：让 AI 能抽取、能引用、能归属
# - anti_ai 侧重「心智信任」：有温度、像真人、读者愿意信
# - compliance 侧重「可信底线」：数据有源、不虚构、不硬广
# - creation 侧重「创作法则」：结构化/数据案例/语言精准化/4类内容/自检清单，直接驱动软文生产
_DEFAULT_RULES = {
    "ai_seo": [
        "核心关键词在标题、首段、小标题中自然出现，避免堆砌",
        "关键词密度控制在 2%-5%，主关键词 + 2-3 个长尾词协同布局",
        "使用长尾词覆盖更多搜索意图，回答用户真实问题",
        "结构化标题（H2/H3）层次清晰，便于搜索引擎与 AI 抓取",
        "每篇围绕 1 个主关键词展开，主题集中不跑题",
        "重要信息前置，首段 100 字内点明主题与关键词",
        "品牌实体信号（品牌名/官网/联系方式/核心产品）在文中可溯源出现，便于 AI 引用",
        "关键论点配可量化数据（数字+单位 / 百分比 / 案例数），提升事实密度",
        "用疑问式标题与 FAQ 形态组织内容，让 AI 能直接抽取为标准答案",
        "至少 1 处可归属证据（据…显示 / 客户案例 / 实测数据），让引用有凭据",
        "清单与对比用有序/无序列表呈现，提升结构化可解析度",
        "围绕目标客户真实意图问题写作，使内容在 AI 回答该问题时可被检索引用",
        # ===== 以下为功能性扩充（算法信任维度更细）=====
        "为关键指标/方法配官方定义或来源链接，提升 E-E-A-T 可信度，便于 AI 引用",
        "在文章首段与 FAQ 中稳定出现品牌全名与官网域名，强化实体一致性",
        "关键结论用加粗或列表突出，让 AI 能直接当作答案片段抽取",
        "对对比类问题给出结构化对照表（维度 / 我们 / 通用做法），便于 AI 引用",
        "为可量化主张标注时间/范围/口径，让数据可核验、可追溯",
        "用一致的实体命名（中文全名 + 英文缩写）建立跨篇品牌一致性",
        "文末提供「相关阅读/延伸问题」，扩展被检索到的长尾问题面",
        "在可被结构化数据（JSON-LD）标注的位置露出核心实体（名称/网址/产品），利于 AI 解析",
        "在结论句中使用「据…/根据…/数据显示…」的归属句式，让 AI 引用时能附上来源",
        "为每个 H2 小标题写一句可直接被抽取为答案的总结句（一句话给结论），再展开论述",
        "文章内自然出现 2-3 个同义长尾问句（「XX 怎么选」「XX 多少钱」），扩展被检索的问题面",
        "品牌官网域名在文中以可点击形式出现至少 1 次（如「详见 www.xxx.com」），强化实体链接信号",
        "首段给出 TL;DR 式的一句话核心结论，让 AI 在摘要/Featured Snippet 中直接引用",
    ],
    "anti_ai": [
        "多用短句和口语化表达，避免长难句与从句堆砌",
        "禁止使用「首先/其次/最后/综上所述/总而言之」等模板化连接词",
        "加入个人观点、具体案例或真实细节，增强真人感",
        "避免空洞形容词堆叠，用具体数据或场景替代",
        "段落长短错落，不要每段都一样长、一样结构",
        "适当使用设问、反问、口语化语气词，让行文有温度",
        "开篇先共情读者困境（用「你/咱们」视角），再给专业判断，建立信任",
        "用生活化类比把专业概念讲「好懂」，再补一句准确表述供 AI 抽取",
        "讲一个真实的人/厂如何踩坑又走出来的小故事，增强可信与温度",
        "给读者一个今天就能用的一小步建议，哪怕不买我们也能用，建立善意",
        "结尾留开放钩子（反直觉结论/待续问题），让人想继续看或私信",
        "承认行业坑点显真诚，不回避风险，比一味自夸更可信",
        # ===== 以下为功能性扩充（心智信任维度更细）=====
        "用「你/咱们」第二人称拉近距离，别通篇第三人称客观腔",
        "把抽象论述换成具体场景（「如果你厂里…」「我们常见的情况是…」），更易代入",
        "用前辈而非客服的语气给建议，像有经验的同行在跟你聊",
        "在关键处补一句对读者困境的共情或鼓励，别一上来就推销",
        "适当用行业黑话与口语词，增强真人感与专业可信度（不刻意书面化）",
        "长短句交错，避免每段结构机械对称，读起来有呼吸感",
        "给一个读者能马上验证的小判断/小测试，建立「这人真懂」的信任",
        "真实呈现取舍与成本（「贵但省心」「便宜但要盯」），不只讲好处",
        "用「说实话」「坦白讲」「给你交个底」这类口语化开头拉近距离，别用「众所周知」",
        "适当自嘲或暴露小缺点（「贵是贵了点，但…」），比完美人设更可信",
        "引用一句真实的客户原话或吐槽（带引号），增强真人感与说服力",
        "结尾别用「综上所述/总而言之」，换成一句反问或邀请（「你怎么看？」「要不要聊聊？」）",
        "写完朗读一遍：如果听起来像机器写的（没有停顿、没有语气词），就改到像说话",
    ],
    "compliance": [
        "联系方式仅在文末出现一次，不在正文中穿插",
        "不使用绝对化用语（如「最好」「第一」「唯一」「国家级」）",
        "不承诺具体效果或收益，不暗示 guaranteed 结果",
        "引用数据需注明来源，避免虚假或夸大宣传",
        "遵守《广告法》及各平台内容合规要求，规避限流风险",
        "医疗、金融、教育等特殊行业需加风险提示",
        "论据库证据须可核验，来源标注清晰，不编造检测报告或客户案例",
        "品牌推荐作为客观选型建议自然带出，不贬低同行、不硬广",
        "无法量化的处用区间或「行业普遍」表述，不虚构精确数字",
        "品牌故事/信任状可讲，但不得暗示垄断、唯一或绝对领先",
        # ===== 以下为功能性扩充（可信底线维度更细）=====
        "涉及第三方品牌/产品时客观表述，不引导贬损或拉踩",
        "用户案例与数据须脱敏，不泄露客户隐私与敏感商业信息",
        "价格/优惠信息须真实有效，标注有效期与适用条件",
        "「免费/限时/独家」等稀缺性话术须有真实依据，禁止虚假紧迫感",
        "文中若含外链/二维码，仅指向官方可信渠道，不导流至无关站点",
        "对「最/极/第一」等《广告法》违禁表述做发布前自检",
        "对比竞品时只列客观参数，不使用贬义形容词描述对手",
        "引用第三方数据须标注「据公开资料/据 XX 报告」，不冒充一手数据",
        "涉及价格时注明「仅供参考，以实际报价为准」，避免价格误导",
        "不使用「治愈/根治/100% 有效」等绝对化疗效表述（特殊行业红线）",
        "文末联系方式标注「官方」字样，不引导加非官方个人微信或群聊",
    ],
    "creation": [
        "核心信息前置：首段 100 字内点明主题与结论，别把关键埋进长段落",
        "用 H1/H2/H3 标题层级当路标，一级标题亮主题、二级分板块、三级拆要点",
        "把「首先…其次…最后…」的长句改成有序/无序列表，AI 提取效率翻倍",
        "对比类内容（参数/方案/成本）用结构化表格呈现，别用文字堆",
        "每个核心论点都配可量化数据：具体数字+单位、百分比、案例数量，替换「效果很好」这类空话",
        "用「某客户接入后，X 指标从 A 降到 B」的具象化案例，地域/行业/结果都明确",
        "把模糊表述改成精准参数：「时间缩短很多」→「从 3 小时缩到 30 分钟」",
        "专业术语必须配「小白能懂」的解释：术语 +（该技术让…提升至…）",
        "避免模糊词（差不多/大概/可能）、抽象词（赋能/打通/颠覆）无指向地堆砌",
        "对标 AI 最爱的 4 类内容创作：问题解答型(Q&A) / 评测对比型 / 实操指南型 / 案例分析型",
        "按「背景→问题→方案→结果」讲故事，有逻辑有结果，人机都爱",
        "写完过自检清单：核心观点 3 秒说清？每论点有数据/案例？术语都解释了？结构用标题/列表理清？有真实场景？",
        "做 AI 与用户的双向翻译：把专业术语转成生动故事，把技术参数包装成用户利益",
        "技术参数放在详情页，正文用场景化表达（「李阿姨说自从装了…」），别通篇堆参数",
        "结尾留开放钩子（反直觉结论/待续问题），让读者想继续看或主动了解更多",
        "每 300 字至少出现 1 个可量化数据点或 1 个具体案例，保持事实密度节奏",
        "用「问题→答案→证据」三段式组织每个小节，AI 和读者都能快速定位核心信息",
        "把技术参数翻译成用户利益：「极限真空度 5×10⁻² Pa」→「能把腔体抽到接近真空，满足镀膜工艺要求」",
        "正文配 1-2 张信息图或对比表，图文结合的内容被 AI 引用概率更高",
        "开头 3 行内必须出现目标关键词，且读起来自然不堆砌",
        "每个核心论点用「观点 + 数据 + 案例」三件套支撑，缺一不可",
    ],
}


@router.post("/seed/{industry_id}")
def seed_default_rules(industry_id: int, db: Session = Depends(get_db)):
    """一键灌入三大规则库默认模板（按内容去重、逐行追加，已存在的规则不重复添加，便于后续扩充默认规则）"""
    seeded = {}
    for rtype, contents in _DEFAULT_RULES.items():
        seeded[rtype] = 0
        base = db.query(RuleLibrary).filter(
            RuleLibrary.industry_id == industry_id,
            RuleLibrary.rule_type == rtype,
            RuleLibrary.is_deleted == 0,
        ).count()
        idx = 0
        for c in contents:
            c = c.strip()
            if not c:
                continue
            existing = db.query(RuleLibrary).filter(
                RuleLibrary.industry_id == industry_id,
                RuleLibrary.rule_type == rtype,
                RuleLibrary.content == c,
                RuleLibrary.is_deleted == 0,
            ).first()
            if existing:
                continue
            db.add(RuleLibrary(
                industry_id=industry_id, rule_type=rtype,
                content=c, platform_ids="all", status=1, sort=base + idx,
            ))
            idx += 1
            seeded[rtype] += 1
    db.commit()
    total = sum(seeded.values())
    msg = f"已灌入 {total} 条默认规则"
    return {"code": 0, "msg": msg, "data": {"seeded": seeded, "total": total}}


RULE_TYPE_LABELS = {
    "ai_seo": "AI SEO 规则",
    "anti_ai": "去 AI 味规则",
    "compliance": "平台合规规则",
    "creation": "创作规则",
}
RULE_TYPE_DESCS = {
    "ai_seo": "指导内容在搜索引擎与 AI 收录中更易被检索、引用、获得排名",
    "anti_ai": "约束行文口吻与结构，降低机械感、提升真人可读性",
    "compliance": "满足各平台内容合规要求，规避限流、下架等风险",
    "creation": "结构化优先（标题/列表/表格）、数据案例驱动、语言精准化、对标 AI 最爱的 4 类内容（Q&A/评测/实操/案例）",
}


@router.post("/assistant-prompt")
def generate_rule_assistant_prompt(payload: dict, db: Session = Depends(get_db)):
    """生成辅助提示词：基于行业/品牌/已有规则拼装一段提示词，

    用户复制到任意 AI 平台粘贴，AI 会批量生成/优化规则，输出可直接逐行导入的格式。
    """
    industry_id = payload.get("industry_id")
    if not industry_id:
        raise HTTPException(400, "industry_id 必填")

    ind = db.query(Industry).filter(Industry.id == industry_id).first()
    industry_name = ind.name if ind else "当前行业"

    brands = db.query(BrandAsset).filter(
        BrandAsset.industry_id == industry_id,
        BrandAsset.is_deleted == 0,
    ).all()

    # 按类型统计已有规则
    rule_counts = {}
    rule_samples = {}
    for rtype in ("ai_seo", "anti_ai", "compliance", "creation"):
        rows = db.query(RuleLibrary).filter(
            RuleLibrary.industry_id == industry_id,
            RuleLibrary.rule_type == rtype,
            RuleLibrary.is_deleted == 0,
        ).order_by(RuleLibrary.sort.asc()).all()
        rule_counts[rtype] = len(rows)
        rule_samples[rtype] = [r.content for r in rows[:8]]  # 每类最多取 8 条样例

    total_existing = sum(rule_counts.values())
    parts = []

    # 角色
    parts.append(
        f"你是一位 {industry_name} 行业的内容策略专家，精通 GEO（生成式引擎优化）与各大内容平台的规则体系。\n"
        f"你的任务是：根据公司背景与已有规则，批量生成或优化**内容创作规则**，"
        f"让 AI 在写作时能自动遵循这些规则，产出既被 AI 引用又让人愿意读的内容。"
    )

    # 公司背景
    parts.append("## 公司背景")
    if brands:
        b = brands[0]
        bp = [f"- **品牌**：{b.brand_name}"]
        if b.slogan:
            bp.append(f"- **定位**：{b.slogan}")
        if b.core_products:
            bp.append(f"- **核心产品**：{b.core_products}")
        if b.unique_selling_points:
            bp.append(f"- **独特优势**：{b.unique_selling_points}")
        parts.append("\n".join(bp))
    else:
        parts.append(f"- （暂无品牌信息，请根据「{industry_name}」行业常识推断）")

    # 四大规则类型
    parts.append("## 四类规则说明")
    for rtype in ("ai_seo", "anti_ai", "compliance", "creation"):
        parts.append(
            f"- **{RULE_TYPE_LABELS[rtype]}**（已有 {rule_counts[rtype]} 条）：{RULE_TYPE_DESCS[rtype]}"
        )

    # 已有规则样例
    parts.append("## 已有规则样例（参考，可在此基础上补充/优化）")
    for rtype in ("ai_seo", "anti_ai", "compliance", "creation"):
        samples = rule_samples[rtype]
        if samples:
            parts.append(f"### {RULE_TYPE_LABELS[rtype]}")
            for s in samples:
                parts.append(f"- {s}")
        else:
            parts.append(f"### {RULE_TYPE_LABELS[rtype]}（暂无规则，可自由创建）")

    # 任务
    parts.append("""## 任务要求

请基于以上行业背景、品牌定位与已有规则，生成新的内容创作规则。要求：

1. **每条规则是明确的指令**，如"多用口语化短句"、"核心关键词自然融入 H2/H3 小标题"，而非名词短语或概念描述
2. **按四类分别生成**，每类至少 3-5 条
3. **规则要落地可执行**：不要写"提升内容质量"，要写"每段首句使用承上启下的过渡句，避免段落之间断裂"
4. **补充已有规则未覆盖的盲区**：如果已有规则偏重结构，就多补口语和情感层面；如果已有偏重 SEO，就多补用户体验和可读性
5. **输出的规则按类型分组**，每组用 `【规则类型名】` 作为标题行

## 输出格式

每行一条规则，分组标题以【】标注。例如：

【AI SEO 规则】
核心关键词在标题、首段、H2 小标题中自然出现
每篇文章至少包含一个结构化列表（有序或无序）
链接锚文本使用描述性词汇而非"点击这里"

【去 AI 味规则】
每段首句口语化，避免"值得注意的是""综上所述"等模板句式
数据后紧接解释"这对你意味着什么"

只输出规则内容，不要额外解释。""")

    prompt = "\n\n".join(parts)

    return {
        "code": 0,
        "data": {
            "prompt": prompt,
            "existing_count": total_existing,
            "counts": rule_counts,
            "brand_count": len(brands),
        }
    }
