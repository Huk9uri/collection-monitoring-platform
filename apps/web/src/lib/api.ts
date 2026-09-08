import axios from 'axios'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_MONITORING_API_URL,
  headers: {
    Accept: 'application/json',
  },
})
