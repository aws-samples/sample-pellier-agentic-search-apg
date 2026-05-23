/**
 * StylistHandoffCard — UI surface for the escalate_to_stylist tool.
 *
 * Renders when the agent decides the ask is outside what it can
 * honestly answer (deep personal-style coaching beyond the catalog,
 * out-of-policy returns Cedar can't process, catalog misses where the
 * shopper deserves a real person). The agent's prose still streams
 * above the card; this component replaces the usual product grid with
 * a clear "talk to a human" CTA.
 *
 * The "stylist" address is a placeholder for whatever escalation
 * channel a production deployment wires in (live chat, email queue,
 * CX ticket). For the workshop it's a mailto — pure UI, no real
 * human on the other end. Builder's Session teaches this as the
 * escape hatch every agent needs but most demos skip.
 */
import { motion } from 'framer-motion'
import { ArrowUpRight, User } from 'lucide-react'

import type { StylistHandoff } from '../hooks/useAgentChat'

interface StylistHandoffCardProps {
  handoff: StylistHandoff
}

export default function StylistHandoffCard({ handoff }: StylistHandoffCardProps) {
  const subject = encodeURIComponent('Stylist handoff from Pellier concierge')
  const body = encodeURIComponent(
    `Reason routed to a stylist:\n${handoff.reason}\n\n` +
      (handoff.customer_id
        ? `Customer reference: ${handoff.customer_id}\n\n`
        : '') +
      'Stylist team — please pick this up from the concierge thread.\n',
  )
  const href = `mailto:${handoff.contact.mailto}?subject=${subject}&body=${body}`

  return (
    <motion.section
      data-testid="stylist-handoff-card"
      role="group"
      aria-label="Stylist handoff"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.2, 0.9, 0.3, 1.05] }}
      style={{
        marginTop: 12,
        padding: '14px 16px',
        background: 'rgba(255, 252, 247, 0.96)',
        border: '1px dashed rgba(196, 69, 54, 0.42)',
        borderRadius: 12,
        fontFamily: 'var(--sans)',
        color: '#1f1410',
        boxShadow: '0 1px 3px rgba(31, 20, 16, 0.06)',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 24,
            height: 24,
            borderRadius: '50%',
            background: 'rgba(196, 69, 54, 0.12)',
            color: 'rgba(196, 69, 54, 0.98)',
          }}
        >
          <User size={13} strokeWidth={1.75} />
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'rgba(196, 69, 54, 0.98)',
          }}
        >
          Handed off to a stylist
        </span>
      </header>

      <p
        style={{
          margin: 0,
          fontSize: 14,
          lineHeight: 1.55,
          color: 'rgba(31, 20, 16, 0.85)',
        }}
      >
        {handoff.reason}
      </p>

      {handoff.next_steps && handoff.next_steps.length > 0 && (
        <ol
          data-testid="stylist-handoff-next-steps"
          style={{
            margin: '10px 0 0',
            padding: 0,
            listStyle: 'none',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            fontSize: 13,
            lineHeight: 1.5,
            color: 'rgba(31, 20, 16, 0.72)',
          }}
        >
          {handoff.next_steps.map((step, idx) => (
            <li
              key={idx}
              style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}
            >
              <span
                aria-hidden="true"
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 11,
                  color: 'rgba(196, 69, 54, 0.7)',
                  minWidth: 14,
                }}
              >
                {idx + 1}.
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}

      <footer
        style={{
          marginTop: 14,
          paddingTop: 10,
          borderTop: '1px solid rgba(31, 20, 16, 0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: 11,
            color: 'rgba(31, 20, 16, 0.55)',
          }}
        >
          {handoff.contact.response_window}
        </span>
        <a
          data-testid="stylist-handoff-cta"
          href={href}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 14px',
            borderRadius: 999,
            background: '#1f1410',
            color: '#F7F3EE',
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: '0.02em',
            textDecoration: 'none',
          }}
        >
          {handoff.contact.label}
          <ArrowUpRight size={13} strokeWidth={1.75} aria-hidden="true" />
        </a>
      </footer>
    </motion.section>
  )
}
