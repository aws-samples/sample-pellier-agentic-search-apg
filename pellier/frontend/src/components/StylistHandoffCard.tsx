/**
 * StylistHandoffCard — UI surface for the escalate_to_human tool.
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
 * human on the other end. The workshop teaches this as the
 * escape hatch every agent needs but most demos skip.
 */
import { motion, useReducedMotion } from 'motion/react'
import { ArrowUpRight, User } from 'lucide-react'

import type { StylistHandoff } from '../hooks/useAgentChat'

interface StylistHandoffCardProps {
  handoff: StylistHandoff
}

export default function StylistHandoffCard({ handoff }: StylistHandoffCardProps) {
  const reduceMotion = useReducedMotion()
  const subject = encodeURIComponent('Stylist handoff from Pellier concierge')
  const body = encodeURIComponent(
    `Reason routed to a stylist:\n${handoff.reason}\n\n` +
      (handoff.customer_id
        ? `Customer reference: ${handoff.customer_id}\n\n`
        : '') +
      'Stylist team, please pick this up from the concierge thread.\n',
  )
  const href = `mailto:${handoff.contact.mailto}?subject=${subject}&body=${body}`

  return (
    <motion.section
      data-testid="stylist-handoff-card"
      role="group"
      aria-label="Stylist handoff"
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        reduceMotion
          ? { duration: 0 }
          : { duration: 0.32, ease: [0.2, 0.9, 0.3, 1.05] }
      }
      style={{
        marginTop: 12,
        padding: '14px 16px',
        background: 'var(--cream-warm)',
        border: '1px dashed color-mix(in srgb, var(--accent) 42%, transparent)',
        borderRadius: 12,
        fontFamily: 'var(--sans)',
        color: 'var(--ink)',
        boxShadow: '0 1px 3px color-mix(in srgb, var(--ink) 6%, transparent)',
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
            background: 'var(--red-soft)',
            color: 'var(--accent)',
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
            color: 'var(--accent)',
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
          color: 'var(--ink-soft)',
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
            color: 'var(--ink-quiet)',
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
                  color: 'color-mix(in srgb, var(--accent) 70%, transparent)',
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
          borderTop: '1px solid color-mix(in srgb, var(--ink) 8%, transparent)',
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
            color: 'var(--ink-quiet)',
          }}
        >
          {handoff.contact.response_window}
        </span>
        <a
          data-testid="stylist-handoff-cta"
          href={href}
          className="stylist-handoff-cta"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 14px',
            minHeight: 44,
            borderRadius: 999,
            background: 'var(--ink)',
            color: 'var(--cream)',
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
