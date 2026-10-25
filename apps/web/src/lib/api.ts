import axios from 'axios'

const DEFAULT_API_TIMEOUT_MILLISECONDS = 40_000

export function resolveApiTimeout(configured: string | undefined) {
  if (configured === undefined || configured.trim() === '') {
    return DEFAULT_API_TIMEOUT_MILLISECONDS
  }

  const timeout = Number(configured)
  if (!Number.isInteger(timeout) || timeout <= 0) {
    throw new Error(
      'VITE_MONITORING_API_TIMEOUT_MS는 양수 정수(밀리초)여야 합니다.',
    )
  }
  return timeout
}

export const apiClient = axios.create({
  withCredentials: true,
  baseURL: import.meta.env.VITE_MONITORING_API_URL,
  timeout: resolveApiTimeout(import.meta.env.VITE_MONITORING_API_TIMEOUT_MS),
  headers: {
    Accept: 'application/json',
  },
})

let csrfToken: string | null = null
export function setCsrfToken(value: string | null) { csrfToken = value }

apiClient.interceptors.request.use((config) => {
  if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(config.method ?? '')) {
    config.headers.set('X-CSRF-Token', csrfToken)
  }
  return config
})
apiClient.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401 && !error.config?.url?.endsWith('/auth/login')) {
    csrfToken = null
    window.dispatchEvent(new Event('monitoring-session-expired'))
  }
  return Promise.reject(error)
})
