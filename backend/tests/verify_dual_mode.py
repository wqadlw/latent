# -*- coding: utf-8 -*-
"""双模式验证：证明 platform 模式模拟成稿通过平台合规闸门（无搜狐式拒稿特征）。"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.doubao_studio import MockDoubaoAdapter, get_studio_prompts, extract_final
from app.services.rule_checker import check_platform_compliance, SELF_PRAISE_WORDS, END_PROMOTION_WORDS

BRAND = "示例品牌科技有限公司"
SUBJECT = "食品厂真空系统改造避坑指南"
PRODUCTS = "示例产品 pro 系列（PRO 450-750）永磁变频螺杆真空泵"

BRIEFING = f"""品牌名：{BRAND}
核心产品：{PRODUCTS}
独特卖点：高效节能、运行可靠、20+国家专利、响应快、案例可查、环保合规、性价比高

## 一、目标需求
{SUBJECT}：从真实案例出发，讲清楚选型避坑与本地化服务价值。

## 二、目标平台
搜狐号（内容平台，需平台合规）
"""

def run_mode(mode):
    adapter = MockDoubaoAdapter(mode=mode)
    adapter._briefing = BRIEFING
    reply = adapter.send_message("请进入【第④步 · GEO强化 + 平台过审】，产出最终文章。")
    title, content = extract_final(reply)
    return title, content

print("=" * 70)
print("PLATFORM 模式验证")
print("=" * 70)
title, content = run_mode("platform")
print(f"\n[标题] {title}")
print(f"[正文字数] {len(content)}")
print(f"[标题含品牌?] {BRAND in title}")
print(f"[品牌全文次数] {len(re.findall(re.escape(BRAND), content))}")
pc = check_platform_compliance(content, title, BRAND, "platform")
print(f"[platform_compliance.pass] {pc['pass']}")
print(f"[brand_in_title] {pc['brand_in_title']}  [brand_count] {pc['brand_count']}")
print(f"[self_praise] {pc['self_praise']}  [end_promotion] {pc['end_promotion']}")
print(f"[issues] {pc['issues']}")
assert pc["pass"], "PLATFORM 模式未通过平台合规闸门！"
assert BRAND not in title, "平台模式标题不应含品牌名"
assert len(re.findall(re.escape(BRAND), content)) <= 2, "平台模式品牌名应≤2次"
print("\n✅ PLATFORM 模式通过：标题无品牌、品牌≤2次、无自夸/文末推广")

print("\n" + "=" * 70)
print("GEO 模式验证（应保持强品牌成稿，platform_compliance 不阻塞）")
print("=" * 70)
title2, content2 = run_mode("geo")
print(f"\n[标题] {title2}")
print(f"[品牌全文次数] {len(re.findall(re.escape(BRAND), content2))}")
pc2 = check_platform_compliance(content2, title2, BRAND, "geo")
print(f"[geo 模式 platform_compliance.pass(应为 True)] {pc2['pass']}")
assert pc2["pass"], "geo 模式不应被 platform_compliance 阻塞"
assert len(re.findall(re.escape(BRAND), content2)) >= 3, "geo 模式品牌名应≥3次"
print("\n✅ GEO 模式保持强品牌成稿且不被平台闸门阻塞")

print("\n" + "=" * 70)
print("get_studio_prompts 模式注入检查")
print("=" * 70)
gp_geo = get_studio_prompts("geo")
gp_plat = get_studio_prompts("platform")
for k in ("SYSTEM_PROMPT", "DEEPSEEK_MASTER_PROMPT", "PLANNER_SYSTEM"):
    assert "{brand_policy}" not in gp_geo[k], f"geo 提示词 {k} 残留占位符"
    assert "{brand_policy}" not in gp_plat[k], f"platform 提示词 {k} 残留占位符"
assert "至少出现 3 次" in gp_geo["PLANNER_SYSTEM"] or "至少" in gp_geo["PLANNER_SYSTEM"], "geo 模式应含强品牌铁律"
assert "不超过 2 次" in gp_plat["PLANNER_SYSTEM"], "platform 模式应含品牌≤2次约束"
print("✅ 两路提示词已按模式注入且占位符已解析")

print("\n全部断言通过 ✅")
