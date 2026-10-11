# GEOFlow 借鉴评估 & 阶段 B（GEO 能力深化）实施方案

> 参照对象：`https://github.com/yaojingang/GEOFlow`（Laravel 8.3+ / AGPL-3.0）
> 本地副本：`D:/AAA/_ref_GEOFlow`
> 评估日期：2026-10-10

---

## 一、GEOFlow 是什么

开源的企业级 GEO 运营系统。体量：

| 指标 | 数值 |
|---|---|
| PHP 文件 | 940 |
| `app/Services` 行数 | ~46,347 |
| `app/Services/GeoFlow` 类数 | 138 |
| 数据库迁移 | 175 |
| 测试文件 | 386 |
| 仓库体积 | 110 MB |

**它的定位比我们大一圈**：我们做的是「内容生产 + 发布」的工具链，它做的是「内容生产 + 发布 + AI 可见性度量 + 质量闸门 + 多站点托管 + Agent 分发」的完整运营平台。

结论先给：**它的工程分层不值得抄（138 个 Service 类是过度工程），但它的 6 个业务能力模型值得抄，而且抄过来能直接补上我们最致命的三个洞。**

---

## 二、我们现在的三个洞

先把家底盘清楚，才知道该借什么。

### 洞 1：质检是「二值」的，不是「决策」

现状 `backend/app/services/rule_checker.py`（378 行）：

```python
overall_pass = compliance["pass"] and ai_seo["pass"] and anti_ai["pass"] and fmt["pass"]
```

- 纯本地正则 + 词表，**不调用任何 AI**（这是设计边界，不打算改）
- 输出只有 `True/False`
- `geo_score.py`（601 行）有 0-100 分 + 70 分闸门 + 双信任诊断，但它和 `rule_checker` 是**两套并行的独立判定**，没有统一裁决

**问题**：一篇文章「72 分、有 2 个未验证的数字断言」，现在只能报 pass。没有任何机制说「这个数字没有出处，不能发」。

### 洞 2：AI 可见性监测是「手工粘贴」的

现状 `backend/app/routers/geo_monitor.py`（608 行）：

- `GeoMonitor` = 一条监测任务（target_query + brand_name + platforms）
- `GeoMonitorReply` = 用户**手工把 AI 的回答复制粘贴进来**，`_parse_ai_reply()` 本地正则抽出 6 个指标（mentioned / mention_count / citation_length / sentiment / valuable_positive / recommended）
- 没有任何来源引用追踪（**AI 回答里引用了哪些网站，我们完全不知道**）
- 没有时间序列、没有并发探测、没有自动化

**问题**：这是整个系统里最应该自动化的一环，却是纯人工。而且丢掉了 GEO 最有价值的数据——**信源引用**。

### 洞 3：没有「发布 → 收录」的回流

- `EffectRecord` 是手工录入的 rank 记录
- 没有爬虫日志 → 不知道 AI 到底有没有来爬我们的文章
- 没有 `llms.txt` / `sitemap.xml` 生成（我们已经产出 MDX，但没有把 MDX 暴露给 AI 抓取）
- 选题 → 写作 → 发布 → 收录 → 排名 → 回流选题的闭环，目前断在「发布」之后

---

## 三、借什么（6 项，按优先级）

### 借 #1｜AI 质检闸门 —— 把二值 pass 升级为三态决策 ⭐最高优先

**GEOFlow 怎么做**

`ArticleAiQualityInspectionService.php`（3993 行）+ `ArticleAiQualityGate.php`（529 行）。核心链路：

```
claim 抽取（从文章里抽出可验证断言）
  → 证据检索（逐条 claim 去知识库找证据，命中则绑定 citation_key）
  → 打分（0-100）
  → 闸门裁决
```

**三态决策**（这是我们最该抄的一行）：

| 决策 | 触发条件 |
|---|---|
| `passed` | 达到通过线（默认 85），且无 hard blocker、无重要不确定项、无无效证据引用 |
| `needs_review` | 分数未达通过线，或证据覆盖不足，或模型输出被截断 |
| `blocked` | 存在已确认 hard blocker，或总分低于人工放行线（默认 70） |

阈值：**自动通过 85 / 人工放行最低 70**。

**超时抽样兜底**（关键工程细节）：
- `deadline_seconds=180`，`sampled_fallback_seconds=45`——超过 45 秒还没跑完全文，自动切抽样模式
- `sampled_max_characters=6000`，`sampled_max_ranges=12`（12 个不重叠区间）
- 抽样结果标记 `inspection_scope=fallback_sampled`，可以走自动放行，但有独立开关 `SAMPLED_AUTO_RELEASE_ENABLED` 可一键关掉

**熔断器**：
- `CIRCUIT_CONSECUTIVE_FAILURES=5`、`CIRCUIT_SAMPLE_SIZE=10`、`CIRCUIT_FAILURE_PERCENT=50`、`CIRCUIT_OPEN_SECONDS=60`

**证据缓存**：`EVIDENCE_CACHE_TTL_SECONDS=86400`（1 天）

**我们借什么**

| 借 | 说明 | 落点 |
|---|---|---|
| 三态决策 | `passed` / `needs_review` / `blocked` 替代 `overall_pass` 布尔 | 新增 `services/quality_gate.py` |
| claim 抽取 + 证据核对 | 从正文抽出「数字断言 / 功效断言 / 资质断言」，逐条去 `KnowledgeItem` 找证据；无证据的标 `unverified` | 新增 `services/claim_extractor.py` |
| 硬闸门 vs 软扣分分离 | 合规类（违禁词/联系方式）→ hard blocker 直接 blocked；GEO 分/心智温度 → 软扣分影响分数 | 改造 `rule_checker.run_full_check()` 返回值 |
| 抽样兜底 | 长文质检超时按区间抽样，标记 `fallback_sampled` | `quality_gate.py` 内 |
| 熔断器 | AI 质检连续失败自动打开 60 秒 | 复用 `llm_scheduler.py` 加计数器 |

**不借**：它的 rollout / 灰度 / 影子模式（`PRINCIPLE_V2_PERCENT`、`SHADOW_V2_PERCENT`、`FAST_V2_PERCENT`）——那是给多租户 SaaS 做算法灰度用的，我们单租户不需要。

**统一裁决**（我们比它更需要的一点）：把 `rule_checker` + `geo_score` + `claim 证据核对` 三路结果汇总成一个 `QualityVerdict`：

```python
{
  "decision": "passed" | "needs_review" | "blocked",
  "score": 78.5,
  "hard_blockers": [...],     # 直接 blocked
  "soft_issues": [...],       # 扣分项
  "unverified_claims": [...], # 无证据断言
  "evidence_coverage": 0.75,  # 证据覆盖率
  "inspection_scope": "full" | "fallback_sampled",
  "thresholds": {"auto_pass": 85, "manual_floor": 70}
}
```

---

### 借 #2｜AI 可见性采集 —— 把手工粘贴升级为自动探测 ⭐最高优先

**GEOFlow 怎么做**

两张表 + 一个 service：

```php
// AiVisibilityRun：一次探测 = 一个 Run
keyword, prompt, provider_type, provider_key, model_id, status,
answer_text, latency_ms, usage_json, analysis_json,
raw_request_json, raw_response_json, parent_run_id

// AiVisibilitySource：Run 下挂 N 条被引用的信源
source_type, citation_key, title, url, domain, site_name,
snippet, summary, content_excerpt, published_at,
rank, rank_score, authority_level, metadata_json
```

**三种 provider**（`AiVisibilityService.php`，487 行）：

| provider_type | 干什么 |
|---|---|
| `doubao_ark_responses` | 豆包带联网检索的回答（能看到 AI 引用了谁） |
| `doubao_search_custom` | 豆包信源搜索（纯信源，不生成回答） |
| `deepseek_analysis` | DeepSeek 对信源做分析，产出「该建哪些页面」的建议 |
| `competitor_detection` | 从 answer_text 里抽竞品（`parent_run_id` 挂回原 Run） |

还有一个两段式编排 `runDoubaoSearchThenDeepSeekAnalysis()`：**先搜信源 → 再把信源喂给分析模型**。这个链路很聪明——信源是客观的，分析是主观的，分开存。

**工程细节**：
- `AiVisibilityResultNormalizer.php`（304 行）：不同 provider 返回格式差异巨大，统一归一化成 `AiVisibilityResult`
- prompt 归一化 + `resolvePrompt()` 默认模板：保证同一个 keyword 跨时间可比
- 重试：`maxProviderAttempts` + `isTransientProviderFailure()`（只重试 429/5xx/超时）
- 稳定错误码：`ai_provider_auth_failed` / `ai_provider_request_failed` / `ai_config_access_revoked` / `ai_result_discarded` / `ai_model_unavailable`
- 调用锁 `acquireForInvocation(model_id, 300)`：防止同一模型并发打爆
- 配额预留 → 成功结算 / 失败释放（`reserveModel` → `recordModelSuccess` / `releaseModel`）

**我们借什么**

| 借 | 落点 |
|---|---|
| Run / Source 两层数据模型 | 新增 `geo_visibility_run` + `geo_visibility_source` 两张表 |
| provider 适配器抽象 | `services/visibility/` 下 `base.py` + `doubao.py` / `deepseek.py` / `kimi.py` / `tongyi.py` |
| 两段式：先搜信源再分析 | `services/visibility/collector.py` |
| prompt 固定模板保证可比 | 落库时把 prompt 一起存，跨时间对比时按 prompt 分组 |
| 稳定错误码 + 只重试瞬时失败 | 复用现有 `llm.py` 的重试逻辑，补错误码归一化 |
| 并发探测 | 一问 × N 引擎，用现有 `llm_scheduler.py` 线程池 |

**对现有 `geo_monitor` 的处置**：
- `GeoMonitor` / `GeoMonitorReply` **保留**（手工粘贴通道不能删，很多 AI 平台没有 API）
- 新增自动采集通道，两条通道**共用同一套指标解析**（把 `_parse_ai_reply` 抽成公共函数）
- `GeoMonitorReply` 加 `run_id` 外键，手工粘贴的也可以关联到自动 Run

---

### 借 #3｜可见性分析看板 —— KPI 定义直接抄

**GEOFlow 的 6 个 KPI**（`AiVisibilityAnalyticsService.php`，1022 行）：

| KPI | 定义 |
|---|---|
| `brand_visibility` | 品牌可见率 = AI 回答里提到品牌，**或**引用信源里前 3 名有品牌站 |
| `top1_rate` | 品牌信源排第 1 的比例 |
| `top3_rate` | 品牌信源排前 3 的比例 |
| `positive_rate` | 正面情感比例 |
| `negative_rate` | 负面情感比例 |
| `sentiment_score` | 情感分（-1 ~ 1） |

**关键定义细节**（值得逐字抄）：

```php
// 品牌「可见」的判定不是简单的字符串包含，而是两路 OR：
'brand_visible' => $answerMentionsBrand                       // 回答正文提到品牌
    || $brandSourceRanks->contains(fn($rank) => $rank <= 3),  // 或引用的信源前 3 有品牌站
```

这个判定很重要——**AI 回答里没提你，但引用了你的站，这也算可见**。

**四个分析面板**：

| 面板 | 价值 |
|---|---|
| `trend` | 日粒度趋势（品牌可见率 / top1 / top3 / 情感分） |
| `termCloud` | 从 answer_text + sources 抽词云 |
| `sourcePreferences` ⭐ | **哪些域名被 AI 偏爱引用**——直接告诉你「该去哪些站点铺内容」 |
| `attentionSources` | 高关注度信源榜 |
| `sourceAction` | 对每个信源给行动建议（自建 / 投放 / 合作） |

**采样**：`DAILY_SAMPLE_TARGET = 5`——每天每关键词最多采 5 个 Run 做 KPI，避免算力爆炸。

**我们借什么**

- 6 个 KPI 定义照抄
- 日粒度趋势（我们已有 `EffectRecord.record_date`，扩展即可）
- **`sourcePreferences` 信源偏好榜**——这是本次借过来**最有商业价值**的一个面板
- `DAILY_SAMPLE_TARGET` 采样策略

**我们比它多做的一点**：把信源偏好榜接回选题。看到「AI 在回答『真空泵怎么选』时引用了 A/B/C 三个站点」，就应该自动生成一批「对标 A 站那篇的选题」。

---

### 借 #4｜竞品检测

**GEOFlow 怎么做**

- `AiVisibilityCompetitor`（竞品库）+ `AiVisibilityCompetitorDetection`（检测结果）
- `AiVisibilityCompetitorParser.php`（38 行，很短）
- `runCompetitorDetection()`：把 `answer_text` 喂给 DeepSeek，让它抽出提到的竞品名
- 用 `parent_run_id` 挂回原 Run，形成「一次探测 → 主结果 + 竞品检测」的树

**我们借什么**

- 2 张表 + 1 个 parser（很轻）
- 看板加一块「竞品提及率对比」：我们 vs 竞品在同一批关键词上的提及率
- 竞品名可以从 `Industry` / 品牌配置里预置，也可以让 AI 抽

**优先级**：中。要先把 #2 #3 做完才有数据喂给它。

---

### 借 #5｜AI 爬虫流量分类 + llms.txt 生成 ⭐高性价比

**GEOFlow 怎么做**

`app/Support/Analytics/TrafficClassifier.php`——三段式纯正则分类，零依赖：

```php
aiBotPatterns():      gptbot, chatgpt-user, chatgpt, oai-searchbot, openai,
                      claudebot, claude-searchbot, claude-user, anthropic,
                      perplexitybot, perplexity-user, perplexity, ccbot,
                      google-extended, applebot-extended, bytespider,
                      meta-externalagent, cohere-ai, youbot
searchBotPatterns():  googlebot, bingbot, baiduspider, yandexbot, duckduckbot,
                      sogou, slurp, 360spider, semrushbot, ahrefsbot, ...
otherBotPatterns():   ...
```

分类结果：`human` / `search_bot` / `ai_bot` / `other_bot` / `unknown`

`llms.txt` / `robots.txt` / `sitemap.xml` / `sitemap.txt` 从发布状态 + 索引开关 + permalink 自动生成。

**我们借什么**

| 借 | 落点 | 成本 |
|---|---|---|
| 爬虫分类器（词表直接抄） | 新增 `services/crawler_classifier.py` | 极小 |
| 爬虫日志采集 | FastAPI 中间件记录 UA + 分类 + 路径 | 小 |
| `llms.txt` 生成 | 从已发布的官网 MDX 内容生成 | 小 |
| `sitemap.xml` 生成 | 同上 | 小 |

**为什么性价比最高**：我们**已经在产出官网 MDX**（`output_format=mdx`），但从来没有把这个内容暴露给 AI 抓取。加一个 `llms.txt` + `sitemap.xml` 端点，配合爬虫日志，就能第一次**实证**「我们发的文章到底有没有被 AI 爬」。

这一步是洞 3（回流闭环）的地基。

---

### 借 #6｜Agent Skill 打包分发 —— 把能力变成可分发资产

**GEOFlow 怎么做**

`.agents/skills/geoflow/` 是一套完整的 Agent Skill 包：

```
manifest.json              # 能力清单
SKILL.md                   # 给 Agent 看的说明
agents/interface.yaml      # 接口定义
agents/openai.yaml         # OpenAI 适配
references/                # 17 份参考文档
scripts/                   # 可执行脚本
evals/                     # 评测集（rubric.md / failure_cases.md / trigger_cases.json）
security/network_policy.json      # 网络白名单
security/permission_policy.json   # 权限策略
templates/
examples/
```

多平台适配：`openai` / `claude` / `agent-skills` / `vscode` / `generic`

**我们借什么**

把「找真空」的 GEO 工作流（选题 → 写作 → 质检 → 发布）打包成一个 Agent Skill，让用户能在 Claude / Cursor / WorkBuddy 里直接调用我们的服务。

**这是产品化路径，不是技术刚需。** 建议放到阶段 B 之后，或者等阶段 D 完成后单独做。

---

## 四、明确不借的（避免踩坑）

| 不借 | 原因 |
|---|---|
| 138 个 Service 类的分层 | 过度工程。我们 12 个 service 覆盖同样业务，拆分粒度已经合适 |
| pgvector 混合检索 | 我们知识库规模远不到需要向量的程度。SQLite LIKE + 关键词倒排完全够 |
| Horizon + 4 个队列隔离 | 单机 SQLite，线程池 + 任务状态机就够。多队列反而增加部署复杂度 |
| 175 个 migration | 我们是 Alembic 单基线 + 增量，不需要按字段拆那么细 |
| 算法灰度（rollout / shadow / percent） | 多租户 SaaS 的需求，单租户用不上 |
| 配额预留 / 结算体系 | 我们不做多租户计费 |
| Laravel 那套 `Data` DTO + `final class` + 构造器注入 | PHP 的写法，Python 用 dataclass + 依赖注入即可，不必照搬 |

---

## 五、阶段 B 实施方案

按依赖顺序分 4 个包，每包独立可验证。

### B1｜质检闸门升级（改动最小，收益最直接）

**目标**：`rule_checker` 的二值 pass → 三态决策 + 证据核对。

**新增文件**
```
backend/app/services/claim_extractor.py      # claim 抽取（本地正则 + 可选 AI 辅助）
backend/app/services/quality_gate.py         # 统一裁决器
backend/app/services/quality_evidence.py     # 证据检索（去 KnowledgeItem 找）
backend/app/services/circuit_breaker.py      # 熔断器（可复用）
```

**新增表**（1 张）
```
quality_check
  id, task_id, content_hash, decision(passed/needs_review/blocked),
  score, inspection_scope(full/fallback_sampled),
  hard_blockers_json, soft_issues_json, unverified_claims_json,
  evidence_coverage, rule_result_json, geo_result_json, mind_result_json,
  prompt_version, algorithm_version, latency_ms, create_time
```

**改造点**
- `rule_checker.run_full_check()` → 返回 `hard_blockers` / `soft_issues` 分离的结构
- `production.py` 任务流：质检结果从 `bool` 改为读 `decision`
- 前端质检卡片：三态配色（绿 / 黄 / 红）+ 未验证断言清单

**验收**：一篇文章能返回完整 `QualityVerdict`；无证据的数字断言能被标出；超长文章超时能走抽样且标记正确。

---

### B2｜可见性自动采集

**目标**：`geo_monitor` 从手工粘贴 → 自动并发探测 + 信源落库。

**新增文件**
```
backend/app/services/visibility/base.py          # Provider 抽象
backend/app/services/visibility/doubao.py        # 豆包（联网）
backend/app/services/visibility/deepseek.py      # DeepSeek 分析
backend/app/services/visibility/collector.py     # 采集编排（先搜信源→再分析）
backend/app/services/visibility/normalizer.py    # 归一化（对应 AiVisibilityResultNormalizer）
backend/app/routers/visibility.py                # 新路由
```

**新增表**（2 张）
```
geo_visibility_run
  id, industry_id, monitor_id(可空), parent_run_id, uuid, keyword, prompt,
  provider_type, provider_key, llm_config_id, model_id, status,
  answer_text, latency_ms, usage_json, analysis_json,
  raw_request_json, raw_response_json, error_code,
  start_time, complete_time, create_time

geo_visibility_source
  id, run_id, source_type, citation_key, title, url, domain, site_name,
  snippet, summary, content_excerpt, published_at,
  rank, rank_score, authority_level, metadata_json
```

**改造点**
- `_parse_ai_reply()` 抽成 `services/visibility/metrics.py`，手工通道和自动通道共用
- `GeoMonitorReply` 加 `run_id` 外键（可空，兼容历史数据）
- 并发：一问 × N 引擎，复用 `llm_scheduler.py`

**验收**：一个关键词能自动跑 3 个引擎，落库 answer_text + 引用信源（domain/rank/url）；失败有稳定错误码。

---

### B3｜分析看板

**目标**：6 个 KPI + 趋势 + 信源偏好榜 + 竞品对比。

**新增文件**
```
backend/app/services/visibility/analytics.py     # KPI 计算（对应 AiVisibilityAnalyticsService）
backend/app/services/visibility/competitor.py    # 竞品检测与解析
frontend/src/views/GeoVisibility.vue             # 看板页
```

**新增表**（2 张）
```
geo_visibility_competitor
  id, industry_id, name, aliases_json, is_self, create_time

geo_visibility_competitor_detection
  id, run_id, competitor_id, mentioned, mention_count, rank, snippet, create_time
```

**KPI 定义**（照抄 GEOFlow）
```
brand_visibility  = 回答提品牌 OR 引用信源前3有品牌站
top1_rate / top3_rate / positive_rate / negative_rate / sentiment_score
采样：每关键词每天最多 5 个 Run
```

**看板四块**
1. KPI 卡片（6 个）
2. 日粒度趋势折线（品牌可见率 / top3 率 / 情感分）
3. **信源偏好榜**（哪些域名被 AI 偏爱引用 + 行动建议）
4. 竞品提及率对比（我们 vs 竞品）

**验收**：看板能显示真实采集数据；信源偏好榜能列出 top 20 域名及引用次数。

---

### B4｜归因闭环

**目标**：发布 → 收录 → 排名 → 回流选题。

**新增文件**
```
backend/app/services/crawler_classifier.py       # 爬虫分类（词表直接抄 GEOFlow）
backend/app/middleware/traffic_log.py            # 爬虫日志中间件
backend/app/services/llms_txt.py                 # llms.txt / sitemap.xml 生成
backend/app/routers/site.py                      # /llms.txt /sitemap.xml 端点
```

**新增表**（1 张）
```
crawler_hit
  id, hit_time, path, user_agent, bot_class(ai_bot/search_bot/other_bot/human/unknown),
  bot_name, ip_hash, content_asset_id(可空)
```

**闭环逻辑**
```
发布（已有）
  → 收录：crawler_hit 里出现 ai_bot 命中该文章 URL
  → 排名：geo_visibility_source 里出现该文章 URL + rank
  → 回流：信源偏好榜 → 自动生成「对标选题」建议
```

**验收**：`/llms.txt` 能正确列出已发布内容；爬虫日志能区分 AI 爬虫与搜索引擎爬虫；能从信源偏好生成选题建议。

---

## 六、优先级与建议

| 包 | 收益 | 工作量 | 建议 |
|---|---|---|---|
| **B1 质检闸门** | 高（直接提升内容质量可控性） | 中 | **先做** |
| **B2 可见性采集** | 高（补上最致命的人工环节） | 大 | **先做** |
| **B5 爬虫分类 + llms.txt** | 高（性价比最高，地基） | 小 | **可插队先做** |
| **B3 分析看板** | 高（依赖 B2） | 中 | B2 之后 |
| **B4 归因闭环** | 中（依赖 B2+B3+B5） | 中 | 最后 |
| **B6 Agent Skill** | 产品化 | 中 | 阶段 D 之后单独做 |

**建议执行顺序**：`B5 → B1 → B2 → B3 → B4`

理由：B5 工作量最小且是 B4 的地基，先做能立刻拿到「AI 有没有来爬」的实证；B1 和 B2 相对独立可以并行；B3 必须等 B2 有数据。

---

## 七、一句话总结

GEOFlow 的**工程分层不值得抄，业务能力模型非常值得抄**。

最该借的三样东西：
1. **三态质检闸门 + claim 证据核对**——把「分数」变成「决策」，把「数字对不对」纳入校验
2. **Run/Source 两层可见性数据模型**——AI 引用了谁，是 GEO 最有价值的数据，我们现在完全没有
3. **AI 爬虫分类 + llms.txt**——零成本拿到「有没有被 AI 爬」的实证，是回流闭环的地基

最不该借的：138 个 Service 类的分层、pgvector、多队列、灰度体系——那是 SaaS 规模的问题，不是我们的问题。
