import type { AnchorHTMLAttributes, MouseEvent, ReactNode, Ref } from 'react'
import { navigate, type NavigateOptions } from './router'

/**
 * A real link (it can be opened in a new tab or copied) whose plain clicks go through
 * `navigate`, so places get a view transition and land at the top of the page.
 */
export function Link({
  to,
  children,
  options = { transition: true, toTop: true },
  ref,
  ...rest
}: { to: string; children: ReactNode; options?: NavigateOptions; ref?: Ref<HTMLAnchorElement> } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    rest.onClick?.(event)
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to, options)
  }
  return (
    <a {...rest} ref={ref} href={to} onClick={onClick}>
      {children}
    </a>
  )
}
