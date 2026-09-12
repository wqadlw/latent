# -*- coding: utf-8 -*-
"""端到端验证：通过真实 API 跑 mock 流水线，确认 platform 模式产出过审成稿。"""
import json, time, urllib.request, urllib.error, re

BASE = "http://127.0.0.1:8765"
BRAND = "示例品牌科技有限公司"
INDUSTRY = 1

def post(path, data):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())

def run_pipeline(mode):
    print(f"\n========== 创建并运行 {mode} 模式 run ==========")
    payload = {
        "industry_id": INDUSTRY,
        "name": f"双模式验证-{mode}",
        "subject": "食品厂真空系统改造避坑指南",
        "platform": "sohu",
        "ai_engine": "mock",
        "publish_mode": mode,
        "auto_publish": False,
    }
    res = post("/api/browser-studio", payload)
    rid = res["data"]["id"]
    print(f"  run id = {rid}, publish_mode = {res['data']['publish_mode']}")
    post(f"/api/browser-studio/{rid}/start", {})
    # 轮询
    for _ in range(60):
        time.sleep(2)
        r = get(f"/api/browser-studio/{rid}")
        st = r["data"]["status"]
        if st in ("await_confirm", "failed"):
            break
    print(f"  最终状态 = {st}")
    if st == "failed":
        print(f"  错误：{r['data'].get('error','')}")
    return r["data"]

def check_platform_compliance_like(text, title):
    """复刻 rule_checker.check_platform_compliance 的本地判定（避免重复 import 依赖）。"""
    SELF_PRAISE = ["行业领先","遥遥领先","首屈一指","当之无愧","品质可靠","始终如一",
                   "无可替代","独一无二","行业标杆","最值得信赖","傲视群雄","国际领先",
                   "国内领先","技术领先","行业第一"]
    END_PROMO = ["了解更多","欢迎咨询","欢迎了解","联系我们","加微信","扫码","关注我们",
                 "点击了解","立即了解","欢迎联系","了解更多详情","点击查看"]
    issues = []
    if BRAND in title:
        issues.append("标题含品牌名")
    bc = len(re.findall(re.escape(BRAND), text))
    if bc > 2:
        issues.append(f"品牌名出现 {bc} 次(>2)")
    sp = [w for w in SELF_PRAISE if w in text]
    if sp:
        issues.append(f"自夸词：{sp}")
    tail = text[-260:]
    if BRAND in tail and any(w in tail for w in END_PROMO):
        issues.append("文末品牌推广")
    return len(issues) == 0, bc, issues

for mode in ("platform", "geo"):
    data = run_pipeline(mode)
    title = data.get("final_title") or ""
    content = data.get("final_content") or ""
    print(f"  [终稿标题] {title}")
    print(f"  [终稿字数] {len(content)}")
    rev = data.get("review_result") or {}
    pc = rev.get("platform_compliance")
    gate = rev.get("gate_pass")
    print(f"  [评审 gate_pass] {gate}  [platform_compliance] {pc}")
    ok, bc, issues = check_platform_compliance_like(content, title)
    print(f"  [本地复核 品牌次数] {bc}  问题={issues}")
    if mode == "platform":
        assert ok, f"platform 模式终稿未通过平台合规复核：{issues}"
        assert BRAND not in title, "platform 模式标题不应含品牌名"
        assert bc <= 2, f"platform 模式品牌名应≤2次，实际 {bc}"
        assert "AI 辅助创作" in content or "AIGC" in content, "platform 模式文末应带 AIGC 声明"
        print("  ✅ PLATFORM 模式：标题无品牌、品牌≤2次、带 AIGC 声明、通过平台合规闸门")
    else:
        assert bc >= 3, f"geo 模式品牌名应≥3次，实际 {bc}"
        print("  ✅ GEO 模式：保持强品牌成稿（不被平台闸门阻塞）")

print("\n🎉 端到端双模式验证全部通过")
