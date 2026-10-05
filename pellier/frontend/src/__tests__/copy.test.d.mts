/** Types for the copy scanner, which `copy_scanner.test.ts` imports. */
export interface AllowedSentence {
  name: string
  reason: string
  text: string
}

export const ALLOWED_SENTENCES: AllowedSentence[]

/** Every copy compliance violation in `source`, as `copy.ts:line:col: message`. */
export function scan(source: string): string[]
