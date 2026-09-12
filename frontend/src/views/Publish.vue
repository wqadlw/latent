<template>
  <div class="publish-view">
    <!-- ========== 平台凭证管理 ========== -->
    <el-card class="block-card" shadow="never">
      <template #header>
        <div class="block-head">
          <div>
            <h3 class="block-title"><el-icon><Key /></el-icon> 平台凭证</h3>
            <p class="block-sub">上传各平台登录态 cookie，或点击「浏览器登录获取 Cookie」弹窗扫码/输密码自动抓取。仅本机明文存储，用于本账号知情授权后的浏览器自动化发布。</p>
          </div>
          <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col v-for="p in platforms" :key="p.platform" :xs="24" :sm="12" :md="8" :lg="8">
          <div class="plat-card" :class="{ 'is-api': p.adapter_type === 'api' }">
            <div class="plat-card__head">
              <span class="plat-card__name">{{ p.name }}</span>
              <el-tag size="small" :type="p.adapter_type === 'api' ? 'info' : 'warning'" effect="plain">
                {{ p.adapter_type === 'api' ? '官方API·暂缓' : '浏览器自动化' }}
              </el-tag>
            </div>
            <div class="plat-card__note">{{ p.note }}</div>
            <div class="plat-card__status">
              <el-tag v-if="p.credential_configured" size="small" type="success" effect="plain">已配置凭证</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">未配置</el-tag>
              <el-tag v-if="p.needs_relogin" size="small" type="danger" effect="plain">需重新登录</el-tag>
            </div>
            <div v-if="p.last_error" class="plat-card__err">⚠ {{ p.last_error }}</div>
            <div class="plat-card__actions">
              <el-button size="small" :icon="p.credential_configured ? Edit : Plus" @click="openCredDialog(p)">
                {{ p.credential_configured ? '更新凭证' : '配置凭证' }}
              </el-button>
              <el-button v-if="p.credential_configured" size="small" text type="danger" :icon="Delete" @click="deleteCred(p)">删除</el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- ========== 发布任务 ========== -->
    <el-card class="block-card" shadow="never">
      <template #header>
        <div class="block-head">
          <div>
            <h3 class="block-title"><el-icon><Promotion /></el-icon> 发布任务</h3>
            <p class="block-sub">从第 9 步 GEO 终稿一键建任务；每条任务需人工审核批准后再执行（防无脑群发对 GEO 反噬）。无浏览器/无凭证时可用「Mock 测试」跑通全链路。</p>
          </div>
          <div class="block-head__actions">
            <el-select v-model="filterTask" placeholder="按生产任务筛选" clearable size="small" style="width: 200px" @change="loadJobs">
              <el-option v-for="t in tasks" :key="t.id" :label="t.title || ('#' + t.id)" :value="t.id" />
            </el-select>
            <el-button type="primary" :icon="Plus" @click="openJobDialog">新建发布任务</el-button>
            <el-button type="success" :icon="MagicStick" @click="openOneClick">🚀 一键生成并发布</el-button>
          </div>
        </div>
      </template>

      <el-table :data="jobs" v-loading="jobsLoading" empty-text="暂无发布任务，点击右上角「新建发布任务」">
        <el-table-column label="生产任务" min-width="150">
          <template #default="{ row }">{{ row.task_title || ('#' + row.task_id) }}</template>
        </el-table-column>
        <el-table-column label="平台" width="100">
          <template #default="{ row }">{{ platformName(row.platform) }}</template>
        </el-table-column>
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title }}</template>
        </el-table-column>
        <el-table-column label="适配器" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.adapter_type === 'mock' ? 'info' : (row.adapter_type === 'api' ? 'info' : 'warning')" effect="plain">
              {{ row.adapter_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)" effect="dark">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="计划时间" width="150">
          <template #default="{ row }">{{ row.scheduled_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="结果" min-width="160">
          <template #default="{ row }">
            <a v-if="row.result_url" :href="row.result_url" target="_blank" class="job-url">{{ row.result_url }}</a>
            <span v-else class="job-url--none">{{ row.error ? '失败：' + row.error : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'pending_review'" size="small" type="success" :icon="Select" @click="approveJob(row)">批准</el-button>
            <el-button v-if="row.status === 'pending_review' || row.status === 'approved'" size="small" text type="danger" :icon="Close" @click="rejectJob(row)">打回</el-button>
            <el-button v-if="row.status === 'approved'" size="small" type="primary" :icon="Promotion" :loading="row._running" @click="runJob(row)">执行发布</el-button>
            <el-button v-if="row.status === 'rejected' || row.status === 'failed'" size="small" text :icon="Refresh" @click="resetToReview(row)">重提</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ========== 凭证对话框 ========== -->
    <el-dialog v-model="credDialog" :title="credForm.id ? '更新凭证：' + platformName(credForm.platform) : '配置凭证：' + platformName(credForm.platform)" width="560px">
      <el-form :model="credForm" label-width="96px">
        <el-form-item label="凭证类型">
          <el-radio-group v-model="credForm.cred_type">
            <el-radio value="cookie">Cookie 登录态</el-radio>
            <el-radio value="password">账号密码</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="credForm.cred_type === 'cookie' ? 'Cookie JSON' : '账号信息 JSON'">
          <el-input v-model="credForm.cred_json" type="textarea" :rows="8" :placeholder="credPlaceholder" />
          <div v-if="credForm.cred_type === 'cookie'" class="cred-capture-hint">
            <div class="cred-capture-opts">
              <el-button size="small" type="primary" plain :icon="Position" :loading="capturing" @click="startCapture">
                🌐 浏览器登录获取
              </el-button>
              <el-button size="small" :icon="Document" @click="openPaste">
                📋 粘贴 Cookie-Editor 导出
              </el-button>
            </div>
            <div class="cred-capture-tip">
              推荐「粘贴」方式：在已登录的浏览器装 <b>Cookie-Editor</b> 插件 → 打开平台页面 → 点导出 → 粘贴下方文本框即可，<b>无需弹窗、最稳</b>。
            </div>
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="credForm.note" placeholder="可选，例如：知乎主号 / 导出时间" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="credDialog = false">取消</el-button>
        <el-button type="primary" :loading="credSaving" @click="saveCred">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== 手动粘贴 Cookie（Cookie-Editor 导出）对话框 ========== -->
    <el-dialog v-model="pasteDialog" title="粘贴 Cookie 登录态" width="560px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" show-icon title="最可靠的登录态录入方式">
        <template #default>
          <p>在<b>已登录</b>该平台的浏览器中安装 <b>Cookie-Editor</b> 插件 → 打开平台页面 → 点「Export」复制全部 cookie。</p>
          <p>直接粘贴到下方文本框，系统会归一化为标准格式并保存。<b>全程不弹窗、不涉及你的密码。</b></p>
        </template>
      </el-alert>
      <el-input v-model="pasteText" type="textarea" :rows="10" placeholder='在此粘贴 Cookie-Editor 导出的 JSON 数组，例如：[{"name":"xxx","value":"yyy","domain":".sohu.com",...}]' class="paste-area" />
      <template #footer>
        <el-button @click="pasteDialog = false">取消</el-button>
        <el-button type="primary" :loading="pasteSaving" @click="savePaste">保存登录态</el-button>
      </template>
    </el-dialog>

    <!-- ========== Cookie 捕获进度对话框 ========== -->
    <el-dialog v-model="captureDialog" title="浏览器登录获取 Cookie" width="520px" :close-on-click-modal="false" :close-on-press-escape="false" @close="onCaptureDialogClose">
      <div class="capture-box">
        <el-alert type="info" :closable="false" show-icon title="请在弹出的浏览器中完成登录">
          <template #default>
            <p>系统已为你打开 <b>{{ capturePlatformName }}</b> 的登录页。</p>
            <p>请像平时一样<b>扫码或输入账号密码</b>登录（所有登录动作由你亲自完成，系统不触碰你的密码/2FA）。</p>
            <p>登录成功后，系统会<b>自动捕获</b>登录态 Cookie；也可点下方「完成登录，捕获 Cookie」手动触发。</p>
          </template>
        </el-alert>

        <div class="capture-status">
          <el-tag :type="captureTagType" effect="dark">{{ captureStatusText }}</el-tag>
          <span v-if="captureCookieCount" class="capture-count">已捕获 {{ captureCookieCount }} 条 cookie</span>
        </div>

        <el-alert v-if="captureError" type="error" :closable="false" show-icon :title="captureError" />

        <p v-if="captureStatus === 'failed' && captureError" class="capture-install">
          安装命令（在后端环境执行）：<br />
          <code>pip install playwright &amp;&amp; playwright install chromium</code>
        </p>
      </div>
      <template #footer>
        <el-button type="primary" :disabled="captureStatus === 'failed' || captureStatus === 'cancelled'" :loading="capturing" @click="finishCapture">
          完成登录，捕获并保存
        </el-button>
        <el-button @click="cancelCapture">取消</el-button>
      </template>
    </el-dialog>

    <!-- ========== 新建发布任务对话框 ========== -->
    <el-dialog v-model="jobDialog" title="新建发布任务" width="560px">
      <el-form :model="jobForm" label-width="96px">
        <el-form-item label="生产任务" required>
          <el-select v-model="jobForm.task_id" filterable placeholder="选择已完成第9步 GEO 终稿的生产任务" style="width: 100%">
            <el-option v-for="t in tasks" :key="t.id" :label="(t.title || ('#' + t.id)) + (t.final_content ? ' · 已有终稿' : '')" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标平台" required>
          <el-select v-model="jobForm.platform" style="width: 100%" @change="onJobPlatformChange">
            <el-option v-for="p in publishablePlatforms" :key="p.platform" :label="p.name + '（' + (p.adapter_type === 'api' ? '官方API暂缓' : '浏览器自动化') + '）'" :value="p.platform" :disabled="p.adapter_type === 'api'" />
          </el-select>
        </el-form-item>
        <el-form-item label="适配器">
          <el-radio-group v-model="jobForm.adapter_type">
            <el-radio value="playwright">Playwright（真实发布）</el-radio>
            <el-radio value="mock">Mock 测试（不走浏览器）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="计划时间">
          <el-date-picker v-model="jobForm.scheduled_at" type="datetime" placeholder="可选，留空立即审核" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss" />
        </el-form-item>
        <el-alert v-if="jobForm.adapter_type === 'playwright' && !hasCredForSelectedPlatform" type="warning" :closable="false" show-icon
          title="该平台尚未配置 cookie 凭证，执行发布时会失败。请先在上方「平台凭证」配置后重试。" />
      </el-form>
      <template #footer>
        <el-button @click="jobDialog = false">取消</el-button>
        <el-button type="primary" :loading="jobSaving" @click="createJob">创建（进入待审核）</el-button>
      </template>
    </el-dialog>

    <!-- ========== 一键生成并发布对话框 ========== -->
    <el-dialog v-model="oneClickDialog" title="🚀 一键生成并发布" width="600px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" show-icon title="用 DeepSeek + 提示词库 + 软文生产步骤，直接产出最终文章并发布">
        <template #default>
          <p>选择平台与主题（或已有任务），系统将依次执行：大纲 → 初稿 → 洗稿精修 → GEO 终检，自动生成完整最终文章，并建发布任务。</p>
          <p>勾选「生成后自动发布」可跳过人工审核直接推送到平台（需自行承担群发风险）。</p>
        </template>
      </el-alert>
      <el-form :model="oneClickForm" label-width="104px" style="margin-top:12px">
        <el-form-item label="生成模式">
          <el-radio-group v-model="oneClickForm.mode">
            <el-radio value="new">新建主题</el-radio>
            <el-radio value="task">已有任务</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="oneClickForm.mode === 'new'" label="文章主题" required>
          <el-input v-model="oneClickForm.topic" placeholder="例如：2026 家用真空吸力解决方案选购指南" />
        </el-form-item>
        <el-form-item v-else label="生产任务" required>
          <el-select v-model="oneClickForm.task_id" filterable placeholder="选择已有生产任务" style="width:100%">
            <el-option v-for="t in tasks" :key="t.id" :label="(t.title || ('#' + t.id))" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标平台" required>
          <el-select v-model="oneClickForm.platform" style="width:100%">
            <el-option v-for="p in publishablePlatforms" :key="p.platform" :label="p.name" :value="p.platform" :disabled="p.adapter_type === 'api'" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 配置">
          <el-select v-model="oneClickForm.config_id" placeholder="默认（按行业/全局生效的 DeepSeek）" clearable style="width:100%">
            <el-option v-for="c in llmConfigs" :key="c.id" :label="c.name + '（' + c.provider + '）'" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="适配器">
          <el-radio-group v-model="oneClickForm.adapter_type">
            <el-radio value="playwright">Playwright（真实发布）</el-radio>
            <el-radio value="mock">Mock 测试</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="自动发布">
          <el-switch v-model="oneClickForm.auto_publish" />
          <span class="oc-tip">开启后跳过人工审核直接发布（请确保已配置该平台 cookie 凭证）</span>
        </el-form-item>
        <el-alert v-if="oneClickForm.adapter_type === 'playwright' && !hasCredForOneClickPlatform" type="warning" :closable="false" show-icon
          title="该平台尚未配置 cookie 凭证，执行发布（含自动发布）会失败。请先配置凭证。" />
        <el-alert v-if="oneClickNeed" type="warning" :closable="false" show-icon :title="'未配置 LLM（DeepSeek）：' + (oneClickNeed.error || '')" />
        <el-collapse v-if="oneClickNeed" class="oc-need">
          <el-collapse-item title="查看已渲染的提示词（可复制给 AI 手动生成）">
            <pre>{{ oneClickNeed.rendered }}</pre>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="oneClickDialog = false">取消</el-button>
        <el-button type="success" :loading="oneClicking" @click="runOneClick">🚀 生成并发布</el-button>
      </template>
    </el-dialog>

    <!-- ========== 一键生成结果对话框 ========== -->
    <el-dialog v-model="oneClickResultDialog" title="✅ 一键生成完成" width="640px">
      <template v-if="oneClickResult">
        <el-alert
          :type="oneClickResult.auto_published ? (oneClickResult.auto_result?.ok ? 'success' : 'error') : 'success'"
          :closable="false" show-icon
          :title="oneClickResult.auto_published
            ? (oneClickResult.auto_result?.ok ? '已生成并发布成功' : '已生成，但自动发布失败（见下方原因）')
            : '已生成最终文章，请在下方任务列表「批准」并执行发布'" />
        <div class="oc-result">
          <p><b>生产任务：</b>#{{ oneClickResult.task_id }}</p>
          <p><b>发布任务：</b>#{{ oneClickResult.job_id }}</p>
          <p><b>最终标题：</b>{{ oneClickResult.final_title }}</p>
          <p><b>正文长度：</b>{{ oneClickResult.final_content_len }} 字</p>
          <el-divider>生成轨迹（4 步）</el-divider>
          <el-steps :active="4" align-center finish-status="success" direction="vertical">
            <el-step v-for="(s, key) in oneClickResult.trace" :key="key" :title="stepLabel(key)" :description="stepDesc(key, s)" />
          </el-steps>
          <template v-if="oneClickResult.auto_published && oneClickResult.auto_result">
            <el-divider>自动发布结果</el-divider>
            <p v-if="oneClickResult.auto_result.url"><b>发布链接：</b><a :href="oneClickResult.auto_result.url" target="_blank">{{ oneClickResult.auto_result.url }}</a></p>
            <p v-else-if="oneClickResult.auto_result.error" class="oc-err">⚠ {{ oneClickResult.auto_result.error }}</p>
          </template>
        </div>
      </template>
      <template #footer>
        <el-button @click="oneClickResultDialog = false">关闭</el-button>
        <el-button type="primary" @click="afterOneClick">查看发布任务</el-button>
      </template>
    </el-dialog>

    <!-- ========== 打回原因对话框 ========== -->
    <el-dialog v-model="rejectDialog" title="打回发布任务" width="460px">
      <el-input v-model="rejectReason" type="textarea" :rows="4" placeholder="填写打回原因（可选）" />
      <template #footer>
        <el-button @click="rejectDialog = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="confirmReject">确认打回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Key, Refresh, Plus, Edit, Delete, Promotion, Select, Close, Position, Document, MagicStick } from '@element-plus/icons-vue'
import { useAppStore } from '../store/app'
import { publishApi, platformCredentialApi, productionApi } from '../api'

const store = useAppStore()
const industryId = computed(() => store.currentIndustryId)

const platforms = ref([])
const credentials = ref([])
const jobs = ref([])
const tasks = ref([])
const jobsLoading = ref(false)

const filterTask = ref('')

// ---- 状态映射 ----
const STATUS_LABEL = {
  draft: '草稿', pending_review: '待审核', approved: '已批准',
  publishing: '发布中', published: '已发布', rejected: '已打回', failed: '失败',
}
const STATUS_TYPE = {
  draft: 'info', pending_review: 'warning', approved: 'primary',
  publishing: 'warning', published: 'success', rejected: 'danger', failed: 'danger',
}
const statusLabel = (s) => STATUS_LABEL[s] || s
const statusType = (s) => STATUS_TYPE[s] || 'info'

const platformName = (key) => (platforms.value.find((p) => p.platform === key) || {}).name || key
const publishablePlatforms = computed(() => platforms.value.filter((p) => p.adapter_type !== 'api'))

const credPlaceholder = computed(() =>
  credForm.cred_type === 'cookie'
    ? '粘贴从浏览器导出的 cookie 数组 JSON，例如：[{"name":"xxx","value":"yyy","domain":".zhihu.com"}]'
    : '{"username":"your_account","password":"your_pwd"}（当前仅 cookie 模式实现登录）'
)

// ---- 凭证 ----
const credDialog = ref(false)
const credSaving = ref(false)
const credForm = reactive({ id: 0, platform: '', cred_type: 'cookie', cred_json: '', note: '' })

function openCredDialog(p) {
  const existing = credentials.value.find((c) => c.platform === p.platform)
  if (existing) {
    credForm.id = existing.id
    credForm.platform = existing.platform
    credForm.cred_type = existing.cred_type
    credForm.cred_json = existing.cred_json
    credForm.note = existing.note
  } else {
    credForm.id = 0
    credForm.platform = p.platform
    credForm.cred_type = 'cookie'
    credForm.cred_json = ''
    credForm.note = ''
  }
  credDialog.value = true
}

async function saveCred() {
  if (!credForm.cred_json.trim()) { ElMessage.warning('请填写凭证内容'); return }
  credSaving.value = true
  try {
    if (credForm.id) {
      await platformCredentialApi.update(credForm.id, {
        cred_type: credForm.cred_type, cred_json: credForm.cred_json, note: credForm.note,
      })
      ElMessage.success('凭证已更新')
    } else {
      await platformCredentialApi.create({
        industry_id: industryId.value, platform: credForm.platform,
        cred_type: credForm.cred_type, cred_json: credForm.cred_json, note: credForm.note,
      })
      ElMessage.success('凭证已保存')
    }
    credDialog.value = false
    await loadCredentials()
    await loadPlatforms()
  } catch (e) { /* 拦截器已提示 */ }
  finally { credSaving.value = false }
}

async function deleteCred(p) {
  const existing = credentials.value.find((c) => c.platform === p.platform)
  if (!existing) return
  await ElMessageBox.confirm(`确认删除「${p.name}」的凭证？`, '删除确认', { type: 'warning' })
    .catch(() => Promise.reject('cancel'))
  try {
    await platformCredentialApi.delete(existing.id)
    ElMessage.success('已删除')
    await loadCredentials()
    await loadPlatforms()
  } catch (e) { if (e !== 'cancel') {} }
}

// ---- 交互式 Cookie 捕获（浏览器登录获取 Cookie） ----
const captureDialog = ref(false)
const capturing = ref(false)
const captureSessionId = ref('')
const captureStatus = ref('')        // starting | waiting_login | captured | failed | cancelled
const captureCookieCount = ref(0)
const captureError = ref('')
const capturePlatformName = ref('')
let captureTimer = null

// ---- 手动粘贴 Cookie（Cookie-Editor 导出） ----
const pasteDialog = ref(false)
const pasteText = ref('')
const pasteSaving = ref(false)

function openPaste() {
  pasteText.value = ''
  pasteDialog.value = true
}

async function savePaste() {
  const text = (pasteText.value || '').trim()
  if (!text) { ElMessage.warning('请先粘贴 Cookie 内容'); return }
  if (!industryId.value) { ElMessage.warning('请先选择行业'); return }
  if (credForm.cred_type !== 'cookie') { ElMessage.warning('仅 Cookie 模式支持粘贴'); return }
  pasteSaving.value = true
  try {
    await platformCredentialApi.capturePaste({
      industry_id: industryId.value,
      platform: credForm.platform,
      credential_id: credForm.id || undefined,
      cookies: text,
    })
    ElMessage.success('已保存登录态（来自粘贴的 Cookie）')
    pasteDialog.value = false
    await loadCredentials()
    await loadPlatforms()
  } catch (e) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail
      : (detail ? JSON.stringify(detail) : (e?.message || '保存失败'))
    ElMessage.error('粘贴保存失败：' + msg)
  } finally {
    pasteSaving.value = false
  }
}

const captureTagType = computed(() => {
  switch (captureStatus.value) {
    case 'captured': return 'success'
    case 'failed': return 'danger'
    case 'cancelled': return 'info'
    default: return 'warning'
  }
})
const captureStatusText = computed(() => {
  switch (captureStatus.value) {
    case 'starting': return '正在打开浏览器…'
    case 'waiting_login': return '等待你在浏览器中登录…'
    case 'captured': return '已捕获登录态 Cookie'
    case 'failed': return '捕获失败'
    case 'cancelled': return '已取消'
    default: return captureStatus.value || '—'
  }
})

function stopCapturePolling() {
  if (captureTimer) { clearInterval(captureTimer); captureTimer = null }
}

async function startCapture() {
  if (!industryId.value) { ElMessage.warning('请先选择行业'); return }
  if (credForm.cred_type !== 'cookie') { ElMessage.warning('仅 Cookie 模式支持浏览器登录获取'); return }
  capturing.value = true
  captureError.value = ''
  captureCookieCount.value = 0
  captureStatus.value = 'starting'
  capturePlatformName.value = platformName(credForm.platform)
  try {
    const res = await platformCredentialApi.captureStart({
      industry_id: industryId.value,
      platform: credForm.platform,
      credential_id: credForm.id || undefined,
    })
    captureSessionId.value = res.data.session_id
    captureDialog.value = true
    // 轮询状态
    stopCapturePolling()
    captureTimer = setInterval(pollCapture, 1500)
    pollCapture()
  } catch (e) {
    ElMessage.error('启动捕获失败：' + (e?.response?.data?.detail || e?.message || ''))
  } finally {
    capturing.value = false
  }
}

async function pollCapture() {
  if (!captureSessionId.value) return
  try {
    const res = await platformCredentialApi.captureStatus(captureSessionId.value)
    const d = res.data
    captureStatus.value = d.status
    captureCookieCount.value = d.cookie_count || 0
    captureError.value = typeof d.error === 'string' ? d.error : (d.error ? JSON.stringify(d.error) : '')
    // 自动捕获成功时，提示可保存（不自动关弹窗，由用户点保存）
    if (d.status === 'captured') stopCapturePolling()
    if (d.status === 'failed' || d.status === 'cancelled') stopCapturePolling()
  } catch (e) {
    // 会话已结束（被后端清理）视为结束
    stopCapturePolling()
  }
}

async function finishCapture() {
  if (!captureSessionId.value) return
  capturing.value = true
  try {
    const res = await platformCredentialApi.captureFinish(captureSessionId.value)
    const d = res.data || {}
    // captureFinish 已直接返回 ok / cookie_count（会话此时已被后端清理，无需再轮询）
    if (d.ok && d.cookie_count > 0) {
      captureStatus.value = 'captured'
      captureCookieCount.value = d.cookie_count
      ElMessage.success(`已捕获 ${d.cookie_count} 条登录态并保存到凭证库`)
      captureDialog.value = false
      await loadCredentials()
      await loadPlatforms()
    } else if (d.ok && d.cookie_count === 0) {
      ElMessage.warning('未检测到登录态 Cookie，请确认已在弹出的浏览器中完成登录后重试')
    } else {
      // 未成功：d.status 可能为 failed / cancelled，d.error 为字符串
      ElMessage.error('捕获失败：' + (d.error || '未知错误'))
    }
  } catch (e) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail
      : (detail ? JSON.stringify(detail) : (e?.message || '未知错误'))
    ElMessage.error('捕获失败：' + msg)
  } finally {
    capturing.value = false
  }
}

async function cancelCapture() {
  if (captureSessionId.value) {
    try { await platformCredentialApi.captureCancel(captureSessionId.value) } catch (e) {}
  }
  stopCapturePolling()
  captureDialog.value = false
}

function onCaptureDialogClose() {
  // 关闭弹窗但未保存：尝试取消后端会话，避免浏览器进程残留
  if (captureSessionId.value && captureStatus.value !== 'captured') {
    platformCredentialApi.captureCancel(captureSessionId.value).catch(() => {})
  }
  stopCapturePolling()
}

// ---- 发布任务 ----
const jobDialog = ref(false)
const jobSaving = ref(false)
const jobForm = reactive({ task_id: '', platform: '', adapter_type: 'playwright', scheduled_at: '' })

const hasCredForSelectedPlatform = computed(() => {
  if (jobForm.adapter_type === 'mock') return true
  return credentials.value.some((c) => c.platform === jobForm.platform && c.status === 1)
})

function onJobPlatformChange() {
  const p = platforms.value.find((x) => x.platform === jobForm.platform)
  if (p && p.adapter_type === 'api') jobForm.adapter_type = 'mock'
}

function openJobDialog() {
  if (!tasks.value.length) { ElMessage.warning('当前行业暂无生产任务'); return }
  jobForm.task_id = ''
  jobForm.platform = publishablePlatforms.value[0]?.platform || ''
  jobForm.adapter_type = 'playwright'
  jobForm.scheduled_at = ''
  jobDialog.value = true
}

async function createJob() {
  if (!jobForm.task_id) { ElMessage.warning('请选择生产任务'); return }
  if (!jobForm.platform) { ElMessage.warning('请选择目标平台'); return }
  jobSaving.value = true
  try {
    await publishApi.createJob({
      industry_id: industryId.value,
      task_id: Number(jobForm.task_id),
      platform: jobForm.platform,
      adapter_type: jobForm.adapter_type,
      scheduled_at: jobForm.scheduled_at || '',
    })
    ElMessage.success('已创建发布任务，进入「待审核」，请审核批准后执行')
    jobDialog.value = false
    await loadJobs()
  } catch (e) { /* 拦截器已提示 */ }
  finally { jobSaving.value = false }
}

// ---- 一键生成并发布 ----
const llmConfigs = ref([])
const oneClickDialog = ref(false)
const oneClicking = ref(false)
const oneClickResultDialog = ref(false)
const oneClickResult = ref(null)
const oneClickNeed = ref(null)
const oneClickForm = reactive({
  mode: 'new', topic: '', task_id: '', platform: '', config_id: '', adapter_type: 'playwright', auto_publish: false,
})

const hasCredForOneClickPlatform = computed(() => {
  if (oneClickForm.adapter_type === 'mock') return true
  return credentials.value.some((c) => c.platform === oneClickForm.platform && c.status === 1)
})

async function loadLlmConfigs() {
  try {
    const res = await llmApi.listConfigs(industryId.value || 0)
    llmConfigs.value = res.data || []
  } catch (e) { llmConfigs.value = [] }
}

function openOneClick() {
  oneClickNeed.value = null
  oneClickResult.value = null
  oneClickForm.mode = 'new'
  oneClickForm.topic = ''
  oneClickForm.task_id = ''
  oneClickForm.platform = publishablePlatforms.value[0]?.platform || ''
  oneClickForm.config_id = (llmConfigs.value.find((c) => c.is_default) || llmConfigs.value[0])?.id ?? ''
  oneClickForm.adapter_type = 'playwright'
  oneClickForm.auto_publish = false
  oneClickDialog.value = true
}

async function runOneClick() {
  if (oneClickForm.mode === 'new') {
    if (!oneClickForm.topic.trim()) { ElMessage.warning('请填写文章主题'); return }
  } else if (!oneClickForm.task_id) {
    ElMessage.warning('请选择生产任务'); return
  }
  if (!oneClickForm.platform) { ElMessage.warning('请选择目标平台'); return }

  oneClicking.value = true
  oneClickNeed.value = null
  try {
    const res = await publishApi.oneClick({
      industry_id: industryId.value || 0,
      platform: oneClickForm.platform,
      task_id: oneClickForm.mode === 'task' ? Number(oneClickForm.task_id) : 0,
      topic: oneClickForm.mode === 'new' ? oneClickForm.topic : '',
      config_id: oneClickForm.config_id ? Number(oneClickForm.config_id) : null,
      adapter_type: oneClickForm.adapter_type,
      auto_publish: oneClickForm.auto_publish,
    })
    const d = res.data || {}
    if (d.need_config) {
      oneClickNeed.value = { failed_step: d.failed_step, rendered: d.rendered, error: d.error }
      ElMessage.warning('未配置 LLM（DeepSeek），已展示可手动复制的提示词')
      return
    }
    if (!d.ok) {
      ElMessage.error('生成失败：' + (d.error || '未知错误') + (d.failed_step ? '（步骤：' + d.failed_step + '）' : ''))
      return
    }
    oneClickResult.value = d
    oneClickResultDialog.value = true
    await loadJobs()
    ElMessage.success(d.auto_published ? '已生成并发布' : '已生成最终文章，请在任务列表批准执行')
  } catch (e) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : (e?.message || '未知错误'))
    ElMessage.error('一键发布失败：' + msg)
  } finally {
    oneClicking.value = false
  }
}

function stepLabel(k) {
  return { outline: '① 大纲生成', draft: '② 初稿生成', rewrite: '③ 洗稿精修', geo: '④ GEO 终检' }[k] || k
}
function stepDesc(k, s) {
  if (!s) return ''
  if (k === 'geo') return 'GEO 评分 ' + (s.geo_score ?? '?') + '，' + (s.parsed_ok ? '四段解析成功' : '四段解析不完整')
  return '提示词：' + (s.prompt_name || '-') + '，生成 ' + (s.len || 0) + ' 字'
}
function afterOneClick() {
  oneClickResultDialog.value = false
  oneClickDialog.value = false
}

async function approveJob(row) {
  try {
    await publishApi.approveJob(row.id)
    ElMessage.success('已批准，可点击「执行发布」')
    await loadJobs()
  } catch (e) {}
}

const rejectDialog = ref(false)
const rejectReason = ref('')
const rejecting = ref(false)
let rejectTarget = null
function rejectJob(row) {
  rejectTarget = row
  rejectReason.value = ''
  rejectDialog.value = true
}
async function confirmReject() {
  if (!rejectTarget) return
  rejecting.value = true
  try {
    await publishApi.rejectJob(rejectTarget.id, rejectReason.value)
    ElMessage.success('已打回')
    rejectDialog.value = false
    await loadJobs()
  } catch (e) {}
  finally { rejecting.value = false }
}

async function runJob(row) {
  row._running = true
  try {
    const res = await publishApi.runJob(row.id)
    const d = res.data
    if (d.ok) {
      ElMessage.success(`发布成功！URL：${d.url}`)
    } else {
      ElMessage.error('发布失败：' + (d.error || '未知错误'))
    }
    await loadJobs()
    await loadPlatforms()
  } catch (e) {}
  finally { row._running = false }
}

// 打回/失败后重提：后端 approve 会将 rejected/failed 重置为 approved，可直接执行或再次打回
async function resetToReview(row) {
  try {
    await publishApi.approveJob(row.id)
    ElMessage.success('已重新提交并批准，可点击「执行发布」')
    await loadJobs()
  } catch (e) {}
}

// ---- 加载 ----
async function loadPlatforms() {
  const res = await publishApi.platforms(industryId.value || 0)
  platforms.value = res.data || []
}
async function loadCredentials() {
  const res = await platformCredentialApi.list(industryId.value || 0)
  credentials.value = res.data || []
}
async function loadJobs() {
  jobsLoading.value = true
  try {
    const res = await publishApi.listJobs(industryId.value || 0, filterTask.value || 0)
    jobs.value = res.data || []
  } finally { jobsLoading.value = false }
}
async function loadTasks() {
  const res = await productionApi.list({ industry_id: industryId.value || 0, page: 1, page_size: 200 })
  tasks.value = res.data?.list || res.data || []
}
async function loadAll() {
  if (!store.currentIndustryId) {
    try { await store.loadIndustries() } catch (e) { /* 留空，下面用 0 兜底 */ }
  }
  await Promise.all([loadPlatforms(), loadCredentials(), loadTasks(), loadJobs(), loadLlmConfigs()])
}

onMounted(loadAll)
</script>

<style scoped>
.publish-view { display: flex; flex-direction: column; gap: 16px; }
.block-card { border-radius: var(--radius-lg, 12px); }
.block-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.block-head__actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.block-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.block-sub { font-size: 12px; color: var(--text-tertiary); margin: 0; max-width: 720px; line-height: 1.6; }

.plat-card { border: 1px solid var(--border-light); border-radius: var(--radius-md, 10px); padding: 14px; background: var(--bg-card); display: flex; flex-direction: column; gap: 8px; height: 100%; }
.plat-card.is-api { opacity: 0.7; }
.plat-card__head { display: flex; align-items: center; justify-content: space-between; }
.plat-card__name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.plat-card__note { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; min-height: 34px; }
.plat-card__status { display: flex; gap: 6px; flex-wrap: wrap; }
.plat-card__err { font-size: 11px; color: var(--el-color-danger); line-height: 1.4; }
.plat-card__actions { display: flex; gap: 6px; margin-top: auto; }

.job-url { color: var(--brand-600, #4f46e5); font-size: 12px; word-break: break-all; }
.job-url--none { font-size: 12px; color: var(--text-tertiary); }

.cred-capture-hint { font-size: 12px; color: var(--text-secondary); margin-top: 8px; line-height: 1.6; }
.cred-capture-hint .el-button { margin-top: 6px; }

.capture-box { display: flex; flex-direction: column; gap: 14px; }
.capture-status { display: flex; align-items: center; gap: 12px; }
.capture-count { font-size: 12px; color: var(--el-color-success); }
.capture-install { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.capture-install code { background: var(--bg-hover, #f4f4f5); padding: 2px 6px; border-radius: 4px; font-family: monospace; }

.oc-tip { font-size: 12px; color: var(--text-tertiary); margin-left: 12px; line-height: 1.5; }
.oc-need { margin-top: 8px; }
.oc-need pre { white-space: pre-wrap; word-break: break-all; font-size: 12px; background: var(--bg-hover, #f4f4f5); padding: 10px; border-radius: 6px; max-height: 240px; overflow: auto; margin: 0; }
.oc-result { font-size: 13px; line-height: 1.8; color: var(--text-primary); }
.oc-result p { margin: 4px 0; }
.oc-err { color: var(--el-color-danger); }
</style>
