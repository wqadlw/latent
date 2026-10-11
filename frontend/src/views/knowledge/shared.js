/**
 * 知识库面板之间共用的小工具。
 *
 * 拆出 ItemPanel / DetailDrawer / CategoryPanel 之后，「解析标签串」「按 id 找分类名/色」
 * 这三件事被两个以上组件同时需要。放进 `utils/` 也不合适 —— 它们只服务知识库的
 * 数据形状（tags 用中英文逗号/顿号/空格分隔；分类名缺省叫「未分类」；无分类用灰）。
 * 所以放在本目录，和它的使用者待在一起。
 */
import { nameById } from '../../utils/lookup'

/** 「敏感肌, 防晒、护理」→ ['敏感肌','防晒','护理'] */
export function parseTags(tags) {
  if (!tags) return []
  return String(tags).split(/[,，、\s]+/).filter(Boolean)
}

/** 分类 id → 名称；找不到回退「未分类」。 */
export function categoryNameOf(categories, id) {
  return nameById(categories, id, 'name', '未分类')
}

/** 分类 id → 主题色；找不到回退中性灰。 */
export function categoryColorOf(categories, id) {
  const hit = (categories || []).find((c) => c && c.id === id)
  return (hit && hit.color) || '#94a3b8'
}
