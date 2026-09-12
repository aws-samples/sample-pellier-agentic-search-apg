/**
 * PellierApproach - the storefront's bridge into Pellier Observatory.
 *
 * This is the one place the storefront names what sits behind it. Each claim
 * points at a surface a participant can open, which is what earns the module
 * its place: the storefront asserts that recommendations are grounded, and
 * the link is how a shopper checks.
 *
 * Copy lives in `PELLIER_APPROACH`. Do not add a pillar without a route that
 * substantiates it.
 */
import { motion, useReducedMotion } from 'framer-motion'
import { Compass, FileCheck2, Hand, Heart } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PELLIER_APPROACH } from '../copy'
import { splitHeadlineAtAccent } from '../utils/headlineAccent'
import ResponsiveImage from './ResponsiveImage'

/** Icons are positional, matching `PELLIER_APPROACH.PILLARS` order. */
const PILLAR_ICONS: LucideIcon[] = [FileCheck2, Compass, Hand, Heart]

export default function PellierApproach() {
  const reduceMotion = useReducedMotion()
  const bottomLine = splitHeadlineAtAccent(
    PELLIER_APPROACH.TITLE_BOTTOM,
    PELLIER_APPROACH.ACCENT,
  )

  return (
    <motion.section
      data-testid="pellier-approach"
      aria-labelledby="pellier-approach-title"
      className="pellier-approach"
      initial={reduceMotion ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{
        duration: reduceMotion ? 0 : 0.6,
        ease: [0.16, 1, 0.3, 1],
      }}
    >
      <div className="pellier-approach-inner">
        <div className="pellier-approach-media">
          <ResponsiveImage
            src={PELLIER_APPROACH.IMAGE}
            alt={PELLIER_APPROACH.IMAGE_ALT}
            widths={[480, 960]}
            sizes="(min-width: 1160px) 30vw, 100vw"
            loading="lazy"
            decoding="async"
            pictureClassName="block h-full w-full"
          />
        </div>

        <div className="pellier-approach-statement">
          <span className="pellier-eyebrow">{PELLIER_APPROACH.EYEBROW}</span>
          <h2 id="pellier-approach-title" className="pellier-statement">
            {PELLIER_APPROACH.TITLE_TOP}
            <br />
            {bottomLine.before}
            {bottomLine.accent ? <em>{bottomLine.accent}</em> : null}
            {bottomLine.after}
          </h2>
          <p>{PELLIER_APPROACH.BODY}</p>
          <Link
            to={PELLIER_APPROACH.CTA_HREF}
            className="pellier-action-quiet"
            data-testid="pellier-approach-cta"
          >
            {PELLIER_APPROACH.CTA_LABEL}
          </Link>
        </div>

        <ul className="pellier-approach-pillars">
          {PELLIER_APPROACH.PILLARS.map((pillar, index) => {
            const PillarIcon = PILLAR_ICONS[index] ?? FileCheck2
            return (
              <li key={pillar.title} className="pellier-pillar">
                <span className="pellier-pillar-icon">
                  <PillarIcon size={19} strokeWidth={1.6} aria-hidden="true" />
                </span>
                <h3>{pillar.title}</h3>
                <p>{pillar.body}</p>
                {pillar.href.startsWith('/#') ? (
                  <a className="pellier-pillar-link" href={pillar.href}>
                    {pillar.linkLabel}
                  </a>
                ) : (
                  <Link className="pellier-pillar-link" to={pillar.href}>
                    {pillar.linkLabel}
                  </Link>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </motion.section>
  )
}
