import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'

const KEY = 'tabletalk-theme'

function initialTheme(): 'light' | 'dark' {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage can be unavailable (private mode); fall back to light
  }
  return 'light'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(initialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      // not essential
    }
  }, [theme])

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
    >
      {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
