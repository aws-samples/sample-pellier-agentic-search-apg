/**
 * Persona portraits, served from `public/assets/personas`.
 *
 * One 720px WebP per person is the canonical identity image across the
 * selector, sign-in transition, header, the Operator desk and the signed-in
 * switcher. CSS owns the crop for each surface so a persona never changes
 * faces when the participant moves between them.
 *
 * The four shoppers (Anna, Marco, Theo, Jessica) and Nadia, the staff member
 * on the Operator desk, share the map: a client on the desk and a shopper in
 * the store are the same person with the same face.
 *
 * The maps hold root-relative repository paths. The accessors resolve them
 * through `imageSrc()` so a caller can assign the result straight to
 * `<img src>`: a bare root-relative path 404s behind the Workshop Studio
 * `/ports/8000/` proxy, and every consumer here renders a plain `<img>`.
 */
import { imageSrc } from '../utils/assetPath'

export const CANONICAL_PERSONA_PORTRAITS: Record<string, string> = {
  marco: '/assets/personas/marco-720.webp',
  anna: '/assets/personas/anna-720.webp',
  theo: '/assets/personas/theo-720.webp',
  jessica: '/assets/personas/jessica-720.webp',
  nadia: '/assets/personas/nadia-720.webp',
}

/** Avatar-sized crops for interface chrome. */
export const PERSONA_PHOTOS: Record<string, string> = {
  fresh: '/favicon.svg',
  ...CANONICAL_PERSONA_PORTRAITS,
}

/** Editorial crops for the hero concierge panel. */
export const PERSONA_PORTRAITS: Record<string, string> = {
  ...CANONICAL_PERSONA_PORTRAITS,
}

/**
 * Edge-to-edge crops for the portrait-led persona modal.
 */
export const PERSONA_MODAL_PORTRAITS: Record<string, string> = {
  fresh: '/favicon.svg',
  ...CANONICAL_PERSONA_PORTRAITS,
}

/**
 * Get the base-resolved avatar URL for a persona ID. Returns undefined for
 * an unknown or absent persona so callers fall back to the initial-circle
 * avatar they already render.
 */
export function getPersonaPhoto(personaId: string | null | undefined): string | undefined {
  if (!personaId) return undefined
  return imageSrc(PERSONA_PHOTOS[personaId])
}

/** Get the base-resolved editorial portrait URL for a persona ID. */
export function getPersonaPortrait(
  personaId: string | null | undefined,
): string | undefined {
  if (!personaId) return undefined
  return imageSrc(PERSONA_PORTRAITS[personaId])
}

/** Get the edge-to-edge portrait used only by the persona selection modal. */
export function getPersonaModalPortrait(
  personaId: string | null | undefined,
): string | undefined {
  if (!personaId) return undefined
  return imageSrc(PERSONA_MODAL_PORTRAITS[personaId])
}
