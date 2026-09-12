import { defineStore } from 'pinia'
import { industryApi } from '../api'

export const useAppStore = defineStore('app', {
  state: () => ({
    industries: [],
    currentIndustryId: null,
    sidebarCollapsed: false,
  }),
  getters: {
    currentIndustry: (state) => {
      return state.industries.find(i => i.id === state.currentIndustryId) || null
    },
    currentIndustryName: (state) => {
      const ind = state.industries.find(i => i.id === state.currentIndustryId)
      return ind ? ind.name : '默认行业'
    }
  },
  actions: {
    async loadIndustries() {
      try {
        const res = await industryApi.list()
        this.industries = res.data || []
        if (this.industries.length > 0 && !this.currentIndustryId) {
          this.currentIndustryId = this.industries[0].id
        }
      } catch (e) {
        console.error('加载行业列表失败', e)
        this.industries = []
      }
    },
    setIndustry(id) {
      this.currentIndustryId = id
      localStorage.setItem('currentIndustryId', id)
    },
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem('sidebarCollapsed', this.sidebarCollapsed ? '1' : '0')
    },
    initFromStorage() {
      const saved = localStorage.getItem('sidebarCollapsed')
      if (saved === '1') this.sidebarCollapsed = true
    }
  }
})
