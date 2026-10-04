/**
 * ProductAvailabilityPanel — live Aurora stock for one product.
 *
 * Three states, deliberately distinct:
 *
 *   reading      the inventory read is in flight
 *   read         `product_catalog.quantity` plus the per-warehouse rows
 *   not read     the read did not happen or returned no availability
 *
 * The third state exists so a failed read can never be presented as zero
 * stock. `availability: null` on the wire means "not read"; rendering that
 * as "0 units on hand" would be a fabricated claim about the authoritative
 * system, which is the one thing this surface must not do. Every state is
 * stated in words, never by color alone.
 *
 * The warehouse rows are the same `pellier.warehouse_inventory` join that
 * the Stock agent's `check_stock` tool reads, so a shopper-visible count and
 * a tool receipt cannot disagree about where stock sits.
 */
import type { ProductAvailability } from '../services/types'
import { PRODUCT_DETAIL } from '../copy'

interface ProductAvailabilityPanelProps {
  /** Live inventory, or `null` when the read did not produce one. */
  availability: ProductAvailability | null
  /** True while the product read is still in flight. */
  loading: boolean
}

function shipWindowLabel(
  min: number | null | undefined,
  max: number | null | undefined,
): string | null {
  if (typeof min !== 'number' || typeof max !== 'number') return null
  return PRODUCT_DETAIL.shipWindow(min, max)
}

export default function ProductAvailabilityPanel({
  availability,
  loading,
}: ProductAvailabilityPanelProps) {
  const wasRead = !loading && availability !== null
  const warehouses = availability?.warehouses ?? []

  return (
    <section
      data-testid="product-availability"
      data-state={loading ? 'reading' : wasRead ? 'read' : 'not-read'}
      aria-labelledby="product-availability-heading"
      className="rounded-[8px] border border-sand bg-cream-warm p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="product-availability-heading"
          className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-soft"
        >
          {PRODUCT_DETAIL.AVAILABILITY_HEADING}
        </h2>
        {/* The provenance label appears only when a read actually landed. */}
        {wasRead ? (
          <span
            data-testid="product-availability-source"
            className="font-sans text-[11px] uppercase tracking-[0.12em] text-accent-ink"
          >
            {PRODUCT_DETAIL.AVAILABILITY_SOURCE}
          </span>
        ) : null}
      </div>

      {loading ? (
        <p className="mt-3 font-sans text-[13px] text-ink-quiet">
          {PRODUCT_DETAIL.AVAILABILITY_READING}
        </p>
      ) : null}

      {!loading && !wasRead ? (
        <p
          data-testid="product-availability-degraded"
          className="mt-3 font-sans text-[13px] text-ink-soft"
        >
          {PRODUCT_DETAIL.AVAILABILITY_UNAVAILABLE}
        </p>
      ) : null}

      {wasRead && availability ? (
        <>
          <p className="mt-3 font-sans text-sm text-ink-soft">
            <strong
              data-testid="product-on-hand"
              className="font-mono text-base text-espresso"
            >
              {availability.onHand}
            </strong>{' '}
            {PRODUCT_DETAIL.ON_HAND_LABEL}
          </p>

          {warehouses.length > 0 ? (
            <>
              <ul
                data-testid="product-warehouses"
                className="mt-4 flex flex-col divide-y divide-sand border-t border-sand"
              >
                {warehouses.map((warehouse) => {
                  const ships = shipWindowLabel(
                    warehouse.shipWindowMin,
                    warehouse.shipWindowMax,
                  )
                  return (
                    <li
                      key={warehouse.warehouseId}
                      data-testid={`product-warehouse-${warehouse.warehouseId}`}
                      className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5"
                    >
                      <span className="font-sans text-[13px] text-espresso">
                        {warehouse.name}
                        <span className="ml-2 text-ink-quiet">{warehouse.city}</span>
                      </span>
                      <span className="flex items-baseline gap-3">
                        {ships ? (
                          <span className="font-sans text-[12px] text-ink-quiet">
                            {ships}
                          </span>
                        ) : null}
                        <span className="font-mono text-[13px] text-espresso">
                          {warehouse.quantity}
                        </span>
                      </span>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-3 font-sans text-[12px] text-ink-quiet">
                {PRODUCT_DETAIL.WAREHOUSE_CAPTION}
              </p>
            </>
          ) : (
            <p className="mt-3 font-sans text-[13px] text-ink-quiet">
              {PRODUCT_DETAIL.WAREHOUSE_EMPTY}
            </p>
          )}
        </>
      ) : null}
    </section>
  )
}
