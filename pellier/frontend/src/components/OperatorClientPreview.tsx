/**
 * Read-only client context carried from Pellier Operator into the storefront.
 *
 * This is not impersonation. The record still comes from the operator-gated
 * API, the shopper persona is cleared before this renders, and every
 * consequential action remains on the operator action rail.
 */
import { ArrowLeft, ClipboardList, Eye, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { MEMBERSHIP } from '../data/membership'
import {
  fetchClientRecord,
  OperatorApiError,
  type OperatorClientRecord,
} from '../services/operator'
import { useEffect, useState } from 'react'

interface OperatorClientPreviewProps {
  customerId: string
  onClose: () => void
}

function money(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export default function OperatorClientPreview({
  customerId,
  onClose,
}: OperatorClientPreviewProps) {
  const [record, setRecord] = useState<OperatorClientRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setRecord(null)
    setError(null)

    fetchClientRecord(customerId)
      .then((next) => {
        if (active) setRecord(next)
      })
      .catch((caught: unknown) => {
        if (!active) return
        setError(
          caught instanceof OperatorApiError
            ? caught.code
            : 'operator_unavailable',
        )
      })

    return () => {
      active = false
    }
  }, [customerId])

  if (error) {
    return (
      <section
        className="w-full border-y border-sand bg-cream-warm"
        data-testid="operator-client-preview-error"
        aria-label="Operator client preview unavailable"
      >
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-container-x py-4">
          <div className="min-w-0">
            <p className="font-sans text-[12px] font-semibold uppercase text-accent-ink">
              Operator preview unavailable
            </p>
            <p className="mt-1 font-sans text-[14px] text-ink-soft">
              This client record requires an active Pellier Operator session.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link
              to="/operator"
              className="inline-flex min-h-10 items-center gap-2 border border-sand px-3 font-sans text-[13px] font-medium text-espresso hover:border-espresso"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Operator
            </Link>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-10 items-center justify-center border border-sand text-espresso hover:border-espresso"
              aria-label="Close client preview"
              title="Close client preview"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </section>
    )
  }

  if (!record) {
    return (
      <section
        className="w-full border-y border-sand bg-cream-warm"
        data-testid="operator-client-preview-loading"
        aria-label="Loading operator client preview"
      >
        <div className="mx-auto max-w-[1440px] px-container-x py-5 font-sans text-[14px] text-ink-soft">
          Reading client context from PostgreSQL...
        </div>
      </section>
    )
  }

  const { client, orders, tickets } = record
  const membership = MEMBERSHIP[client.membership]
  const openTickets = client.openTicketCount ?? 0
  const latestTicket = tickets.find((ticket) =>
    ['open', 'pending'].includes(ticket.status),
  )
  const recentPieces = orders.slice(0, 3).map((order) => order.productName)
  const evidenceConflict =
    client.returnEvidence?.unconfirmedReturnAssertion === true

  return (
    <section
      className="w-full border-y border-sand bg-cream-warm"
      data-testid="operator-client-preview"
      aria-label={`Operator preview for ${client.name}`}
    >
      <div className="mx-auto max-w-[1440px] px-container-x py-5 md:py-6">
        <div className="grid gap-5 md:grid-cols-[minmax(0,1.4fr)_minmax(220px,0.8fr)_auto] md:items-center md:gap-7">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 font-sans text-[12px] font-semibold uppercase text-accent-ink">
                <Eye className="h-3.5 w-3.5" aria-hidden />
                Operator client preview
              </span>
              <span className="border border-sand px-2 py-0.5 font-sans text-[11px] font-medium uppercase text-ink-quiet">
                Read-only
              </span>
            </div>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 className="font-display text-[26px] font-normal text-espresso md:text-[30px]">
                {client.name}
              </h2>
              <span className="font-sans text-[13px] text-ink-soft">
                {membership.label} · {membership.descriptor}
              </span>
            </div>
            <p className="mt-2 max-w-[760px] font-sans text-[14px] leading-6 text-ink-soft">
              {client.note}
            </p>
            {evidenceConflict ? (
              <p
                className="mt-3 border-l-2 border-accent-ink pl-3 font-sans text-[13px] leading-5 text-espresso"
                data-testid="operator-client-preview-evidence-conflict"
              >
                Service context says a return was received. The returns ledger
                contains {client.returnEvidence?.authoritativeReturnCount ?? 0}{' '}
                {(client.returnEvidence?.authoritativeReturnCount ?? 0) === 1 ? 'record' : 'records'}.
                {' '}These claims remain separate pending operator
                reconciliation.
              </p>
            ) : null}
          </div>

          <dl className="grid grid-cols-2 gap-x-5 gap-y-3 border-y border-sand py-4 md:border-x md:border-y-0 md:px-6 md:py-1">
            <div>
              <dt className="font-sans text-[11px] uppercase text-ink-quiet">
                Orders
              </dt>
              <dd className="mt-1 font-display text-[22px] text-espresso">
                {orders.length}
              </dd>
            </div>
            <div>
              <dt className="font-sans text-[11px] uppercase text-ink-quiet">
                Open cases
              </dt>
              <dd className="mt-1 font-display text-[22px] text-espresso">
                {openTickets}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="font-sans text-[11px] uppercase text-ink-quiet">
                Recent pieces
              </dt>
              <dd className="mt-1 font-sans text-[13px] leading-5 text-ink-soft">
                {recentPieces.length > 0
                  ? recentPieces.join(' · ')
                  : 'No orders on record'}
              </dd>
            </div>
            {latestTicket ? (
              <div className="col-span-2">
                <dt className="font-sans text-[11px] uppercase text-ink-quiet">
                  Current case
                </dt>
                <dd className="mt-1 font-sans text-[13px] leading-5 text-ink-soft">
                  {latestTicket.subject}
                </dd>
              </div>
            ) : null}
          </dl>

          <div className="flex flex-wrap items-center gap-2 md:w-[178px] md:flex-col md:items-stretch">
            <Link
              to={`/operator/clients/${encodeURIComponent(client.customerId)}`}
              className="inline-flex min-h-10 items-center justify-center gap-2 bg-espresso px-3 font-sans text-[13px] font-medium text-cream-warm hover:bg-dusk"
              data-testid="operator-client-preview-record"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Client record
            </Link>
            <Link
              to="/operator/reviews"
              className="inline-flex min-h-10 items-center justify-center gap-2 border border-sand px-3 font-sans text-[13px] font-medium text-espresso hover:border-espresso"
              data-testid="operator-client-preview-reviews"
            >
              <ClipboardList className="h-4 w-4" aria-hidden />
              Action queue
            </Link>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex min-h-10 items-center justify-center gap-2 px-3 font-sans text-[13px] text-ink-soft hover:text-espresso"
              data-testid="operator-client-preview-close"
            >
              <X className="h-4 w-4" aria-hidden />
              Close preview
            </button>
          </div>
        </div>

        <p className="sr-only">
          Twelve-month spend {money(client.spend12mo)}.
        </p>
      </div>
    </section>
  )
}
