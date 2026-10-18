import type { Chapter } from '../../data/types'
import { prologue } from './00-prologue'
import { beginning } from './01-beginning'
import { teaching } from './02-teaching'
import { searching } from './03-searching'
import { design } from './04-design'
import { training } from './05-training'
import { results } from './06-results'
import { answerKey } from './07-answer-key'
import { graders } from './08-graders'
import { seal } from './09-seal'
import { tonight } from './10-tonight'
import { next } from './11-next'

/** The journal in reading order. A new chapter is one file and one line here. */
export const CHAPTERS: Chapter[] = [prologue, beginning, teaching, searching, design, training, results, answerKey, graders, seal, tonight, next]

export const CHAPTER_BY_ID: Record<string, Chapter> = Object.fromEntries(CHAPTERS.map((c) => [c.id, c]))

/** The chapter holding the work in progress: where the "You are here" mark sits. */
export const CURRENT_CHAPTER = CHAPTERS.find((c) => c.status === 'running')?.id ?? CHAPTERS[CHAPTERS.length - 1]!.id
