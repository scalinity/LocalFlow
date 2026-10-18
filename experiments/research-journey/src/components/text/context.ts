import { createContext, useContext } from 'react'

/** Glossary terms opened inside one idea; the idea shows their glosses in its margin. */
export interface GlossState {
  open: string[]
  toggle: (id: string) => void
}
export const GlossContext = createContext<GlossState | null>(null)

/** Footnote numbers for the sources cited inside one idea. */
export const CiteContext = createContext<Map<string, number> | null>(null)

export const useGloss = () => useContext(GlossContext)
export const useCiteNumbers = () => useContext(CiteContext)
