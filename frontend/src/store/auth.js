import { defineStore } from 'pinia'
import { authApi } from '../api'
import { clearToken, getStoredUser, getToken, setStoredUser, setToken } from '../api/authToken'

/**
 * 登录态。
 *
 * 令牌与用户信息同时落 localStorage（刷新页面后无需重新登录），
 * 但**权限判定以后端为准** —— 前端只负责「是否显示入口」，
 * 真正的拦截在 `main.py` 给每个业务路由挂的 `get_current_user` 上。
 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken(),
    user: getStoredUser(),
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    username: (state) => state.user?.username || '',
    role: (state) => state.user?.role || '',
    isAdmin: (state) => state.user?.role === 'admin',
    displayName: (state) => state.user?.username || '未登录',
  },
  actions: {
    async login(username, password) {
      const res = await authApi.login({ username, password })
      const data = res.data || {}
      this.token = data.token
      this.user = data.user
      setToken(data.token)
      setStoredUser(data.user)
      return data
    },

    /** 拉取当前用户（用于刷新后校准，token 失效时抛错由拦截器处理）。 */
    async fetchMe() {
      const res = await authApi.me()
      this.user = res.data
      setStoredUser(res.data)
      return res.data
    },

    logout() {
      this.token = ''
      this.user = null
      clearToken()
    },
  },
})
