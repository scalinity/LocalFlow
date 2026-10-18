import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'
import './styles/app.css'
import { App } from './App'
import { applyStoredTheme } from './components/layout/ThemeToggle'

// Apply a stored appearance before the first paint, so a dark-mode reader never sees a flash of light.
applyStoredTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
