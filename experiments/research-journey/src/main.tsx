import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'
import './styles/app.css'
import { App } from './App'
import { applyStoredTheme } from './components/layout/ThemeToggle'

// Apply a stored appearance before the first paint, so a dark-mode reader never sees a flash of light.
applyStoredTheme()

// In the desktop window the title bar is gone: the masthead makes room for the window buttons.
if ('__TAURI_INTERNALS__' in window) document.documentElement.dataset.shell = 'tauri'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
