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
        const ids = this.industries.map(i => i.id)
        if (!ids.length) {
          this.currentIndustryId = null
          return
        }
        // 生效优先级：store 里已有的（且仍存在）> localStorage 保存的（且仍存在）> 第一个。
        // 为什么必须校验「仍存在」：行业被删掉后，localStorage 里还留着它的 id，
        // 直接拿来用会让所有业务接口都带着一个不存在的 industry_id 去请求。
        const candidates = [this.currentIndustryId, Number(localStorage.getItem('currentIndustryId'))]
        this.currentIndustryId = candidates.find(id => id && ids.includes(id)) || ids[0]
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
      // 恢复上次选中的行业。此前这里只恢复 sidebarCollapsed，
      // 而 setIndustry() 一直在往 localStorage 写 currentIndustryId——
      // 写进去却从不读出来，导致「上次选的行业」每次启动都丢失、回落到第一个。
      const savedIndustry = Number(localStorage.getItem('currentIndustryId'))
      if (savedIndustry) this.currentIndustryId = savedIndustry
    }
  }
})
