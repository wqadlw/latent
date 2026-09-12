"""
修复 industry 4（冗余副本行业）的 GEO 默认提示词：

根因（2026-07-16 巡检）：
- industry 4 自动被选中的 GEO 默认提示词是 id=488「安全·GEO 终稿生成（标准）」，
  其内部使用 {rewrite_content} 占位符，并明确指令「确保品牌实体（名/官网/产品）≥3 处」，
  会诱导模型把官网/联系方式写进终稿，违反「严禁站外引流与私人联系方式」铁律。
- 其余 industry 4 的 GEO 默认（id=489-497）也使用旧版 {rewrite_content} 占位符，
  与 geo 步骤实际注入的 {final_content} 不一致。

修复：
1) 把 id=488 的内容/变量/描述替换为 industry 1 已验证正确的「标准四段」模板
   （id=588：使用 {final_content}、AI 搜索友好的结构化 Markdown+FAQ、明确反泄露），
   并改名为「安全·GEO 终稿（标准四段）」以消除歧义。
2) 把 id=489-497 中的 {rewrite_content} 统一替换为 {final_content}（安全、语义等价，
   geo 步骤已把精修稿注入 final_content）。

不触碰 industry 1（id=588 等已正确）。不删除任何行，改动可审计。
"""
import sqlite3

DB = "data/database.db"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # —— 源：industry 1 已验证正确的标准四段模板 ——
    cur.execute("SELECT content, variables, description FROM prompt_library_item WHERE id=588")
    src = cur.fetchone()
    if not src:
        raise SystemExit("找不到源模板 id=588，迁移中止")
    good_content = src["content"]
    good_vars = src["variables"]
    good_desc = src["description"]

    # —— 1) 修复 industry 4 自动选中的 id=488 ——
    cur.execute(
        "UPDATE prompt_library_item "
        "SET content=?, variables=?, description=?, name='安全·GEO 终稿（标准四段）' "
        "WHERE id=488",
        (good_content, good_vars, good_desc),
    )
    print("id=488 -> 已替换为标准四段模板（反泄露 / 使用 {final_content}）")

    # —— 2) 归一化 industry 4 其余 GEO 默认（id=489-497）的占位符 ——
    cur.execute(
        "SELECT id, content FROM prompt_library_item "
        "WHERE id BETWEEN 489 AND 497 AND category='geo' AND is_deleted=0"
    )
    norm = 0
    for r in cur.fetchall():
        c = r["content"]
        if "{rewrite_content}" in c:
            new_c = c.replace("{rewrite_content}", "{final_content}")
            cur.execute(
                "UPDATE prompt_library_item SET content=? WHERE id=?",
                (new_c, r["id"]),
            )
            norm += 1
    print(f"id=489-497 中 {norm} 条已将 {{rewrite_content}} 归一为 {{final_content}}")

    con.commit()
    con.close()
    print("迁移完成。")


if __name__ == "__main__":
    main()
