/**
 * Atelier Architecture — shared components.
 *
 * The building blocks used by every architecture detail page (Memory,
 * MCP, State Management, Tool Registry, Runtime, Skills, Evaluations).
 *
 * The Skills page is the visual contract. Every component here ships
 * with the exact styling Skills used, extracted so the other pages
 * mirror it byte-for-byte. Styling lives in
 * ``src/styles/atelier-shared.css`` — all colors reference CSS custom
 * properties from ``src/index.css :root``.
 *
 * Token additions for this module:
 *   --amber-1: #b88a3a     — Evaluations telemetry corner
 *   --amber-soft           — Evaluations axis tint
 */
export { default as DetailPageShell } from './DetailPageShell'
export { default as SectionFrame } from './SectionFrame'
export { default as SectionEyebrow } from './SectionEyebrow'
export { default as CheatSheet } from './CheatSheet'
export { default as LiveStrip } from './LiveStrip'
export { default as StatusBadge } from './StatusBadge'
export type { StatusBadgeVariant } from './StatusBadge'
export { default as DiagramFrame } from './DiagramFrame'
export { default as MonoBlock } from './MonoBlock'
