/** Types for the copy scanner, which `copy_scanner.test.ts` imports. */
export interface AllowedSentence {
  name: string
  reason: string
  text: string
}

export const ALLOWED_SENTENCES: AllowedSentence[]

/** Every copy compliance violation in `source`, as `<fileName>:line:col: message`. */
export function scan(source: string, fileName?: string): string[]

/** The repository's `data/` directory. */
export const DATA_DIR: string

/** JSON files in `data/` that hold no copy, with the reason each is skipped. */
export const DATA_NOT_COPY: Map<string, string>

/** The JSON files in `data/` the scanner reads as copy, sorted. */
export function dataCopyFiles(): Promise<string[]>
