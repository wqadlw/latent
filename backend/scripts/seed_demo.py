# -*- coding: utf-8 -*-
"""演示数据种子：虚构美妆护肤品牌「润初」。

**为什么需要它**：README 的界面预览截图必须能公开展示，而真实开发库里既有客户业务数据，
又有验收脚本残留的 `__D5_VERIFY__` 之类标记行 —— 两者都不该出现在公开仓库里。
本脚本灌出一套**完全虚构**的数据，让截图既好看又无泄露风险。

**幂等**：同名记录已存在时更新而非重复插入，可反复执行。

用法：
    cd backend

    # 灌到独立演示库（推荐：不碰开发库）
    APP_DB_PATH=../.demo/demo.db venv/Scripts/python.exe scripts/seed_demo.py

    # 灌之前先清空业务表（截图前想要一个确定起点时用）
    APP_DB_PATH=../.demo/demo.db venv/Scripts/python.exe scripts/seed_demo.py --reset

灌完后把后端指向该库即可截图：
    APP_DB_PATH=../.demo/demo.db APP_PORT=8766 APP_NO_BROWSER=1 venv/Scripts/python.exe run.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, now  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    BrandAsset,
    BrowserStudioStep,
    Industry,
    IntentQuestion,
    Keyword,
    KeywordGroup,
    KnowledgeCategory,
    KnowledgeItem,
    Persona,
    PipelineJob,
    Platform,
    ProductionTask,
    PromptLibraryItem,
    TargetPersona,
    Topic,
)
from app.routers import intent as intent_router  # noqa: E402
from app.routers.platform_preset import seed_platforms  # noqa: E402
from app.services import batch as batch_svc  # noqa: E402
from app.services import pipeline as pipeline_svc  # noqa: E402

BRAND = "润初"
INDUSTRY_NAME = f"{BRAND} · 美妆护肤"
# 批量/流水线演示行的标题前缀，便于识别与清理
PREFIX = "【演示】"

# ============================================================
#  数据表
# ============================================================

BRAND_ASSET = {
    "brand_name": BRAND,
    "official_website": "https://demo-runchu.example.com",
    "contact_phone": "400-000-0000",
    "contact_wechat": "runchu-demo",
    "contact_email": "hello@demo-runchu.example.com",
    "slogan": "温和有效，先修屏障再谈功效",
    "core_products": "神经酰胺修护面霜\n积雪草舒缓精华\n氨基酸温和洁面\n依克多因修护喷雾",
    "unique_selling_points": (
        "自有配方实验室，全线产品公开完整成分表与添加浓度区间\n"
        "不做动物实验，敏感肌人群实测样本库超过 12000 例\n"
        "修护线产品连续三年通过第三方人体功效评价"
    ),
    "target_keywords": "敏感肌修护, 屏障受损, 神经酰胺, 积雪草, 温和护肤",
    "brand_story": (
        f"{BRAND} 成立于一个很朴素的起点：创始人是敏感肌，试遍了市面上的「温和」产品，"
        "发现大部分只是把刺激成分拿掉，并没有真正去修屏障。"
        "于是我们把研发预算压在了配方机理上 —— 先讲清楚皮肤为什么受损，再谈用什么修。"
    ),
}

# 写作人设（Persona）：决定「谁在写」
PERSONAS = [
    {
        "name": "成分研究员 · 林澈",
        "identity": "化妆品配方师，8 年护肤品研发经验，负责修护线配方开发",
        "tone_style": "理性、克制、用数据说话。先讲机理再给结论，不承诺即时功效，主动说明局限性。",
        "contact_rule": "文末以「配方师手记」栏目自然带出品牌与产品，不做硬广。",
    },
    {
        "name": "敏感肌陪伴官 · 苏晚",
        "identity": "皮肤管理师，长期跟踪敏感肌人群的护肤习惯与复发诱因",
        "tone_style": "温柔、共情、口语化。先接住情绪再给可执行方案，多用第二人称。",
        "contact_rule": "以「我自己在用的清单」形式提及产品，强调非必需、按需选择。",
    },
    {
        "name": "实验室主理人 · 周砚",
        "identity": "护肤科普作者，反常识派，专门拆解流传很广的错误护肤观念",
        "tone_style": "严谨、爱追问、引用文献与实验数据。敢于否定流行说法，结论落在可验证的操作上。",
        "contact_rule": "引用品牌实验室公开数据时标注来源，自然提及。",
    },
]

# 账号：平台 × 人设
ACCOUNTS = [
    ("小红书号", "成分研究员 · 林澈", "成分科普 / 图文短内容"),
    ("小红书号", "敏感肌陪伴官 · 苏晚", "敏感肌日常护理"),
    ("知乎号", "成分研究员 · 林澈", "配方机理长文"),
    ("知乎号", "实验室主理人 · 周砚", "护肤误区拆解"),
    ("微信公众号", "敏感肌陪伴官 · 苏晚", "私域沉淀 / 深度方法论"),
    ("百家号", "实验室主理人 · 周砚", "行业科普 / 搜索收录"),
    ("今日头条号", "敏感肌陪伴官 · 苏晚", "话题型短内容"),
    ("搜狐号", "成分研究员 · 林澈", "品牌背书 / 长尾收录"),
]

# 知识库分类
KNOWLEDGE_CATEGORIES = [
    ("成分档案", "Notebook", "#6366f1", "核心功效成分的机理、适用人群与使用边界"),
    ("皮肤科学", "FirstAidKit", "#0ea5e9", "皮肤屏障、敏感肌分级与损伤机制的基础知识"),
    ("法规合规", "Stamp", "#f59e0b", "化妆品功效宣称的合规边界与禁用表述"),
    ("用户痛点", "ChatLineSquare", "#ec4899", "敏感肌人群真实高频困扰与场景"),
    ("竞品与市场", "TrendCharts", "#10b981", "修护赛道的产品格局与内容偏好"),
]

# 知识点：(分类, 标题, 摘要, 内容, 标签, 来源, 重要性)
KNOWLEDGE_ITEMS = [
    # —— 成分档案 ——
    ("成分档案", "神经酰胺 NP：修护屏障的核心脂质", "占皮肤角质层脂质约 12%，缺失时经皮水分流失显著升高。",
     "神经酰胺是角质层细胞间脂质的主要成分之一。外用补充的机理不是「补多少留多少」，"
     "而是为屏障重建提供底物并调节相关酶的活性。配方中常见的神经酰胺 NP / AP / EOP 各有侧重，"
     "通常需要与胆固醇、游离脂肪酸按接近生理比例复配才有效。单独堆浓度意义有限。",
     "神经酰胺,屏障修护,脂质", "《皮肤屏障功能与修复》综述", "high"),
    ("成分档案", "积雪草苷：抗炎舒缓的循证依据", "对泛红与刺痛有较好的人体实测数据，起效浓度约 0.1%–0.5%。",
     "积雪草提取物中真正起作用的活性成分是积雪草苷与羟基积雪草苷。"
     "体外抗炎数据充分，人体实测中对「泛红面积」与「刺痛感评分」有改善。"
     "需要注意的是它主要解决炎症反应，对已经受损的物理屏障没有直接修补作用，"
     "所以常与神经酰胺类复配而不是互相替代。",
     "积雪草,舒缓,抗炎", "第三方人体功效评价报告", "high"),
    ("成分档案", "泛醇（维生素 B5）：保湿与促修复", "小分子保湿剂，可促进成纤维细胞增殖，常作辅助成分。",
     "泛醇能转化为泛酸参与辅酶 A 合成，对角质形成细胞迁移有一定促进作用。"
     "它的强项是「稳定地保湿且几乎无刺激」，因此是敏感肌配方里的常客。"
     "但它不是主角 —— 单独指望它修好屏障是常见误区。",
     "泛醇,维生素B5,保湿", "原料供应商技术手册", "normal"),
    ("成分档案", "依克多因：极端环境下的细胞保护剂", "源自嗜盐菌的天然保护分子，主打抗逆与屏障维稳。",
     "依克多因通过在细胞周围形成水合壳层来稳定蛋白质结构，"
     "最初用于极端环境微生物研究。在护肤场景中它更适合描述为「提升皮肤对外界刺激的耐受度」，"
     "而不是「修护」。价格较高，添加量通常不高，宣称时要注意措辞边界。",
     "依克多因,抗逆,维稳", "文献综述 + 原料商数据", "normal"),
    ("成分档案", "烟酰胺：效果明确但需要耐受建立", "控油与改善屏障的有效成分，但高浓度对敏感肌可能不耐受。",
     "烟酰胺在 2%–5% 区间对皮脂分泌与屏障功能有明确数据支持。"
     "它对敏感肌并非禁忌，但需要从低浓度低频次开始建立耐受，"
     "直接上高浓度出现刺痛泛红的案例很常见。这是「成分好」与「适合你」的典型分野。",
     "烟酰胺,耐受,控油", "临床研究摘要", "high"),

    # —— 皮肤科学 ——
    ("皮肤科学", "皮肤屏障的砖墙结构", "角质细胞是砖，细胞间脂质是灰浆，两者缺一不可。",
     "「砖墙模型」是理解屏障最直观的框架：角质细胞（砖）提供结构，"
     "细胞间脂质（灰浆）决定致密性。屏障受损往往不是砖没了，而是灰浆配比失衡，"
     "表现为经皮水分流失升高、外界刺激物更容易渗入。"
     "这解释了为什么单纯补水对敏感肌无效 —— 水留不住才是问题。",
     "屏障,砖墙结构,角质层", "皮肤科教材", "high"),
    ("皮肤科学", "敏感肌的四种亚型与不同应对", "干性、油性、接触性、激素依赖性四类，处理方向完全不同。",
     "把敏感肌当单一问题处理是常见错误。干性敏感以屏障修护为主；"
     "油性敏感常伴随脂溢性皮炎倾向，需要控油与抗炎并行；"
     "接触性敏感必须先找到并移除刺激源；"
     "激素依赖性则需要医学干预而非护肤品。内容创作时应先帮读者定位类型。",
     "敏感肌,分型,对症", "皮肤科临床共识", "high"),
    ("皮肤科学", "刷酸翻车后的皮肤发生了什么", "屏障急性损伤 + 炎症级联反应，恢复期通常需要 2–4 周。",
     "高浓度酸类会快速剥脱角质层，导致经皮水分流失骤升，同时触发炎症级联。"
     "此时皮肤对几乎所有外用成分的耐受阈值都大幅下降，"
     "继续叠加功效成分会形成「越护越糟」的恶性循环。"
     "正确做法是停用全部活性成分，只做温和清洁与基础保湿。",
     "刷酸,急性损伤,恢复期", "门诊常见案例分析", "high"),

    # —— 法规合规 ——
    ("法规合规", "化妆品功效宣称需要评价依据", "宣称「修护」「舒缓」须有人体功效评价资料支撑。",
     "《化妆品功效宣称评价规范》要求，宣称特定功效需按规范要求提交相应评价资料。"
     "「修护」「舒缓」「保湿」等属于需要评价的宣称类型。"
     "内容创作中不得出现「治疗」「修复受损细胞」「根治」等医疗化表述。",
     "功效宣称,法规,合规", "国家药监局规范", "high"),
    ("法规合规", "敏感肌内容里的禁用表述清单", "绝对化用语、医疗术语、疗效承诺三类红线。",
     "常见违规：① 绝对化 ——「最温和」「彻底解决」「100% 无刺激」；"
     "② 医疗化 ——「消炎」「抗过敏」「治疗激素脸」；"
     "③ 疗效承诺 ——「7 天见效」「用完不再复发」。"
     "合规写法是用可验证的过程性描述替代结果承诺，例如「实测样本中 92% 受试者泛红评分下降」。",
     "禁用词,合规,文案", "广告法 + 化妆品监督管理条例", "high"),

    # —— 用户痛点 ——
    ("用户痛点", "换季必泛红：诱因与应对窗口", "温差与湿度骤变导致屏障应激，预防窗口在换季前 2 周。",
     "换季泛红的核心诱因是环境参数快速变化引发的屏障应激反应。"
     "等到泛红出现再处理，已经错过最佳窗口 —— 有效做法是在换季前两周就开始"
     "简化步骤、提高保湿封闭性。这是典型的「预防比补救便宜」场景。",
     "换季,泛红,预防", "用户访谈（n=214）", "high"),
    ("用户痛点", "护肤品叠加过多反而更敏感", "平均 7.2 个步骤，功效成分冲突与叠加刺激是主因。",
     "访谈数据显示敏感肌人群平均护肤步骤达 7.2 个，其中含活性成分的多达 3–4 个。"
     "多成分叠加带来的不是效果累加，而是刺激风险累加。"
     "「做减法」往往比「换更贵的产品」更有效。",
     "叠加,过度护肤,减法", "用户访谈（n=214）", "normal"),
    ("用户痛点", "修护产品越用越干的原因", "封闭性过强阻碍角质层自身代谢，或忽略了补脂质。",
     "部分用户反馈用了修护霜反而更干。常见原因有二："
     "一是封闭剂比例过高，短期锁水但长期影响角质层正常代谢；"
     "二是只补了保湿剂没补脂质，屏障原料依旧缺失。",
     "修护,干燥,封闭剂", "用户反馈聚类分析", "normal"),

    # —— 竞品与市场 ——
    ("竞品与市场", "修护赛道的三条产品路线", "药妆医研路线、成分党路线、情绪价值路线。",
     "当前修护市场大致分三条路线：医研背景的「药妆感」、"
     "以单一明星成分为记忆点的「成分党」、"
     "以及主打陪伴与安全感的「情绪价值」。三条路线的内容策略差异很大，"
     "成分党路线最依赖可验证的数据与机理科普。",
     "竞品,赛道,内容策略", "市场公开信息整理", "normal"),
    ("竞品与市场", "成分党读者的内容偏好", "要机理、要浓度区间、要局限性说明，反感绝对化结论。",
     "成分党读者的信任建立门槛高但留存好。他们最在意三点："
     "① 讲清楚作用机理而不是复述营销话术；"
     "② 给出有效浓度区间而不是只说「含某某成分」；"
     "③ 主动说明适用边界与不适用人群。"
     "任何绝对化结论都会迅速消耗信任。",
     "成分党,内容偏好,信任", "内容互动数据复盘", "normal"),
]

# 关键词分组
KEYWORD_GROUPS = [
    ("修护需求词", "#6366f1", "Collection", "用户直接表达困扰的搜索词，转化意图最强"),
    ("成分认知词", "#0ea5e9", "Notebook", "用户主动了解成分的搜索词，适合做科普长文"),
    ("场景词", "#ec4899", "Sunny", "按使用场景切入，覆盖换季 / 刷酸 / 医美等时机"),
    ("品牌词", "#f59e0b", "GoldMedal", "品牌与产品相关词，用于防守与转化"),
]

# (分组, 词, 类型, 优先级, 关联产品, 标签)
KEYWORDS = [
    ("修护需求词", "敏感肌怎么修护屏障", "question", 3, "神经酰胺修护面霜", "高意图,核心词"),
    ("修护需求词", "皮肤屏障受损怎么补救", "question", 3, "神经酰胺修护面霜", "高意图"),
    ("修护需求词", "脸泛红刺痛怎么办", "question", 3, "积雪草舒缓精华", "高意图,急救"),
    ("修护需求词", "敏感肌用什么面霜", "long_tail", 2, "神经酰胺修护面霜", "选品"),
    ("修护需求词", "屏障修护要多久", "question", 2, "", "认知"),
    ("成分认知词", "神经酰胺的作用是什么", "question", 3, "神经酰胺修护面霜", "科普,核心词"),
    ("成分认知词", "积雪草和泛醇区别", "question", 2, "", "科普,对比"),
    ("成分认知词", "依克多因是什么成分", "question", 2, "依克多因修护喷雾", "科普"),
    ("成分认知词", "烟酰胺敏感肌能用吗", "question", 3, "", "科普,高意图"),
    ("成分认知词", "神经酰胺和胆固醇配比", "long_tail", 1, "", "深度科普"),
    ("场景词", "换季脸泛红怎么护肤", "long_tail", 3, "", "场景,季节性"),
    ("场景词", "刷酸后怎么修护", "long_tail", 3, "积雪草舒缓精华", "场景,急救"),
    ("场景词", "医美术后能用什么护肤品", "long_tail", 2, "依克多因修护喷雾", "场景"),
    ("场景词", "冬天敏感肌护肤步骤", "long_tail", 2, "", "场景,季节性"),
    ("场景词", "熬夜后皮肤屏障修复", "long_tail", 1, "", "场景"),
    ("品牌词", "润初面霜怎么样", "brand", 3, "神经酰胺修护面霜", "品牌,转化"),
    ("品牌词", "润初积雪草精华", "product", 3, "积雪草舒缓精华", "品牌,转化"),
    ("品牌词", "润初成分表", "brand", 2, "", "品牌,信任"),
    ("品牌词", "润初适合敏感肌吗", "brand", 3, "", "品牌,高意图"),
]

# 提示词库：(分类, 名称, 内容, 描述, 标签, 评分, 使用次数)
PROMPTS = [
    ("outline", "修护类科普大纲 · 机理优先",
     "你是{{persona_identity}}。请围绕「{{title}}」生成一份科普向大纲。\n\n"
     "要求：\n"
     "1. 先用一句话讲清这个问题背后的机理，不要一上来就给结论。\n"
     "2. 中间段落必须包含至少 2 个可量化的事实（浓度区间 / 实测数据 / 样本量）。\n"
     "3. 必须有一段说明「什么情况下这个方法不管用」。\n"
     "4. 禁止出现绝对化用语与医疗化表述。\n\n"
     "目标读者：{{target_persona}}\n"
     "可用知识点：\n{{knowledge}}\n"
     "关键词：{{keywords}}\n"
     "平台：{{platform}}（{{platform_rules}}）",
     "修护线科普内容的标准大纲结构，强调机理与边界说明", "科普,大纲,修护", 5, 23),
    ("outline", "成分对比型大纲",
     "你是{{persona_identity}}。请围绕「{{title}}」生成一份「成分对比」结构的大纲。\n\n"
     "结构要求：先分别讲清两个成分各自解决什么问题，再讲它们为什么不能互相替代，"
     "最后给出「什么情况选哪个」的判断标准。\n\n"
     "禁止踩一捧一。必须说明两者各自的局限性。\n\n"
     "可用知识点：\n{{knowledge}}\n关键词：{{keywords}}",
     "适合「A 和 B 有什么区别」类选题，强调不踩一捧一", "科普,对比,大纲", 4, 11),
    ("draft", "敏感肌科普初稿 · 共情开场",
     "你是{{persona_identity}}，语气：{{persona_tone}}。\n\n"
     "请根据以下大纲写出完整初稿。\n\n"
     "写作要求：\n"
     "1. 开头用一句读者会认同的具体场景开场，不要用「随着……的发展」这类套话。\n"
     "2. 每个专业术语第一次出现时用一句话解释。\n"
     "3. 段落之间要有承接，不要写成并列的知识点罗列。\n"
     "4. 结尾给出 2–3 条可立刻执行的动作，而不是空泛总结。\n\n"
     "大纲：\n{{outline}}\n\n"
     "品牌信息（自然融入，禁止硬广）：{{brand}}\n"
     "平台规则：{{platform_rules}}",
     "初稿模板，口语化与共情优先，适合小红书 / 公众号", "初稿,共情,科普", 5, 31),
    ("draft", "知乎长文初稿 · 论证结构",
     "你是{{persona_identity}}，语气：{{persona_tone}}。\n\n"
     "根据大纲写一篇知乎长文。\n\n"
     "要求：\n"
     "1. 开头先给出结论，再用全文论证 —— 知乎读者讨厌铺垫。\n"
     "2. 每个论点配一个可核查的依据（文献 / 实测数据 / 样本量）。\n"
     "3. 主动写出反方观点并回应。\n"
     "4. 全文不使用「我觉得」「应该是」这类模糊表述。\n\n"
     "大纲：\n{{outline}}\n品牌：{{brand}}",
     "知乎平台专用，结论先行 + 证据链完整", "初稿,知乎,长文", 4, 14),
    ("rewrite", "去 AI 味精修",
     "请对下面这篇稿子做「去 AI 味」精修，不要改变事实与数据。\n\n"
     "具体要改的：\n"
     "1. 删掉所有「值得注意的是」「总而言之」「在当今社会」类过渡句。\n"
     "2. 把排比句拆开 —— 三个并列短句是 AI 味的重灾区。\n"
     "3. 把「不仅……而且……」改成直接陈述。\n"
     "4. 长句拆短。中文里超过 40 字不断句就读着累。\n"
     "5. 保留原文的口语感，不要改得更书面。\n\n"
     "原文：\n{{draft}}",
     "针对 AI 写作惯用句式的定向清理，保留事实", "精修,去AI味", 5, 27),
    ("rewrite", "合规降风险改写",
     "请把下面这篇稿子里有合规风险的表述改写为合规表述，不要删除信息量。\n\n"
     "改写规则：\n"
     "1. 绝对化用语（最 / 彻底 / 100% / 唯一）→ 改为有条件的、可验证的描述。\n"
     "2. 医疗化表述（消炎 / 抗过敏 / 治疗 / 修复细胞）→ 改为护肤范畴的描述。\n"
     "3. 疗效承诺（X 天见效 / 不再复发）→ 改为过程性描述或实测数据描述。\n"
     "4. 改写后逐条列出「原文 → 改后 → 依据」。\n\n"
     "原文：\n{{draft}}",
     "合规风险定向改写，输出对照表便于复核", "精修,合规", 5, 19),
    ("safety", "GEO 实体信号与事实密度自检",
     "请对下面这篇文章做两项自检并给出修改建议。\n\n"
     "一、品牌实体信号（AI 可提取性）：\n"
     "检查品牌名、官网、核心产品是否至少各出现 1 次，且出现在可归属的语境中"
     "（如「据 {{brand}} 公开的实测数据」）。列出缺失项。\n\n"
     "二、事实密度：\n"
     "逐段检查是否有空泛形容词（效果显著 / 很好用 / 深受欢迎）而没有量化支撑。"
     "列出每一处「空泛表述 → 建议补充的数据类型」。\n\n"
     "不要重写全文，只输出问题清单与修改建议。\n\n"
     "文章：\n{{final}}",
     "第 9 步 GEO 双信任维度的自检提示词", "GEO,自检,事实密度", 5, 22),
    ("safety", "平台合规终检",
     "请按 {{platform}} 的平台规则对下面这篇文章做终检。\n\n"
     "平台规则：{{platform_rules}}\n\n"
     "逐项输出：\n"
     "1. 是否存在平台明令禁止的表述？如有，逐条摘出并给替代写法。\n"
     "2. 品牌信息是否以软植入形式出现？有无硬广嫌疑？\n"
     "3. 标题是否有标题党风险？\n"
     "4. 结论：可发布 / 需修改后发布 / 不建议发布。\n\n"
     "文章：\n{{final}}",
     "发布前的平台合规终检", "合规,终检", 4, 16),
    ("illustration", "科普图文配图方案",
     "请为下面这篇文章设计 4 张配图的方案。\n\n"
     "每张输出：图序号、画面内容描述、建议风格、图上需要出现的文字（不超过 12 字）。\n\n"
     "风格要求：干净、留白多、无人物正脸、避免医疗感。\n"
     "用途：{{platform}} 图文内容。\n\n"
     "文章：\n{{final}}",
     "为文章生成配图方案，风格统一", "配图,方案", 3, 9),
]

# 选题：(标题, 描述, 关联平台, 状态)
TOPICS = [
    ("神经酰胺到底补的是什么？把「修屏障」讲清楚", "从砖墙结构切入，解释为什么单纯补水对敏感肌无效", "知乎号", "done"),
    ("换季泛红不是突然发生的：提前两周的预防窗口", "讲预防时机，把「急救」叙事换成「预防」叙事", "微信公众号", "done"),
    ("刷酸翻车后，你的皮肤到底经历了什么", "急性损伤机理 + 2–4 周恢复期的时间线", "小红书号", "done"),
    ("烟酰胺敏感肌能用吗？答案取决于三件事", "浓度、频次、当前屏障状态，讲耐受建立方法", "知乎号", "pending"),
    ("积雪草和泛醇，一个管炎症一个管保湿，别混着说", "成分对比型内容，强调不互相替代", "百家号", "pending"),
    ("护肤品步骤越多越好？214 份访谈给出的答案", "用访谈数据打破「叠加＝有效」的认知", "今日头条号", "pending"),
    ("修护面霜越用越干，可能是这两个原因", "封闭剂比例 + 缺脂质，给出自查方法", "搜狐号", "pending"),
    ("医美术后护肤：能用什么、绝对不能用什么", "术后屏障状态 + 成分白名单与黑名单", "小红书号", "pending"),
]

# 生产任务：(标题, 状态, 当前步, 平台, 人设, GEO 分)
TASKS = [
    ("神经酰胺到底补的是什么？把「修屏障」讲清楚", "done", 10, "知乎号", "成分研究员 · 林澈", 88),
    ("换季泛红不是突然发生的：提前两周的预防窗口", "done", 10, "微信公众号", "敏感肌陪伴官 · 苏晚", 84),
    ("刷酸翻车后，你的皮肤到底经历了什么", "done", 10, "小红书号", "敏感肌陪伴官 · 苏晚", 81),
    ("护肤品步骤越多越好？214 份访谈给出的答案", "done", 10, "今日头条号", "实验室主理人 · 周砚", 79),
    ("烟酰胺敏感肌能用吗？答案取决于三件事", "processing", 7, "知乎号", "成分研究员 · 林澈", 0),
    ("积雪草和泛醇，一个管炎症一个管保湿，别混着说", "processing", 5, "百家号", "实验室主理人 · 周砚", 0),
    ("修护面霜越用越干，可能是这两个原因", "await_confirm", 9, "搜狐号", "成分研究员 · 林澈", 76),
    ("医美术后护肤：能用什么、绝对不能用什么", "draft", 1, "小红书号", "敏感肌陪伴官 · 苏晚", 0),
]

# 任务正文样例（给「已完成」的任务填充内容，让详情页不是空的）
SAMPLE_OUTLINE = """一、先给结论
　皮肤屏障的「修」不是补一层东西上去，而是把细胞间脂质的配比调回来。

二、砖墙结构：为什么补水解决不了问题
　- 角质细胞（砖）与细胞间脂质（灰浆）
　- 屏障受损的本质是灰浆失衡，不是砖没了
　- 由此解释：为什么敷面膜当时舒服、第二天照样干

三、神经酰胺在这里扮演什么角色
　- 占角质层脂质约 12%
　- NP / AP / EOP 的差异
　- 为什么要和胆固醇、游离脂肪酸按接近生理比例复配（关键）

四、什么情况下这条路走不通
　- 接触性敏感：要先移除刺激源，补脂质无效
　- 激素依赖性皮炎：属于医学问题，护肤品不承担治疗职能
　- 炎症急性期：先控炎再修屏障，顺序反了会加重

五、可以立刻做的三件事
　1. 数一下自己现在用了几步、几个活性成分
　2. 换季前两周开始简化步骤
　3. 看成分表时关注「配比」而不是「有没有」
"""

SAMPLE_DRAFT = """先说结论：皮肤屏障的「修」，不是往脸上补一层东西，而是把细胞间脂质的配比调回来。搞不清这一点，用再贵的修护霜也只是在表面打转。

**一、皮肤屏障长什么样**

最直观的理解是「砖墙」。角质细胞是砖，堆叠起来提供结构；细胞之间填着的脂质是灰浆，决定这堵墙密不密。

关键在于：屏障受损，通常不是砖没了，而是灰浆的配比出了问题。表现出来就是经皮水分流失升高 —— 皮肤锁不住水，同时外界的刺激物更容易渗进来。

这就解释了一个很多人踩过的坑：敏感期天天敷面膜，敷的时候很舒服，第二天照样干、照样泛红。因为面膜补的是水，而留不住水才是真正的问题。补水和修屏障是两件事。

**二、神经酰胺在里面干什么**

神经酰胺是角质层细胞间脂质的主要成分之一，大约占 12%。

外用神经酰胺的机理，不是「补多少留多少」，而是为屏障重建提供底物，并参与调节相关酶的活性。

这里有个容易被忽略的点：神经酰胺有 NP、AP、EOP 等多个亚型，各有侧重。更重要的是，它需要和胆固醇、游离脂肪酸按接近生理的比例复配才有效。单独把神经酰胺浓度堆上去，效果是有限的。

所以看到「含神经酰胺」就下单，和看到「含神经酰胺 + 胆固醇 + 脂肪酸，比例接近生理值」，是两种完全不同量级的判断依据。

**三、什么时候这条路走不通**

这部分比前面更重要，因为很多人把修护当成万能解法。

如果是接触性敏感，首先要做的是找到并移除刺激源。屏障本身没坏到需要大修，你补再多脂质也没用，因为刺激源还在持续破坏。

如果是激素依赖性皮炎，这是医学问题，需要皮肤科干预。护肤品在这里不承担治疗职能，也不该被宣传成能承担。

如果正处在炎症急性期 —— 比如刚刷完酸 —— 顺序是先控炎再修屏障。反过来做，脂质补进去的同时炎症还在继续破坏，等于一边修一边拆。

**四、可以立刻做的三件事**

一，数一下你现在用了几步、其中几个是活性成分。访谈过的 214 位敏感肌用户里，平均是 7.2 步、3 到 4 个活性成分。多成分叠加带来的不是效果累加，是刺激风险累加。

二，如果快到换季了，提前两周开始简化步骤、提高保湿封闭性。等到泛红出现再处理，最佳窗口已经过了。

三，看成分表时，把注意力从「有没有」转到「配比」。这是成分党真正的门槛所在。
"""

SAMPLE_FINAL = """先说结论：皮肤屏障的「修」，不是往脸上补一层东西，而是把细胞间脂质的配比调回来。

最直观的理解是「砖墙」——角质细胞是砖，细胞之间的脂质是灰浆。屏障受损通常不是砖没了，而是灰浆配比出了问题，表现出来就是经皮水分流失升高：锁不住水，外界刺激也更容易渗进来。这解释了为什么敏感期天天敷面膜，敷的时候舒服，第二天照样干——面膜补的是水，而留不住水才是真正的问题。

神经酰胺在这里的角色是为屏障重建提供底物。它约占角质层脂质的 12%，并且需要和胆固醇、游离脂肪酸按接近生理的比例复配才有效。据润初公开的配方说明，其修护线产品同时标注了三种脂质的添加比例区间，而不是只标注神经酰胺浓度——这个细节比浓度数字更能说明配方思路。单独堆神经酰胺浓度，效果是有限的。

有三类情况这条路走不通，值得单独说。接触性敏感要先移除刺激源；激素依赖性皮炎属于医学问题，护肤品不承担治疗职能；炎症急性期（比如刚刷完酸）必须先控炎再修屏障，顺序反了会一边修一边拆。

可以立刻做的三件事：数一下自己现在用了几步、几个活性成分（访谈的 214 位敏感肌用户平均是 7.2 步、3 到 4 个活性成分，叠加带来的不是效果累加而是风险累加）；换季前两周开始简化步骤；看成分表时把注意力从「有没有」转到「配比」。
"""


# ============================================================
#  写入
# ============================================================

def _reset(db) -> None:
    """清空全部业务表（保留表结构）。截图前想要确定起点时用。

    ⚠️ 必须按「库里真实存在的表」来删，不能直接用 `Base.metadata.sorted_tables`：
    模型层保留了若干**已并表的历史模型**（如 `BrowserStudioRun` 已并入
    `production_task`），它们的表早被迁移删掉了，照着删会 `no such table`。
    """
    from app.models import Base
    from sqlalchemy import inspect

    # 不动 sys_user：它是登录凭据而不是业务数据。清掉它会让演示库在首次启动
    # 之前无法登录（要靠 main._seed_defaults 再补一次），凭空多一个前置步骤。
    keep = {"alembic_version", "sys_user"}
    existing = set(inspect(db.get_bind()).get_table_names())
    order = [t for t in reversed(Base.metadata.sorted_tables)
             if t.name in existing and t.name not in keep]
    skipped = [t.name for t in Base.metadata.sorted_tables
               if t.name not in existing and t.name not in keep]

    for t in order:
        db.execute(t.delete())
    db.commit()
    print(f"[reset] 已清空 {len(order)} 张表（保留 sys_user）"
          + (f"（跳过 {len(skipped)} 张模型中已并表的旧表）" if skipped else ""))


def _upsert(db, model, match, values=None):
    """按 match 查；命中就更新 values，未命中就用 match+values 创建。

    ⚠️ 刻意把「查找键」与「写入值」拆成两个参数：早期版本用 `**filters, **defaults`
    展开，一旦某个字段同时出现在两边（比如 Persona 的 `name`）就会
    `got multiple values for keyword argument`。这里用 dict 合并（后者覆盖前者），
    重叠字段不再报错。
    """
    obj = db.query(model).filter_by(**match).first()
    if obj:
        for k, v in (values or {}).items():
            setattr(obj, k, v)
        return obj, False
    obj = model(**{**match, **(values or {})})
    db.add(obj)
    db.flush()
    return obj, True


def _ensure_steps(db, run, statuses):
    """按编排规格建步骤行并设置状态（模拟「已经跑到第 N 步」）。"""
    spec = pipeline_svc.spec_of(run)
    for no, key in enumerate(spec["steps"], start=1):
        db.add(BrowserStudioStep(
            run_id=run.id, step_no=no, step_key=key, title=key,
            status=statuses.get(key, "pending"),
        ))
    db.commit()


def _seed_pipeline_demo(db, iid):
    """造一个「看起来真在跑」的批量生产批次：3 选题 × 2 平台 = 6 条运行。

    刻意**复用 `app.services.batch.create`**，不手写 production_task / pipeline_job 的插入：
    这两张表的字段多且还在演进，手写插入会静默造出「能存进去但结构不对」的假数据。

    队列态摊开到 排队中 / 退避重试 / 执行中 / 待确认 / 失败 —— 这样「执行队列」
    「批次进度」「断点续跑」三块一眼就能看到东西（否则截图全是空状态）。
    """
    subjects = [f"{PREFIX}{s}" for s in (
        "换季泛红该怎么选修护面霜",
        "神经酰胺浓度越高越好吗",
        "刷酸翻车后多久能恢复",
    )]
    # 幂等：`batch.create` 每次都会生成新批次号，不加这道闸门重复执行会累积出多个演示批次。
    existing = db.query(ProductionTask).filter(
        ProductionTask.is_deleted == 0,
        ProductionTask.subject.like(PREFIX + "%"),
    ).first()
    if existing is not None:
        print(f"[流水线] 演示批次已存在（运行 #{existing.id}），跳过")
        return

    result = batch_svc.create(db, {
        "industry_id": iid,
        "subjects": subjects,
        "platforms": ["sohu", "zhihu"],
        "skip_duplicates": False,
        "priority": 5,
        "max_attempts": 2,
        "ai_engine": "mock",
        "pipeline_spec": {"steps": pipeline_svc.STEP_ORDER, "max_revise_rounds": 2},
    })
    if not result.get("ok"):
        print(f"[流水线] 跳过：{result.get('error')}")
        return

    batch_id = result["batch_id"]
    runs = (db.query(ProductionTask)
            .filter(ProductionTask.batch_id == batch_id)
            .order_by(ProductionTask.id.asc()).all())
    jobs = {j.run_id: j for j in
            db.query(PipelineJob).filter(PipelineJob.batch_id == batch_id).all()}

    def finish_ok(run, score):
        run.status, run.error, run.geo_score = "await_confirm", "", score
        run.clarified_brief = "选题角与目标读者已明确"
        run.outline_content = "一、问题机理\n二、成分作用\n三、适用边界\n四、可执行建议"
        run.draft_content = SAMPLE_DRAFT
        run.rewrite_content = SAMPLE_DRAFT
        run.final_title = (run.subject or "").replace(PREFIX, "")
        run.final_content = SAMPLE_FINAL
        run.review_result = json.dumps(
            {"gate_pass": True, "geo_score": score, "issues": []}, ensure_ascii=False)
        _ensure_steps(db, run, dict.fromkeys(pipeline_svc.STEP_ORDER, "done"))
        job = jobs[run.id]
        job.status, job.attempts, job.error = "done", 1, ""
        job.started_at = now() - timedelta(minutes=20)
        job.finished_at = now() - timedelta(minutes=12)
        db.commit()

    # ①② 已跑完、停在人工确认闸门（GEO 分一高一低）
    finish_ok(runs[0], 86)
    finish_ok(runs[1], 64)

    # ③ 失败（两次尝试用尽，停在 GEO 强化步）
    r3 = runs[2]
    r3.status = "failed"
    r3.error = "步骤⑥失败：未抽取到终稿（AI 未遵守输出契约）"
    r3.outline_content = "一、为什么刷酸会翻车\n二、屏障急性损伤的三个阶段\n三、恢复期该做什么"
    r3.draft_content = "（初稿正文，约 1200 字）"
    _ensure_steps(db, r3, {"connect": "done", "clarify": "done", "outline": "done",
                           "draft": "done", "depolish": "done", "geo": "failed"})
    j3 = jobs[r3.id]
    j3.status, j3.attempts, j3.max_attempts = "failed", 2, 2
    j3.error, j3.finished_at = r3.error, now()
    db.commit()

    # ④ 执行中（①②③④ 产物就绪，断点在第 ⑤ 步）
    r4 = runs[3]
    r4.status = "running"
    r4.clarified_brief = "选题角：从「浓度崇拜」切入；目标读者：成分党进阶用户"
    r4.outline_content = "一、浓度不是唯一变量\n二、生理比例复配\n三、如何看成分表"
    r4.draft_content = SAMPLE_DRAFT
    r4.rewrite_content = SAMPLE_DRAFT
    _ensure_steps(db, r4, {"connect": "done", "clarify": "done", "outline": "done",
                           "draft": "done", "depolish": "done", "geo": "running"})
    j4 = jobs[r4.id]
    j4.status, j4.attempts, j4.worker = "running", 1, "dispatcher-demo"
    j4.started_at = now() - timedelta(minutes=3)
    db.commit()

    # ⑤ 第一次失败、正在退避等待（最能说明「自动重试」）
    r5 = runs[4]
    r5.status = "created"
    r5.error = "DeepSeek 请求超时"
    r5.clarified_brief = "选题角：换季前的预防窗口；目标读者：敏感肌人群"
    _ensure_steps(db, r5, {"connect": "done", "clarify": "done"})
    j5 = jobs[r5.id]
    j5.status, j5.attempts = "queued", 1
    j5.available_at = now() + timedelta(seconds=45)
    j5.error = "DeepSeek 请求超时（第 1 次失败，稍后自动重试）"
    db.commit()

    # ⑥ 全新排队中。
    # ⚠️ 必须把 available_at 推后：演示实例的调度线程是活的，不设到期时间的话
    # 它会在一两秒内把这条领走，「排队中」这个状态就永远截不到。
    j6 = jobs[runs[5].id]
    j6.status, j6.attempts = "queued", 0
    j6.available_at = now() + timedelta(seconds=120)
    db.commit()

    counts = {}
    for j in db.query(PipelineJob).filter(PipelineJob.batch_id == batch_id).all():
        counts[j.status] = counts.get(j.status, 0) + 1
    print(f"[流水线] 批次 {batch_id}｜{len(runs)} 条运行｜队列态 {json.dumps(counts, ensure_ascii=False)}")


def main() -> None:
    reset = "--reset" in sys.argv

    with SessionLocal() as db:
        if reset:
            _reset(db)

        # —— 行业 ——
        ind, _ = _upsert(
            db, Industry,
            {"name": INDUSTRY_NAME, "is_deleted": 0},
            {"description": "虚构演示行业：敏感肌修护品牌「润初」的内容运营空间", "sort": 0},
        )
        db.commit()
        iid = ind.id
        print(f"[行业] id={iid}  {ind.name}")

        # —— 平台（复用官方预置端点，8 个内容平台 + 官网）——
        seed_platforms(iid, db)
        platforms = {p.name: p.id for p in db.query(Platform).filter(
            Platform.industry_id == iid, Platform.is_deleted == 0).all()}
        print(f"[平台] {len(platforms)} 个")

        # —— 品牌资产 ——
        _upsert(db, BrandAsset,
                {"industry_id": iid, "brand_name": BRAND, "is_deleted": 0},
                {**BRAND_ASSET, "is_default": 1})

        # —— 写作人设 ——
        personas = {}
        for i, p in enumerate(PERSONAS):
            obj, _ = _upsert(db, Persona,
                             {"industry_id": iid, "name": p["name"], "is_deleted": 0},
                             {**p, "sort": i})
            personas[p["name"]] = obj.id
        db.commit()
        print(f"[人设] {len(personas)} 个")

        # —— 账号 ——
        for i, (pname, persona_name, track) in enumerate(ACCOUNTS):
            short = persona_name.split(" · ")[-1]
            _upsert(db, Account,
                    {"industry_id": iid, "account_name": f"{pname} · {short}", "is_deleted": 0},
                    {"content_track": track, "status": 1, "sort": i,
                     "platform_id": platforms.get(pname), "persona_id": personas.get(persona_name)})
        db.commit()
        print(f"[账号] {len(ACCOUNTS)} 个")

        # —— 知识库 ——
        cats = {}
        for i, (name, icon, color, desc) in enumerate(KNOWLEDGE_CATEGORIES):
            obj, _ = _upsert(db, KnowledgeCategory,
                             {"industry_id": iid, "name": name, "is_deleted": 0},
                             {"icon": icon, "color": color, "description": desc, "sort": i})
            cats[name] = obj.id
        for cat_name, title, summary, content, tags, source, imp in KNOWLEDGE_ITEMS:
            _upsert(db, KnowledgeItem,
                    {"industry_id": iid, "title": title, "is_deleted": 0},
                    {"summary": summary, "content": content, "tags": tags,
                     "source": source, "importance": imp, "status": "published",
                     "category_id": cats.get(cat_name)})
        db.commit()
        print(f"[知识库] {len(cats)} 分类 / {len(KNOWLEDGE_ITEMS)} 条")

        # —— 关键词 ——
        groups = {}
        for i, (name, color, icon, desc) in enumerate(KEYWORD_GROUPS):
            obj, _ = _upsert(db, KeywordGroup,
                             {"industry_id": iid, "name": name, "is_deleted": 0},
                             {"color": color, "icon": icon, "description": desc, "sort": i})
            groups[name] = obj.id
        for i, (gname, word, ktype, prio, product, tags) in enumerate(KEYWORDS):
            _upsert(db, Keyword,
                    {"industry_id": iid, "word": word, "is_deleted": 0},
                    {"type": ktype, "priority": prio, "related_product": product,
                     "tags": tags, "sort": i, "group_id": groups.get(gname)})
        db.commit()
        print(f"[关键词] {len(groups)} 组 / {len(KEYWORDS)} 个")

        # —— 提示词库 ——
        for i, (cat, name, content, desc, tags, rating, used) in enumerate(PROMPTS):
            _upsert(db, PromptLibraryItem,
                    {"industry_id": iid, "name": name, "category": cat, "is_deleted": 0},
                    {"content": content, "description": desc, "tags": tags,
                     "rating": rating, "usage_count": used,
                     "variables": json.dumps(
                         sorted({s.split("}}")[0] for s in content.split("{{")[1:]}),
                         ensure_ascii=False),
                     "sort": i})
        db.commit()
        print(f"[提示词库] {len(PROMPTS)} 条")

        # —— 选题 ——
        today = date.today()
        for i, (title, desc, pname, status) in enumerate(TOPICS):
            _upsert(db, Topic,
                    {"industry_id": iid, "title": title, "is_deleted": 0},
                    {"description": desc, "platform_id": platforms.get(pname, 0),
                     "status": status, "plan_date": today + timedelta(days=i * 2), "sort": i})
        db.commit()
        print(f"[选题] {len(TOPICS)} 条")

        # —— 生产任务 ——
        now_dt = datetime.now()
        for i, (title, status, step, pname, persona_name, geo) in enumerate(TASKS):
            done = status == "done"
            _upsert(db, ProductionTask,
                    {"industry_id": iid, "title": title, "is_deleted": 0},
                    {
                        "status": status, "current_step": step,
                        "industry_snapshot": INDUSTRY_NAME,
                        "platform_id": platforms.get(pname, 0), "platform_snapshot": pname,
                        "persona_id": personas.get(persona_name, 0), "persona_snapshot": persona_name,
                        "geo_score": geo,
                        "plan_date": (today + timedelta(days=i)).isoformat(),
                        "outline_content": SAMPLE_OUTLINE if step >= 6 else "",
                        "draft_content": SAMPLE_DRAFT if step >= 7 else "",
                        "rewrite_content": SAMPLE_DRAFT if step >= 8 else "",
                        "safety_report": "GEO 自检通过；未发现绝对化用语与医疗化表述。" if done else "",
                        "final_content": SAMPLE_FINAL if done else "",
                        "final_title": title if done else "",
                        "create_time": now_dt - timedelta(days=len(TASKS) - i),
                        "mode": "manual",
                    })
        db.commit()
        print(f"[生产任务] {len(TASKS)} 条")

        # —— 批量生产 / 流水线演示批次 ——
        _seed_pipeline_demo(db, iid)

        # —— GEO 客户画像 + 意图问题（复用行业预设注册表）——
        intent_router.seed_target_personas(iid, db)
        intent_router.seed_intent_questions(iid, db)
        db.commit()
        n_tp = db.query(TargetPersona).filter(TargetPersona.industry_id == iid,
                                              TargetPersona.is_deleted == 0).count()
        n_iq = db.query(IntentQuestion).filter(IntentQuestion.industry_id == iid,
                                               IntentQuestion.is_deleted == 0).count()
        print(f"[GEO] 目标画像 {n_tp} 个 / 意图问题 {n_iq} 条")

    print(f"\n完成。演示数据已写入：{os.environ.get('APP_DB_PATH') or '（默认开发库）'}")


if __name__ == "__main__":
    main()
