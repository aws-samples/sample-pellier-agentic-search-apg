/**
 * PellierServiceStrip - retail assurances.
 *
 * The shipping and returns figures match `FOOTER.BOTTOM_STRIP.SERVICE_ITEMS`. If
 * one changes, change both: two different numbers for the same policy is the
 * kind of quiet contradiction a participant notices.
 */
import { Gift, Headset, RotateCcw, Truck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SERVICE_STRIP } from '../copy'

/** Icons are positional, matching `SERVICE_STRIP.ITEMS` order. */
const SERVICE_ICONS: LucideIcon[] = [Truck, RotateCcw, Gift, Headset]

export default function PellierServiceStrip() {
  return (
    <section
      data-testid="pellier-service-strip"
      aria-label="Pellier services"
      className="pellier-services"
    >
      <div className="pellier-services-inner">
        {SERVICE_STRIP.ITEMS.map((item, index) => {
          const ServiceIcon = SERVICE_ICONS[index] ?? Truck
          return (
            <div key={item.title} className="pellier-service">
              <span className="pellier-service-icon">
                <ServiceIcon size={19} strokeWidth={1.6} aria-hidden="true" />
              </span>
              <span className="pellier-service-copy">
                <strong>{item.title}</strong>
                <span>{item.body}</span>
              </span>
            </div>
          )
        })}

      </div>
    </section>
  )
}
