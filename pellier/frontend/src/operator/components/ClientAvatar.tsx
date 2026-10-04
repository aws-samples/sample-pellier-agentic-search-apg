/**
 * A person's portrait, or a monogram when none exists.
 *
 * The four shoppers and Nadia share one portrait map, so the client on the
 * desk and the shopper in the store are the same face. Anyone else degrades to
 * an initial, which reads as intentional rather than broken.
 */
import React, { useState } from 'react'
import { getPersonaPhoto } from '../../data/personaPhotos'

interface ClientAvatarProps {
  customerId?: string | null
  name: string
  /** The portrait key: a persona id, or a staff username such as `nadia`. */
  personaId?: string | null
  size?: 'sm' | 'lg'
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const ClientAvatar: React.FC<ClientAvatarProps> = ({ customerId, name, personaId, size = 'sm' }) => {
  const [failedSource, setFailedSource] = useState<string | null>(null)
  const key = personaId || String(customerId || '').replace(/^CUST-/i, '').toLowerCase() || null
  const src = getPersonaPhoto(key)

  if (!src || failedSource === src) {
    return (
      <span className="op-monogram" data-size={size} aria-hidden="true" data-testid="operator-monogram">
        {initials(name)}
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className="op-avatar"
      data-size={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailedSource(src)}
    />
  )
}

export default ClientAvatar
