import axios, { AxiosError, AxiosHeaders } from 'axios'
import { mockAdapter } from './mockAdapter'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

const api = axios.create({
  baseURL,
  timeout: 15000,
  headers: AxiosHeaders.from({ 'Content-Type': 'application/json' }),
  ...(useMock ? { adapter: mockAdapter } : {}),
})

api.interceptors.request.use((config) => config)

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (error instanceof AxiosError && error.response?.status === 401) {
      // 本期无登录，401 仅在拦截器统一消化，不整页跳转。
    }
    return Promise.reject(error)
  },
)

export const isMockMode = useMock
export default api
