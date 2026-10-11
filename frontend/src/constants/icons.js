/**
 * 分类 / 分组图标单一真源。
 *
 * 「知识库分类」与「关键词分组」共用同一套图标（Keyword 里那句注释
 * 「分组图标（与知识库分类保持一致）」就是这个意图）。但两处各存了一份，
 * 于是**已经漂移**：
 *   - `iconMap`：Knowledge 9 个键（无 Collection），Keyword 10 个键（有 Collection）
 *   - `iconOptions`：Knowledge 8 项，Keyword 9 项
 *   - 两边都**没有**把 `Files` 列进 `iconOptions`，尽管两边的 `iconMap` 都能渲染它
 *
 * 后果是具体可见的：在知识库新建分类时**选不到 Collection 图标**，
 * 而关键词分组却能选；一旦某条分类的 icon 存成 `Collection`，
 * 知识库的 `iconMap['Collection']` 为 undefined，会静默回退成 Folder。
 *
 * 现在收敛为一份：`ICON_OPTIONS` 取并集（两个视图都能选到全部可渲染图标），
 * `iconMap` 覆盖全部可渲染图标。新增图标只改这里。
 */
import {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files,
} from '@element-plus/icons-vue'

/** 图标名 → 组件。key 必须覆盖 ICON_OPTIONS 的每一项。 */
export const ICON_MAP = {
  Folder, MagicStick, Document, Reading, Notebook, Box, ChatDotRound, Flag, Collection, Files,
}

/** 供下拉框选择的可选图标名（与 ICON_MAP 的键一一对应）。 */
export const ICON_OPTIONS = [
  'Folder', 'MagicStick', 'Document', 'Reading', 'Notebook',
  'Box', 'ChatDotRound', 'Flag', 'Collection', 'Files',
]

/** 取图标组件；未知图标名回退 Folder。 */
export function iconOf(name) {
  return ICON_MAP[name] || Folder
}
