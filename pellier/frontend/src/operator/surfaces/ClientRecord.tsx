/**
 * One client record: standing, order history, tickets, credits, and the
 * governed review path an operator can enter through Concierge.
 *
 * Consequential actions are deliberately absent from the record itself. The
 * Concierge prepares one exact proposal, Action Queue records the human
 * decision, and only the confirmed review can reach execution.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { MEMBERSHIP } from '../../data/membership'
import {
  fetchClientRecord,
  OperatorApiError,
  type OperatorClientRecord,
} from '../../services/operator'
import { imageSrc } from '../../utils/assetPath'
import ResponsiveImage from '../../components/ResponsiveImage'
import ServiceSource from '../components/ServiceSource'
import ClientAvatar from '../components/ClientAvatar'
import OperatorConcierge from '../concierge/OperatorConcierge'
import MembershipRung from '../components/MembershipRung'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState from '../components/OperatorState'
import ReplacementCare from '../components/ReplacementCare'

function money(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

/**
 * The record head's plate.
 *
 * Only the three storefront-switchable heroes have a full-bleed photograph,
 * and they get their OWN storefront hero: opening Marco's record shows the
 * advisor the room Marco shops in, which is the whole reason this desk sits
 * next to a shop rather than inside a CRM. An explicit map rather than
 * `hero-${personaId}.png`, so an unrecognised persona degrades to the house
 * ground instead of requesting an asset that does not exist.
 *
 * Everyone else gets the house ground: identical geometry, identical type,
 * no photograph. One design, one of two grounds.
 */
const PERSONA_PLATES: Record<string, string> = {
  marco: '/products/hero-marco.png',
  anna: '/products/hero-anna.png',
  theo: '/products/hero-theo.png',
}

function shortDate(iso: string | null): string {
  if (!iso) return '—'
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime())
    ? '—'
    : parsed.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
}

const ClientRecordPage: React.FC = () => {
  const { customerId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [guidedServiceRecovery] = useState(
    () =>
      new URLSearchParams(location.search).get('guided') ===
      'service-recovery',
  )
  const [record, setRecord] = useState<OperatorClientRecord | null>(null)
  const [retryVersion, setRetryVersion] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    let active = true
    fetchClientRecord(customerId)
      .then((data) => {
        if (active) {
          setRecord(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(
          err instanceof OperatorApiError ? err.code : 'operator_unavailable',
        )
      })
    return () => {
      active = false
    }
  }, [customerId])

  useEffect(load, [load, retryVersion])

  useEffect(() => {
    if (!guidedServiceRecovery || !location.search) return
    navigate(`${location.pathname}${location.hash}`, { replace: true })
  }, [
    guidedServiceRecovery,
    location.hash,
    location.pathname,
    location.search,
    navigate,
  ])

  // Client data arrives after the route mounts. Reveal the existing chat once
  // its target exists; opening it still resumes history without submitting.
  useEffect(() => {
    if (!record || !['#operator-concierge', '#operator-concierge-title'].includes(location.hash)) return
    const target = window.matchMedia('(min-width: 1081px)').matches
      ? 'operator-client-record'
      : 'operator-concierge'
    document.getElementById(target)?.scrollIntoView({ block: 'start', behavior: 'instant' })
  }, [record, location.hash])

  if (error) {
    const authenticationRequired =
      error === 'authentication_required' || error === 'invalid_credentials'
    const operatorRequired = error === 'operator_group_required'
    const unavailable = error === 'operator_unavailable'
    return (
      <OperatorState
        level={1}
        data-testid="operator-record-error"
        surface={authenticationRequired ? 'plate' : 'paper'}
        eyebrow="Client record"
        lead={
          <Link to="/operator" className="operator-back">
            Clients
          </Link>
        }
        headline={
          authenticationRequired
            ? 'Operator sign-in required'
            : operatorRequired
              ? 'Operator access required'
              : unavailable
                ? 'Operator is temporarily unavailable'
                : 'Record unavailable'
        }
        body={
          authenticationRequired ? (
            <>
              Sign in with the workshop operator account to read this client
              record. No database request was attempted.
            </>
          ) : operatorRequired ? (
            <>
              This signed-in account is not a member of the operator group. No
              database request was attempted.
            </>
          ) : unavailable ? (
            <>
              The governed service could not be reached for{' '}
              <code>{customerId}</code>. No current client record was returned.
            </>
          ) : (
            <>
              The live database did not return a record for{' '}
              <code>{customerId}</code>.
            </>
          )
        }
        reason={error}
        action={authenticationRequired ? <OperatorSignInAction unlocks="open this client record" /> : !operatorRequired ? <button type="button" className="operator-button operator-button-inline" onClick={() => setRetryVersion(v => v + 1)}>Try again</button> : undefined}
      />
    )
  }

  if (!record) {
    return (
      <OperatorState
        level={1}
        data-testid="operator-record-loading"
        eyebrow="Client record"
        headline="Reading the client record from Aurora…"
      />
    )
  }

  const { client, orders, tickets, credits, returns } = record
  const currentRequest = tickets.find(
    (ticket) => ticket.status === 'open' || ticket.status === 'pending',
  )
  const returnEvidence = client.returnEvidence

  const membershipLabel = `${MEMBERSHIP[client.membership].label} \u00b7 ${
    MEMBERSHIP[client.membership].descriptor
  }`
  const plate = client.personaId ? PERSONA_PLATES[client.personaId] : undefined

  return (
    // Two panes, both first class. The record keeps every field and interaction it
    // had; the Concierge is ADDED beside it rather than replacing it, so the left
    // column is not reduced to a SaaS sidebar.
    <div className="operator-workbench" data-testid="operator-record">
      {/* Destination, then the record's own identifier. The customer id is
          the value an operator pastes into a query, so it is shown as data
          rather than hidden.

          Above the two columns, not inside the record one. As a child of the
          left column it pushed the record band down by its own height while
          the Concierge card started at the grid's top edge, so the two panes
          opened on different content and read as misaligned. */}
      <nav className="operator-crumb" aria-label="Breadcrumb">
        <Link to="/operator" className="operator-back">
          Clients
        </Link>
        <span className="operator-crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="operator-crumb-id">{client.customerId}</span>
      </nav>
      <nav className="operator-record-jumps" aria-label="Client record sections">
        <a href="#operator-client-record">Record</a>
        <a href="#operator-concierge">Operator chat</a>
        <a href="#operator-client-activity">Activity</a>
      </nav>
      <div className="operator-workbench-record" id="operator-client-record">

      {/* An editorial band, not a row of fields: portrait, name in the display
          face, rung, and the one link back to the shop. The governance note
          that used to sit inside it now follows on paper, where 13px prose is
          legible and where it belongs — it is guidance for the operator, not
          part of the client's identity. */}
      <header
        className="operator-record-head"
        data-plate={plate ? 'persona' : 'house'}
      >
        {plate ? (
          <ResponsiveImage
            src={plate}
            widths={[960, 1600]}
            sizes="(max-width: 1080px) 100vw, 780px"
            pictureClassName="operator-record-plate"
            className="operator-record-plate-image"
            alt=""
            aria-hidden="true"
            decoding="async"
          />
        ) : null}
        <div className="operator-record-head-inner">
          <ClientAvatar
            customerId={client.customerId}
            name={client.name}
            personaId={client.personaId}
            size="lg"
          />
          {/* Name and rung on one line, the client's own note under it, the
              handoff last. A right-hand standing column read as a second
              layout the moment the band sat in the 52% record pane: the name
              wrapped to two lines and the note broke into four. */}
          <div className="operator-record-identity">
            <div className="operator-record-headline">
              <h1 className="operator-title">{client.name}</h1>
              <MembershipRung membership={client.membership} describe />
            </div>
            <p className="operator-lede">{client.note}</p>
            <div className="operator-standing">
              <div className="operator-standing-row">
                <span>Storefront</span>
                <Link
                  to={
                    client.personaId
                      ? `/?persona=${encodeURIComponent(client.personaId)}`
                      : `/?clientPreview=${encodeURIComponent(client.customerId)}`
                  }
                  className="operator-back"
                  data-testid="operator-storefront-handoff"
                >
                  {client.personaId
                    ? `Open ${client.name.split(' ')[0]}'s storefront`
                    : 'Preview client context'}
                </Link>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="operator-record-context">
        <ServiceSource service="aurora">Client record and transaction history</ServiceSource>
        <details className="operator-source-details"><summary>Standing and authority</summary>
          <p>{MEMBERSHIP[client.membership].earns}. Standing is business context. For tools exposed through Gateway, AgentCore Policy decides whether the action is permitted. Aurora still decides whether the data may be changed.</p>
        </details>
      </div>

      {currentRequest ? (
        <section
          className="operator-service-request"
          data-conflict={
            returnEvidence?.unconfirmedReturnAssertion ? 'true' : 'false'
          }
          data-testid="operator-service-request"
          aria-labelledby="operator-service-request-title"
        >
          <div className="operator-service-request-head">
            <span className="operator-service-request-ticket">
              {currentRequest.ticketId}
            </span>
            {/* A dot and a phrase, not a shouted pill. The phrase names the
                state an operator has to act on: an assertion no authoritative
                row backs needs verifying, and anything else is just the
                ticket's own status. */}
            <span
              className="operator-service-request-state"
              data-status={currentRequest.status}
            >
              <span className="operator-service-request-dot" aria-hidden="true" />
              {returnEvidence?.unconfirmedReturnAssertion
                ? 'Needs verification'
                : currentRequest.status}
            </span>
          </div>
          <h2 id="operator-service-request-title">
            {currentRequest.subject}
          </h2>
          {/*
            * The disagreement, side by side.
            *
            * This card exists because a support ticket can ASSERT a return
            * while the database holds no row for it, and the console's job is
            * to show that rather than resolve it by guessing. Two columns make
            * the two claims comparable; a stacked list made them read as one
            * account of events. The right column is labelled by what it is,
            * not by the product behind it, because the same build runs on
            * local PostgreSQL and on Aurora.
            */}
          <div className="operator-service-request-claims">
            <div>
              <span className="operator-service-request-claim-label">
                Client report
              </span>
              <p>{currentRequest.lastNote}</p>
            </div>
            <div>
              <span className="operator-service-request-claim-label">
                {record.dataSource ? `${record.dataSource} record` : 'System of record'}
              </span>
              <p>
                {returnEvidence?.authoritativeReturnCount ?? returns.length}{' '}
                authoritative{' '}
                {(returnEvidence?.authoritativeReturnCount ?? returns.length) === 1
                  ? 'row'
                  : 'rows'}{' '}
                in the returns ledger
              </p>
            </div>
          </div>
          <div className="operator-service-request-foot">
            <p className="operator-service-request-next">
              {returnEvidence?.unconfirmedReturnAssertion
                ? 'Reconcile the assertion before promising an outcome.'
                : 'Investigate the request against current records.'}
            </p>
            <a
              href="#operator-concierge-title"
              className="operator-service-request-action"
            >
              Investigate case
            </a>
          </div>
        </section>
      ) : null}

      {client.personaId === 'theo' ? <ReplacementCare key={client.customerId} record={record} /> : null}

      {/* Four figures an advisor needs before speaking. */}
      <div className="operator-quad" data-testid="operator-quad">
        <div className="operator-quad-cell">
          <div className="operator-quad-label">12-month spend</div>
          <div className="operator-quad-value">{money(client.spend12mo)}</div>
          <div className="operator-quad-note">
            Membership is derived from this figure.
          </div>
        </div>
        <div className="operator-quad-cell">
          <div className="operator-quad-label">Store credit</div>
          <div
            className="operator-quad-value"
            data-tone={client.creditBalanceCents ? 'authority' : 'quiet'}
          >
            {money((client.creditBalanceCents ?? 0) / 100)}
          </div>
          <div className="operator-quad-note">
            {credits.length === 0
              ? 'Nothing on file.'
              : `${credits.length} credit${credits.length === 1 ? '' : 's'} on file.`}
          </div>
        </div>
        <div className="operator-quad-cell">
          <div className="operator-quad-label">Order value</div>
          <div className="operator-quad-value">{money(client.orderValue)}</div>
          <div className="operator-quad-note">
            {orders.length === 0
              ? 'No orders on record.'
              : `Across ${orders.length} order${orders.length === 1 ? '' : 's'}.`}
          </div>
        </div>
        <div className="operator-quad-cell">
          <div className="operator-quad-label">Open tickets</div>
          <div
            className="operator-quad-value"
            data-tone={client.openTicketCount ? 'authority' : 'quiet'}
          >
            {client.openTicketCount ?? 0}
          </div>
          <div className="operator-quad-note">
            {client.openTicketCount
              ? 'Awaiting a decision.'
              : 'Nothing outstanding.'}
          </div>
        </div>
      </div>

      <div className="operator-record" id="operator-client-activity">
        <nav className="operator-activity-nav" aria-label="Client activity"><a href="#operator-orders">Orders</a><a href="#operator-tickets">Support</a><a href="#operator-credits">Credits</a></nav>
        <div>
          <section
            className="operator-card operator-orders"
            data-testid="operator-orders" id="operator-orders"
          >
            <h2 className="operator-card-title">
              Order history <span>{orders.length}</span>
            </h2>
            {orders.length === 0 ? (
              <p className="operator-hint">No orders on record.</p>
            ) : (
              <div className="operator-table-wrap">
                <table className="operator-table">
                <thead>
                  <tr>
                    <th />
                    <th className="operator-order-piece">Piece</th>
                    <th className="operator-col-optional">Placed</th>
                    <th className="operator-table-num">Qty</th>
                    <th className="operator-table-num">Price</th>
                    <th className="operator-table-num">ID</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr key={order.orderId}>
                      <td>
                        <OrderThumb
                          src={order.imageUrl}
                          name={order.productName}
                        />
                      </td>
                      <td className="operator-order-piece">
                        {/* Move 3: the order history is a ledger of PIECES.
                            The name takes the storefront's product register so
                            an advisor recognises what the client owns rather
                            than reading a string in a cell. */}
                        <span className="operator-piece-name">
                          {order.productName}
                        </span>
                        <div className="operator-cell-note">{order.brand}</div>
                      </td>
                      <td className="operator-table-date operator-col-optional">
                        {shortDate(order.placedAt)}
                      </td>
                      <td className="operator-table-num">{order.quantity}</td>
                      <td className="operator-table-num">
                        {money(order.price)}
                      </td>
                      <td className="operator-table-id">
                        {order.productId}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </section>

          <section className="operator-card" data-testid="operator-tickets" id="operator-tickets">
            <h2 className="operator-card-title">
              Support history <span>{tickets.length}</span>
            </h2>
            {tickets.length === 0 ? (
              <p className="operator-hint">
                No tickets on record for this client.
              </p>
            ) : (
              <div className="operator-table-wrap">
                <table className="operator-table">
                <thead>
                  <tr>
                    <th className="operator-col-optional">Ticket</th>
                    <th>Subject</th>
                    <th>Status</th>
                    <th className="operator-col-optional">Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {tickets.map((ticket) => (
                    <tr key={ticket.ticketId}>
                      <td className="operator-table-id operator-col-optional">
                        {ticket.ticketId}
                      </td>
                      <td>
                        {ticket.subject}
                        <div className="operator-cell-note">
                          {ticket.lastNote}
                        </div>
                      </td>
                      <td>
                        <span
                          className="operator-status"
                          data-status={ticket.status}
                        >
                          {ticket.status}
                        </span>
                      </td>
                      <td className="operator-table-date operator-col-optional">
                        {shortDate(ticket.openedAt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </section>

          <section className="operator-card" data-testid="operator-credits" id="operator-credits">
            <h2 className="operator-card-title">
              Store credits
              {client.creditBalanceCents ? (
                <span>${client.creditBalance}</span>
              ) : null}
            </h2>
            {credits.length === 0 ? (
              <p className="operator-hint">No credits issued.</p>
            ) : (
              <div className="operator-table-wrap">
                <table className="operator-table">
                <thead>
                  <tr>
                    <th>Reason</th>
                    <th className="operator-col-optional">Issued</th>
                    <th>By</th>
                    <th className="operator-table-num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {credits.map((credit) => (
                    <tr key={credit.creditId}>
                      <td>{credit.reason}</td>
                      <td className="operator-table-date operator-col-optional">
                        {shortDate(credit.createdAt)}
                      </td>
                      <td className="operator-table-id">
                        {credit.issuedBy ?? 'seed'}
                      </td>
                      <td className="operator-table-num">${credit.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </section>
        </div>

      </div>
      </div>

      <div className="operator-workbench-concierge">
        <OperatorConcierge
          clientId={client.customerId}
          clientName={client.name}
          membershipLabel={membershipLabel}
          spendLabel={`${money(client.spend12mo)} \u00b7 12mo spend`}
          record={record}
          guidedServiceRecovery={guidedServiceRecovery}
        />
      </div>
    </div>
  )
}

/** Product thumbnail with a designed fallback tile, never a grey box. */
const OrderThumb: React.FC<{ src: string; name: string }> = ({ src, name }) => {
  const [failed, setFailed] = useState(false)
  // Resolved through imageSrc: a bare root-relative path 404s behind the
  // Workshop Studio `/ports/8000/` proxy.
  const resolved = imageSrc(src)
  if (!resolved || failed) {
    return (
      <span className="operator-thumb-fallback" aria-hidden="true">
        {name.slice(0, 1).toUpperCase()}
      </span>
    )
  }
  return (
    <img
      src={resolved}
      alt=""
      aria-hidden="true"
      className="operator-thumb"
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  )
}

const ClientRecord: React.FC = () => {
  const { customerId } = useParams()
  return <ClientRecordPage key={customerId} />
}

export default ClientRecord
