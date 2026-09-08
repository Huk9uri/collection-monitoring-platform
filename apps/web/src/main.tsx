import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app'
import './styles/index.css'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('앱 루트 요소를 찾을 수 없습니다.')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
