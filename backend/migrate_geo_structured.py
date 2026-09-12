"""一次性迁移：把 geo 默认提示词升级为「AI 搜索友好的结构化 Markdown 输出」。

仅对内容中仍含旧文案的 geo 默认提示词做定向替换，不影响用户已自定义的内容。
"""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "database.db")

OLD1 = "5. 结构清晰：# / ## 层级分明，每节一个中心，利于大模型摘录。"
NEW1 = ("5. 结构清晰（AI 搜索友好）：正文用 **Markdown 结构化排版** —— 用 # / ## 标题分层、"
        "要点用 - 列表、关键实体与品牌名用 **加粗**、并单独设一个「常见问题 FAQ」小节用疑问式"
        "小标题直接回答客户会问 AI 的问题，便于 AI 检索、摘要与引用。")
OLD2 = "（完整最终正文：合规无夸大、品牌信号自然、呼应{expected_recommendation}、对{intent_question}给出可信回答）"
NEW2 = ("（完整最终正文，用 AI 搜索友好的结构化 Markdown 排版：含 # / ## 标题分层、- 列表、"
        "**加粗**关键实体，以及单独一个「常见问题 FAQ」小节用疑问式小标题直接作答；"
        "合规无夸大、品牌信号自然、呼应{expected_recommendation}、对{intent_question}给出可信回答）")

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, content FROM prompt_library_item WHERE category='geo' AND is_default=1")
rows = cur.fetchall()
updated = 0
for rid, content in rows:
    if OLD1 in content or OLD2 in content:
        nc = content.replace(OLD1, NEW1).replace(OLD2, NEW2)
        cur.execute("UPDATE prompt_library_item SET content=? WHERE id=?", (nc, rid))
        updated += 1
conn.commit()
conn.close()
print(f"已更新 {updated} 条 geo 默认提示词为结构化 Markdown 输出")
