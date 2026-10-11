<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  MagicStick, ArrowDown, CopyDocument, Document, Check,
} from '@element-plus/icons-vue'
import { productionApi } from '../../../api'
import { copyText, writeClipboard } from '../../../utils/clipboard'
import StepHeader from '../../../components/production/StepHeader.vue'

// illuState 由父组件持有（属于任务持久化状态），本组件就地修改其字段
// { plan, promptId, style, method }
const props = defineProps({
  options: { type: Object, required: true },
  currentTask: { type: Object, required: true },
  saveDraft: { type: Function, required: true },
  illuState: { type: Object, required: true },
  currentRecommendation: { type: Object, required: true },
  recommendationMethod: { type: String, required: true },
})

const loadingIllu = ref(false)

// 图文混排区块——把配图锚定到文章对应章节位置（封面置顶 + 各章节前插入插图）
const articleBlocks = computed(() => {
  const data = props.illuState.plan
  if (!data || !data.plan || !data.plan.length) return []
  const sections = data.sections || []
  const byAnchor = {}
  data.plan.forEach(p => { byAnchor[p.section_anchor] = p })
  const blocks = []
  if (byAnchor[-1]) blocks.push({ type: 'image', img: byAnchor[-1] })
  sections.forEach((sec, i) => {
    blocks.push({ type: 'text', section: sec })
    if (byAnchor[i]) blocks.push({ type: 'image', img: byAnchor[i] })
  })
  return blocks
})

async function generateIllustration() {
  if (!props.currentTask?.id) return
  loadingIllu.value = true
  try {
    const res = await productionApi.illustrationPlan({
      task_id: props.currentTask.id,
      prompt_id: props.illuState.promptId || null, // 0 表示内置默认
      method: 'both', // 同时产出 AI 提示词与网络关键字
      style: props.illuState.style || null,
      max_inline: 6,
    })
    props.illuState.plan = res.data
    // 立即持久化整包（meta + recommendation + plan）
    props.currentTask.illustration_plan = JSON.stringify(res.data)
    props.illuState.promptId = res.data.prompt_id || 0
    if (res.data.style) props.illuState.style = res.data.style
    await props.saveDraft(true)
    ElMessage.success(props.illuState.method === 'ai'
      ? '配图方案已生成，复制提示词去 AI 生图工具即可'
      : '图片关键字已生成，去免版税图库搜图即可')
  } catch {
    // 错误由拦截器统一提示
  } finally {
    loadingIllu.value = false
  }
}

// 保存配图（含回填的图片链接）
async function saveIllustrations() {
  if (!props.illuState.plan) return
  props.currentTask.illustration_plan = JSON.stringify(props.illuState.plan)
  await props.saveDraft(true)
  ElMessage.success('配图方案已保存')
}

// copyText 已抽到 utils/clipboard.js（全站统一实现）

async function copyItemPrompt(it, mode) {
  let text = ''
  if (mode === 'network') {
    text = '图片关键字：\n' + (it.search_keywords || []).join('、') +
      '\n\n推荐平台：\n' + (it.search_platforms || []).join('；')
  } else {
    text = '文生图提示词（中文）：\n' + (it.ai_prompt || '') +
      '\n\n英文提示词：\n' + (it.ai_prompt_en || '') +
      '\n\n反向词：' + (it.negative_prompt || '') +
      '\n\n建议比例：' + it.aspect_ratio + '（' + it.size + '）'
  }
  if (await writeClipboard(text)) {
    ElMessage.success(mode === 'network' ? '已复制该图关键字' : '已复制该图提示词，可粘贴到生图工具')
  } else {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

async function copyAllIllustration(mode) {
  if (!props.illuState.plan) return
  const text = mode === 'network'
    ? (props.illuState.plan.copy_all_network || '')
    : (props.illuState.plan.copy_all_ai || '')
  if (!text) return
  if (await writeClipboard(text)) {
    ElMessage.success(mode === 'network' ? '已复制全部图片关键字' : '已复制全部文生图提示词')
  } else {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

// 复制「带图位标记的成品文章」——把配图锚定到文章对应位置，可直接回填发布（图片链接后续替换）
async function copyArticleWithMarkers() {
  const blocks = articleBlocks.value
  if (!blocks.length) { ElMessage.warning('请先生成配图方案'); return }
  const lines = []
  for (const b of blocks) {
    if (b.type === 'image') {
      const img = b.img
      const label = img.position === 'cover' ? '封面图' : `插图${img.section_anchor + 1} - ${img.section_title}`
      lines.push(`[配图：${label}]`)
    } else {
      const sec = b.section
      if (sec.header) lines.push('#'.repeat(sec.level || 2) + ' ' + sec.header)
      if (sec.body) lines.push(sec.body)
    }
  }
  const text = lines.join('\n\n')
  if (await writeClipboard(text)) {
    ElMessage.success('已复制带图位标记的成品文章，可回填发布（把 [配图] 替换为实际图片）')
  } else {
    ElMessage.error('复制失败，请手动复制')
  }
}
</script>

<template>
  <div class="step-pane">
    <StepHeader :no="10" title="文章配图" desc="按章节锚定配图、生成文生图提示词或搜图关键字，并产出带图位的成品文章" />
    <div class="illu-wrap" v-loading="loadingIllu">
      <!-- 配图建议横幅（与当前模式联动） -->
      <div class="illu-advice" :class="'illu-advice--' + (currentRecommendation?.method || 'ai')">
        <div class="illu-advice__head">
          <el-icon><MagicStick /></el-icon>
          <span class="illu-advice__title">配图建议</span>
          <el-tag size="small" :type="recommendationMethod === 'ai' ? 'primary' : 'warning'" effect="dark">
            {{ recommendationMethod === 'ai' ? '建议优先 AI 生图' : '建议优先 网络搜图' }}
          </el-tag>
          <el-tag v-if="illuState.method !== recommendationMethod" size="small" type="info" effect="plain" class="illu-advice__note">
            当前为{{ illuState.method === 'ai' ? 'AI 生图' : '网络搜图' }}模式
          </el-tag>
        </div>
        <div class="illu-advice__reason">{{ currentRecommendation?.reason }}</div>
      </div>

      <!-- 模式 + 工具栏 -->
      <div class="illu-toolbar">
        <div class="flow-row illu-toolbar__row">
          <el-button-group class="illu-mode">
            <el-button :type="illuState.method === 'ai' ? 'primary' : 'default'" @click="illuState.method = 'ai'">AI 生图（用提示词）</el-button>
            <el-button :type="illuState.method === 'network' ? 'primary' : 'default'" @click="illuState.method = 'network'">网络搜图（用关键字）</el-button>
          </el-button-group>
          <div class="flow-label">配图提示词</div>
          <el-select v-model="illuState.promptId" placeholder="选择配图提示词（库里「配图类」）" style="flex: 1; min-width: 160px">
            <el-option v-for="p in (options.prompts?.illustration || [])" :key="p.id" :label="p.name" :value="p.id" />
            <el-option :value="0" label="内置默认配图提示词" />
          </el-select>
          <div class="flow-label">风格</div>
          <el-select v-model="illuState.style" placeholder="自动" style="width: 150px">
            <el-option label="自动（按平台）" value="" />
            <el-option label="写实摄影" value="photo" />
            <el-option label="清新插画" value="fresh" />
            <el-option label="国风插画" value="guofeng" />
            <el-option label="极简扁平" value="flat" />
            <el-option label="3D 渲染" value="3d" />
          </el-select>
          <el-button type="primary" :icon="MagicStick" @click="generateIllustration">生成配图方案</el-button>
        </div>
        <div class="illu-tip" v-if="!currentTask.final_content">提示：未检测到最终文章内容，将仅生成封面图，建议先完成第 9 步回填最终文章。</div>
      </div>

      <!-- 图文混排预览（核心） -->
      <template v-if="illuState.plan && illuState.plan.plan.length">
        <div class="illu-flow__bar">
          <span class="illu-flow__title">图文混排预览（封面 + 各章节插图，已锚定到文章位置）</span>
          <div class="illu-flow__btns">
            <el-button size="small" :icon="CopyDocument" @click="copyAllIllustration(illuState.method)">复制全部{{ illuState.method === 'ai' ? '提示词' : '关键字' }}</el-button>
            <el-button size="small" :icon="Document" @click="copyArticleWithMarkers">复制带图位标记的成品文章</el-button>
            <el-button size="small" type="success" plain :icon="Check" @click="saveIllustrations">保存配图</el-button>
          </div>
        </div>

        <div class="illu-flow">
          <template v-for="(blk, bi) in articleBlocks" :key="bi">
            <!-- 文章文本块 -->
            <div v-if="blk.type === 'text'" class="illu-text">
              <div class="illu-text__head" :class="'illu-text__head--lv' + (blk.section.level || 2)">
                {{ blk.section.header || '开头导语' }}
              </div>
              <div class="illu-text__body">{{ blk.section.body }}</div>
            </div>
            <!-- 配图卡片（折叠，点击展开查看提示词/关键字） -->
            <div v-else class="illu-card" :class="{ 'is-open': blk.img._expanded }">
              <div class="illu-card__head" @click="blk.img._expanded = !blk.img._expanded">
                <span class="illu-badge" :class="blk.img.position === 'cover' ? 'illu-badge--cover' : 'illu-badge--section'">
                  {{ blk.img.position === 'cover' ? '封面图' : ('插图 ' + (blk.img.section_anchor + 1)) }}
                </span>
                <span class="illu-meta">{{ blk.img.section_title }} · {{ blk.img.aspect_ratio }} · {{ blk.img.size }}</span>
                <el-icon class="illu-card__chevron" :class="{ 'is-open': blk.img._expanded }"><ArrowDown /></el-icon>
              </div>
              <div v-show="blk.img._expanded" class="illu-card__body">
                <template v-if="illuState.method === 'ai'">
                  <div class="illu-field">
                    <div class="flow-label">文生图提示词（中文）</div>
                    <el-input :model-value="blk.img.ai_prompt" type="textarea" :rows="4" readonly />
                  </div>
                  <div class="illu-field">
                    <div class="flow-label">英文提示词（Midjourney 等）</div>
                    <el-input :model-value="blk.img.ai_prompt_en" type="textarea" :rows="2" readonly />
                  </div>
                  <div class="illu-field">
                    <div class="flow-label">反向词</div>
                    <el-input :model-value="blk.img.negative_prompt" type="textarea" :rows="1" readonly />
                  </div>
                </template>
                <template v-else>
                  <div class="illu-field">
                    <div class="flow-label">图片关键字（用于搜图）</div>
                    <div class="kw-chips">
                      <el-tag v-for="(kw, idx) in blk.img.search_keywords" :key="idx" class="kw-chip" @click="copyText(kw)">{{ kw }}</el-tag>
                    </div>
                  </div>
                  <div class="illu-field">
                    <div class="flow-label">推荐搜图平台</div>
                    <div class="kw-chips">
                      <el-tag v-for="(sp, idx) in blk.img.search_platforms" :key="idx" type="info" effect="plain" class="kw-chip">{{ sp }}</el-tag>
                    </div>
                  </div>
                </template>
                <div class="illu-card__foot">
                  <el-button size="small" :icon="CopyDocument" @click.stop="copyItemPrompt(blk.img, illuState.method)">复制这张</el-button>
                  <el-input v-model="blk.img.image_url" placeholder="生图/搜图后粘贴图片链接归档" size="small" style="flex: 1" @click.stop />
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
      <div v-else-if="!loadingIllu" class="empty-tip" style="padding: 30px">
        选择配图提示词后点击「生成配图方案」，将按文章章节生成封面 + 内文插图的配图方案，并锚定到文章对应位置。
      </div>
    </div>
  </div>
</template>
