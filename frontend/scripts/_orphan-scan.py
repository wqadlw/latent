"""孤儿扫描：import 了但没用到的绑定 / 模板里用了但没 import 的组件。

用法：python scripts/_orphan-scan.py <file.vue> [more.vue ...]
退出码非 0 表示发现可疑项。

设计要点（都是踩过的坑）：
  1. **不要用 `<template>(.*?)</template>` 抽模板**。根 `<template>` 里常嵌
     `<template #dropdown>` 之类的插槽模板，非贪婪匹配会在第一个内层 `</template>`
     处截断，于是根模板后半段的组件全被判成「没用过」——假红（噪声淹没真问题）。
  2. **不要用 `re.sub` 删掉 import 行再查名字**。删不干净就等于「用过」，
     而漏报孤儿正是最危险的方向（假绿）。
     改为**数出现次数**：标识符总出现次数 vs. 落在 import 语句区间内的次数，
     两者相等 ⇒ 只出现在 import 里 ⇒ 孤儿。不依赖替换是否成功。
  3. **前后用 lookaround 卡边界**（`(?<![\\w$])name(?![\\w$])`），
     否则 `Item` 会命中 `ItemPanel`，把真孤儿盖掉。
     注意别写成 `[\\s:@{...]|^name`：`|` 优先级会让字符类变成独立分支，
     任意空白都能命中，扫描器**永远报不出孤儿**——本项目吃过的假绿之一。
  4. **全局注册的组件要进白名单**。`src/main.js` 把
     `@element-plus/icons-vue` 的**全部**导出 `app.component(key, ...)` 了，
     所以 `<Memo />` 不 import 也能用。不认识这一点就会把 `<Memo>` 误报成缺陷。
     图标名从 node_modules 里现读，跟着版本走，不写死。
"""
import re
import sys
from pathlib import Path

VUE_BUILTINS = {"template", "script", "style", "Transition", "Teleport", "KeepAlive", "Suspense"}

# import 语句（含多行命名导入）。只用来**定位区间**，不做替换。
IMPORT_RE = re.compile(r"import\s+[^;'\"]+?from\s+['\"][^'\"]+['\"]")
# 取被导入的本地绑定名
BINDING_RE = re.compile(r"import\s+([^;'\"]+?)\s+from\s+['\"][^'\"]+['\"]")
COMPONENT_TAG_RE = re.compile(r"<([A-Z][A-Za-z0-9]*)[\s/>]")


def global_component_names(root: Path | None = None) -> set[str]:
    """全局注册的组件名（见 src/main.js：Element Plus 图标全量注册）。"""
    base = root or Path(__file__).resolve().parent.parent
    pkg = base / "node_modules/@element-plus/icons-vue/dist/index.js"
    if not pkg.exists():
        return set()
    txt = pkg.read_text(encoding="utf-8", errors="ignore")
    blocks = re.findall(r"export\s*\{(.*?)\}", txt, flags=re.S)
    names: set[str] = set()
    for part in (blocks[-1] if blocks else "").split(","):
        part = part.strip()
        if part:
            names.add(part.split(" as ")[-1].strip())
    return names


GLOBALS = global_component_names()


def strip_comments(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


def _ident_re(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")


def scan(path: Path) -> list[str]:
    src = strip_comments(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    import_spans = [m.span() for m in IMPORT_RE.finditer(src)]

    def only_in_imports(name: str) -> bool:
        hits = [m.start() for m in _ident_re(name).finditer(src)]
        if not hits:
            return False  # 压根没出现，交给别的规则
        return all(any(a <= p < b for a, b in import_spans) for p in hits)

    # ---- 1) import 了但没用到的绑定 ----
    imported: set[str] = set()
    for m in BINDING_RE.finditer(src):
        clause = m.group(1).strip()
        if not clause.startswith("{"):
            head = re.match(r"([A-Za-z_$][\w$]*)", clause)
            if head:
                imported.add(head.group(1))
        for brace in re.finditer(r"\{([^}]*)\}", clause):
            for part in brace.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                alias = part.split(" as ")[-1].strip()
                if alias:
                    imported.add(alias)

    for name in sorted(imported):
        if only_in_imports(name):
            problems.append(f"UNUSED_IMPORT  {name}")

    # ---- 2) 模板里用了但没 import 的组件 ----
    for tag in sorted(set(COMPONENT_TAG_RE.findall(src))):
        if tag in VUE_BUILTINS or tag in GLOBALS:
            continue
        if tag not in imported:
            problems.append(f"UNIMPORTED_COMPONENT  <{tag}>")

    return problems


def main() -> int:
    bad = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        probs = scan(p)
        if probs:
            bad += len(probs)
            print(f"\n{p}:")
            for x in probs:
                print("  " + x)
        else:
            print(f"{p}: ok")
    print(f"\n合计可疑项：{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
