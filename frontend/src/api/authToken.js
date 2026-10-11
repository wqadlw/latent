/**
 * 访问令牌的本地存取（独立模块，避免 api 与 store 之间循环依赖）。
 *
 * 令牌存 localStorage 而非 Cookie：后端以 `Authorization: Bearer` 校验，
 * 无 Cookie 就天然免疫 CSRF，也不需要维护会话表。
 */

const TOKEN_KEY = 'acm_token'
const USER_KEY = 'acm_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredUser(user) {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function isLoggedIn() {
  return !!getToken()
}
