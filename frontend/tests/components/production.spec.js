import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import VersionHistoryDialog from '@/components/production/VersionHistoryDialog.vue'
import KnowledgePreviewDrawer from '@/components/production/KnowledgePreviewDrawer.vue'
import CustomVarDialog from '@/components/production/CustomVarDialog.vue'
import OneClickGenerateResult from '@/components/production/OneClickGenerateResult.vue'
import CreatePublishTaskDialog from '@/components/production/CreatePublishTaskDialog.vue'

// dialog/drawer 通过 teleport 渲染到 body，单测中在 document.body 内断言；清理避免用例间泄漏
afterEach(() => {
  document.body.innerHTML = ''
})

function findBtn(text) {
  return [...document.body.querySelectorAll('button')].find((b) => b.textContent.includes(text))
}

describe('VersionHistoryDialog', () => {
  test('空列表展示提示', async () => {
    mount(VersionHistoryDialog, { props: { modelValue: true, list: [] } })
    await flushPromises()
    expect(document.body.textContent).toContain('暂无历史版本')
  })

  test('渲染版本并 emit restore', async () => {
    const item = { id: 1, version_no: 2, create_time: '2026-07-22T10:00:00Z', content: 'hello world' }
    const wrapper = mount(VersionHistoryDialog, { props: { modelValue: true, list: [item] } })
    await flushPromises()
    expect(document.body.textContent).toContain('v2')
    expect(document.body.textContent).toContain('hello world')
    const btn = findBtn('回滚到此版本')
    expect(btn).toBeTruthy()
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('restore')).toBeTruthy()
    expect(wrapper.emitted('restore')[0][0]).toEqual(item)
  })
})

describe('KnowledgePreviewDrawer', () => {
  test('渲染知识点并 emit toggle', async () => {
    const item = { id: 5, title: '知识点T', importance: 'high', source: 'S', tags: 'a,b', content: 'C' }
    const wrapper = mount(KnowledgePreviewDrawer, { props: { modelValue: true, item, isSelected: false } })
    await flushPromises()
    expect(document.body.textContent).toContain('知识点T')
    expect(document.body.textContent).toContain('高重要性')
    const btn = findBtn('加入选择')
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('toggle')).toBeTruthy()
    expect(wrapper.emitted('toggle')[0][0]).toBe(5)
  })
})

describe('CustomVarDialog', () => {
  test('列出变量并 emit confirm', async () => {
    const list = [{ name: 'topic', desc: '主题', value: '' }]
    const wrapper = mount(CustomVarDialog, { props: { modelValue: true, list } })
    await flushPromises()
    expect(document.body.textContent).toContain('{topic}')
    const btn = findBtn('生成提示词')
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })
})

describe('OneClickGenerateResult', () => {
  test('geo 模式渲染标题/评分并 emit accept', async () => {
    const data = { config_name: 'c1', provider: 'p', model: 'm', parsed: { title: 'GeoTitle', score: 88 }, text: 'body' }
    const labelMap = { geo: 'GEO 终稿' }
    const wrapper = mount(OneClickGenerateResult, { props: { modelValue: true, data, step: 'geo', labelMap } })
    await flushPromises()
    expect(document.body.textContent).toContain('GeoTitle')
    expect(document.body.textContent).toContain('88 / 100')
    const btn = findBtn('接受并生成最终发布稿')
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('accept')).toBeTruthy()
  })

  test('emit copy', async () => {
    const wrapper = mount(OneClickGenerateResult, {
      props: { modelValue: true, data: { text: 'x' }, step: 'draft', labelMap: { draft: '初稿' } },
    })
    await flushPromises()
    const btn = findBtn('复制')
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('copy')).toBeTruthy()
  })
})

describe('CreatePublishTaskDialog', () => {
  test('列出平台并 emit create', async () => {
    const platforms = [
      { platform: 'zhihu', name: '知乎', adapter_type: 'playwright' },
      { platform: 'weibo', name: '微博', adapter_type: 'api' },
    ]
    const form = { platform: '', adapter_type: 'mock', scheduled_at: '' }
    const wrapper = mount(CreatePublishTaskDialog, { props: { modelValue: true, form, platforms } })
    await flushPromises()
    expect(document.body.textContent).toContain('知乎')
    expect(document.body.textContent).toContain('微博')
    const btn = findBtn('创建（进入待审核）')
    await btn.click()
    await nextTick()
    expect(wrapper.emitted('create')).toBeTruthy()
  })
})
