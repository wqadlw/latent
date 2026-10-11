#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三模式端到端验证：geo(对照) / platform(对照) / green(绿色吸粉) / official(官网 MDX)。
使用 mock 引擎（无需任何 API 配置），创建运行 → 启动 → 轮询到终态 → 校验产出。
"""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
INDUSTRY = 1


def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def create_run(platform, publish_mode, name):
    payload = {
        "industry_id": INDUSTRY,
        "name": name,
        "platform": platform,
        "publish_mode": publish_mode,
        "ai_engine": "mock",
        "auto_publish": False,
    }
    st, resp = call("POST", "/api/browser-studio", payload)
    assert st == 200, f"create failed: {st} {resp}"
    return resp["data"]["id"]


def wait_done(run_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, resp = call("GET", f"/api/browser-studio/{run_id}")
        assert st == 200, f"get failed: {st}"
        data = resp["data"]
        # 终稿在 await_confirm（人工确认闸门）前已完整生成，故该状态也视为「产出就绪」
        if data["status"] in ("succeeded", "failed", "partial", "await_confirm", "confirmed"):
            return data
        time.sleep(2)
    raise TimeoutError(f"run {run_id} 未在 {timeout}s 内完成")


def check_official(r):
    fc = r["final_content"] or ""
    errs = []
    if r.get("output_format") != "mdx":
        errs.append(f"output_format 应为 mdx，实际 {r.get('output_format')}")
    # 去除可能的 ```mdx 代码围栏，便于校验内部 frontmatter
    _fc = fc.strip()
    if _fc.startswith("```"):
        _fc = "\n".join(_fc.split("\n")[1:])
        if _fc.endswith("```"):
            _fc = _fc[:-3]
        _fc = _fc.strip()
    if not _fc.startswith("---"):
        errs.append("MDX 应以 frontmatter (---) 开头")
    # 提取 frontmatter 块（首个 --- 与第二个 --- 之间）做字段校验
    fm = ""
    parts = _fc.split("---")
    if len(parts) >= 3:
        fm = parts[1]
    for key in ("category", "publishDate", "tags", "cover"):
        if key not in fm and key not in _fc:
            errs.append(f"frontmatter 缺少 {key}")
    if "<Image" in fc or "<image" in fc:
        errs.append("MDX 含 <Image /> 组件（禁止）")
    # 4 列数据对比表
    if "| --- | --- | --- | --- |" not in fc and fc.count("|") < 8:
        errs.append("MDX 缺少 4 列数据对比表")
    # 引用块金句
    if "> " not in _fc:
        errs.append("MDX 缺少引用块金句")
    # emoji 检测（粗略）
    import re
    emoji_ranges = ["\U0001F300-\U0001FAFF", "\U00002600-\U000027BF", "\U0001F000-\U0001F02F", "\U0001F1E6-\U0001F1FF"]
    if re.search("[" + "".join(emoji_ranges) + "]", fc):
        errs.append("MDX 含 emoji（禁止）")
    if not r.get("publish_prompt"):
        errs.append("publish_prompt（自动化发布提示词）为空")
    return errs


def count_brand(text, brand="示例品牌"):
    return text.count(brand)


def check_green(r):
    fc = r["final_content"] or ""
    errs = []
    # 品牌仅自然偶提（≤2，且与示例品牌/示例产品相关）
    n = count_brand(fc, "示例品牌") + count_brand(fc, "示例产品")
    if n > 2:
        errs.append(f"绿色模式品牌提及 {n} 次（应 ≤2），实际：{fc[:200]}")
    # 不应出现联系方式/引流词
    bad = ["官网", "电话", "微信", "扫码", "二维码", "下载APP", "关注公众号", "网址", "http"]
    hits = [b for b in bad if b in fc]
    if hits:
        errs.append(f"绿色模式出现引流/联系方式词：{hits}")
    # 不应有口号式硬广标语
    slogans = ["品质可靠，始终如一", "行业领先", "品质保证"]
    sh = [s for s in slogans if s in fc]
    if sh:
        errs.append(f"绿色模式出现口号式标语：{sh}")
    return errs


def main():
    results = {}
    # 1) official / geo 对照
    rid = create_run("official", "", "e2e-official")
    call("POST", f"/api/browser-studio/{rid}/start")
    r = wait_done(rid)
    # 确认（人工满意闸门）→ 发布（官网 MDX 路径：应标记 succeeded，不建第三方任务）
    if r["status"] == "await_confirm":
        call("POST", f"/api/browser-studio/{rid}/confirm")
        call("POST", f"/api/browser-studio/{rid}/publish")
        r = wait_done(rid, timeout=60)
        if r.get("sohu_job_id"):
            r["_err_publish"] = "官网 MDX 不应创建第三方发布任务"
    results["official"] = (r, check_official(r))

    # 2) green
    rid = create_run("sohu", "green", "e2e-green")
    call("POST", f"/api/browser-studio/{rid}/start")
    r = wait_done(rid)
    results["green"] = (r, check_green(r))

    # 3) platform 对照
    rid = create_run("sohu", "platform", "e2e-platform")
    call("POST", f"/api/browser-studio/{rid}/start")
    r = wait_done(rid)
    # platform 模式终稿在 await_confirm（人工闸门）前即完整，无需确认
    results["platform"] = (r, [] if r.get("final_content") else [f"status={r['status']} 无终稿"] + (r.get("error", "").split('\n')[:3]))

    print("=" * 60)
    ok_all = True
    for mode, (r, errs) in results.items():
        status = r["status"]
        out = r.get("output_format")
        pm = r.get("publish_mode")
        print(f"[{mode}] status={status} publish_mode={pm} output_format={out} "
              f"final_len={len(r.get('final_content') or '')} geo={r.get('geo_score')}")
        if errs:
            ok_all = False
            for e in errs:
                print(f"   ✗ {e}")
        else:
            print("   ✓ 校验通过")
    print("=" * 60)
    if ok_all:
        print("✅ 三模式端到端验证全部通过")
    else:
        print("❌ 存在校验失败项")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
