<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <section class="brand-panel">
      <div class="brand-panel__inner">
        <div class="brand-mark">
          <BrandMark :size="38" foreground="#FFFFFF" accent="#9CA3AF" />
          <span class="brand-mark__text">显影 Latent</span>
        </div>

        <h1 class="brand-headline">
          让品牌从潜影到显影<br />
          在 AI 的答案里被看见、被引用
        </h1>

        <ul class="brand-points">
          <li v-for="point in highlights" :key="point.title">
            <span class="point-dot"></span>
            <div>
              <strong>{{ point.title }}</strong>
              <p>{{ point.desc }}</p>
            </div>
          </li>
        </ul>

        <div class="brand-version">
          <span class="dot"></span>
          <span>v{{ version }}</span>
          <span class="sep">·</span>
          <span>本地部署 · 数据不出机</span>
        </div>
      </div>
      <div class="brand-panel__glow"></div>
    </section>

    <!-- 右侧表单区 -->
    <section class="form-panel">
      <div class="form-card">
        <header class="form-card__head">
          <h2>登录</h2>
          <p>请使用系统账号登录，继续你的 GEO 运营工作台</p>
        </header>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          @submit.prevent="onSubmit"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              autocomplete="username"
              :prefix-icon="User"
              @keyup.enter="onSubmit"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
              show-password
              :prefix-icon="Lock"
              @keyup.enter="onSubmit"
            />
          </el-form-item>

          <el-button
            type="primary"
            class="submit-btn"
            :loading="loading"
            @click="onSubmit"
          >
            {{ loading ? '登录中…' : '登 录' }}
          </el-button>
        </el-form>

        <el-alert
          v-if="errorMsg"
          :title="errorMsg"
          type="error"
          :closable="false"
          show-icon
          class="error-alert"
        />

        <footer class="form-card__foot">
          <p class="hint-title">首次使用？</p>
          <p class="hint-body">
            默认账号 <code>admin</code> / <code>admin123</code>，
            登录后请立即在「系统设置 → 账号安全」中修改密码。
          </p>
        </footer>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { metaApi } from '../api'
import { useAuthStore } from '../store/auth'
import BrandMark from '../components/BrandMark.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const version = ref('3.0.0')

const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const highlights = [
  { title: '结构化内容资产', desc: '行业 / 平台 / 人设 / 知识库 / 提示词统一沉淀，按行业空间严格隔离' },
  { title: '可追溯生产流水线', desc: '每步产物回填为变量，发布前经证据核对的质检闸门' },
  { title: 'AI 可见性闭环', desc: '发布 → 收录 → 引用 → 排名 → 回流选题，每一步都可度量' },
]

onMounted(async () => {
  try {
    const res = await metaApi.get()
    if (res?.data?.version) version.value = res.data.version
  } catch {
    // 后端未就绪时不阻断登录页渲染
  }
})

async function onSubmit() {
  errorMsg.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.replace(redirect)
  } catch (err) {
    const detail = err?.response?.data?.detail
    errorMsg.value = typeof detail === 'string' ? detail : '登录失败，请检查用户名与密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page);
}

/* ===== 左侧品牌区 ===== */
.brand-panel {
  position: relative;
  flex: 1 1 52%;
  overflow: hidden;
  background: linear-gradient(150deg, #0a0908 0%, #1c1917 55%, #12100f 100%);
  color: var(--text-inverse);
  display: flex;
  align-items: center;
}

.brand-panel__glow {
  position: absolute;
  right: -160px;
  bottom: -180px;
  width: 520px;
  height: 520px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(156, 163, 175, 0.22) 0%, rgba(156, 163, 175, 0) 68%);
  pointer-events: none;
}

.brand-panel__inner {
  position: relative;
  z-index: 1;
  padding: 0 8%;
  max-width: 620px;
}

.brand-mark {
  display: flex;
  align-items: center;
  margin-bottom: 46px;
}

.brand-mark__text {
  margin-left: 12px;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.4px;
}

.brand-headline {
  font-size: 30px;
  line-height: 1.5;
  font-weight: 600;
  margin: 0 0 44px;
  color: #fff;
}

.brand-points {
  list-style: none;
  padding: 0;
  margin: 0 0 52px;
}

.brand-points li {
  display: flex;
  align-items: flex-start;
  margin-bottom: 22px;
}

.point-dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  margin-top: 8px;
  margin-right: 14px;
  border-radius: 50%;
  background: #9ca3af;
  box-shadow: 0 0 0 4px rgba(156, 163, 175, 0.18);
}

.brand-points strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}

.brand-points p {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: rgba(226, 232, 240, 0.62);
}

.brand-version {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.5);
}

.brand-version .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-emerald);
  margin-right: 8px;
}

.brand-version .sep {
  margin: 0 8px;
}

/* ===== 右侧表单区 ===== */
.form-panel {
  flex: 1 1 48%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.form-card {
  width: 100%;
  max-width: 380px;
}

.form-card__head {
  margin-bottom: 30px;
}

.form-card__head h2 {
  margin: 0 0 8px;
  font-size: 25px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-card__head p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.submit-btn {
  width: 100%;
  height: 44px;
  margin-top: 6px;
  font-size: 15px;
  letter-spacing: 2px;
}

.error-alert {
  margin-top: 16px;
}

.form-card__foot {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid var(--border-light);
}

.hint-title {
  margin: 0 0 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
}

.hint-body {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-tertiary);
}

.hint-body code {
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12px;
}

/* 窄屏隐藏品牌区，只留表单 */
@media (max-width: 860px) {
  .brand-panel {
    display: none;
  }
  .form-panel {
    flex: 1 1 100%;
  }
}
</style>
