/**
 * A client's portrait, or a designed monogram when none exists.
 *
 * Never a grey box. Twelve of the fifteen clients have real portraits; the
 * three hero personas have their own. Anyone added later degrades to an
 * initial set in the brand's authority colour, which reads as intentional
 * rather than broken.
 */

import React, { useState } from 'react'
import { getClientPhoto, getClientPortrait, getPersonaPhoto, getPersonaPortrait } from '../../data/personaPhotos'

interface ClientAvatarProps {
  customerId: string
  name: string
  /** `personaId` is set only for the three storefront-switchable heroes. */
  personaId?: string | null
  size?: 'sm' | 'lg'
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

/** Visual identity only. This never selects a shopper or grants account access. */
const HERO_CLIENT_PORTRAITS: Record<string, string> = {
  'CUST-MARCO': 'marco',
  'CUST-ANNA': 'anna',
  'CUST-THEO': 'theo',
}

const ClientAvatar: React.FC<ClientAvatarProps> = ({
  customerId,
  name,
  personaId,
  size = 'sm',
}) => {
  const [failedSource, setFailedSource] = useState<string | null>(null)

  // Heroes resolve through the persona maps; everyone else through the client
  // maps. Keeping them separate stops a client id from ever resolving as a
  // signed-in shopper.
  const portraitPersona = personaId || HERO_CLIENT_PORTRAITS[customerId]
  const src = portraitPersona
    ? size === 'lg'
      ? getPersonaPortrait(portraitPersona)
      : getPersonaPhoto(portraitPersona)
    : size === 'lg'
      ? getClientPortrait(customerId)
      : getClientPhoto(customerId)

  if (!src || failedSource === src) {
    return (
      <span
        className={size === 'lg' ? 'operator-monogram-lg' : 'operator-monogram'}
        aria-hidden="true"
        data-testid="operator-monogram"
      >
        {initials(name)}
      </span>
    )
  }

  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className={size === 'lg' ? 'operator-portrait' : 'operator-avatar'}
      loading="lazy"
      decoding="async"
      onError={() => setFailedSource(src)}
    />
  )
}

export default ClientAvatar
