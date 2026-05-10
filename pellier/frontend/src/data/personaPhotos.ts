/**
 * Persona headshot photos — Unsplash free-to-use portraits.
 *
 * Shared across the Atelier sidebar, Boutique header persona pill,
 * and persona dropdown. Each URL points to a 200×200 face-crop so
 * avatars render a real face at any size.
 *
 * Swap any URL to change the face globally.
 */
export const PERSONA_PHOTOS: Record<string, string> = {
  marco:
    'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200&h=200&fit=crop&crop=face',
  anna:
    'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
  theo:
    'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=200&h=200&fit=crop&crop=face',
  fresh:
    'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&h=200&fit=crop&crop=face',
}

/**
 * Get the photo URL for a persona ID. Returns undefined for unknown
 * personas so callers can fall back to the initial-circle avatar.
 */
export function getPersonaPhoto(personaId: string | null | undefined): string | undefined {
  if (!personaId) return PERSONA_PHOTOS.fresh
  return PERSONA_PHOTOS[personaId]
}
