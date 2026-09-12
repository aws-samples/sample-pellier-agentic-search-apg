/**
 * The book — every client, richest standing first.
 *
 * Reads the operator-gated `GET /api/operator/clients`. Membership counts
 * come from the API rather than being recomputed here, so the summary cannot
 * disagree with the rows.
 */

import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  MEMBERSHIP,
  MEMBERSHIP_RUNGS,
  type Membership,
} from '../../data/membership'
import { useClientBook } from '../hooks/useClientBook'
import ServiceSource from '../components/ServiceSource'
import ClientAvatar from '../components/ClientAvatar'
import MembershipRung from '../components/MembershipRung'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState from '../components/OperatorState'

/**
 * How many rows the entrance stagger walks before it stops adding delay.
 *
 * A count, not a duration: 12 x 26ms puts the last staggered row at 312ms,
 * which is inside the window where a sequence still reads as one gesture. Past
 * that an operator has begun reading the top of the book, and a row still
 * arriving underneath is a distraction rather than an arrival.
 */
const ENTRANCE_STAGGER_CAP = 12

function money(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

const BOOK_VIEW_KEY = 'pellier-operator-book-view'
function savedBookView(key = BOOK_VIEW_KEY): { query?: string; rung?: Membership | null; scroll?: number } {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || '{}')
    if (!value || typeof value !== 'object') return {}
    return {
      query: typeof value.query === 'string' ? value.query : '',
      rung: MEMBERSHIP_RUNGS.includes(value.rung) ? value.rung : null,
      scroll: Number.isFinite(value.scroll) ? value.scroll : 0,
    }
  } catch { return {} }
}

const ClientBook: React.FC<{ intent?: 'record' | 'chat' }> = ({ intent = 'record' }) => {
  const navigate = useNavigate()
  const { book, error, refresh } = useClientBook()
  const [params, setParams] = useSearchParams()
  const chatEntry = intent === 'chat'
  const viewKey = chatEntry ? 'pellier-operator-chat-view' : BOOK_VIEW_KEY
  const [initialView] = useState(() => savedBookView(viewKey))
  // Client-side: the whole book is already loaded, so filtering needs no
  // round trip. Null means "no filter", not "registered".
  const requestedRung = params.get('membership')
  const rungFilter: Membership | null = requestedRung == null
    ? initialView.rung ?? null
    : MEMBERSHIP_RUNGS.includes(requestedRung as Membership) ? requestedRung as Membership : null
  const setRungFilter = (rung: Membership | null) => {
    setParams(current => {
      const next = new URLSearchParams(current)
      next.set('membership', rung ?? 'all')
      return next
    })
  }
  // Typed name filter. Fifteen clients fit on one screen; forty do not, and an
  // associate who knows the name should not have to scan the ladder for it.
  const [query, setQuery] = useState(() => initialView.query ?? '')

  useEffect(() => {
    if (params.has('membership') || !initialView.rung) return
    setParams(current => {
      const next = new URLSearchParams(current)
      next.set('membership', initialView.rung!)
      return next
    }, { replace: true })
  }, [initialView.rung, params, setParams])

  const rememberPosition = () => {
    try { sessionStorage.setItem(viewKey, JSON.stringify({ query, rung: rungFilter, scroll: window.scrollY })) } catch { /* Storage can be disabled. */ }
  }
  useEffect(() => {
    if (!book) return
    const scroll = savedBookView(viewKey).scroll
    if (typeof scroll === 'number' && scroll > 0) window.scrollTo({ top: scroll, behavior: 'instant' })
  }, [book, viewKey])

  if (error) {
    const authenticationRequired =
      error === 'authentication_required' || error === 'invalid_credentials'
    const operatorRequired = error === 'operator_group_required'
    const unavailable = error === 'operator_unavailable'
    return (
      <OperatorState
        level={1}
        data-testid="operator-book-error"
        surface={authenticationRequired ? 'plate' : 'paper'}
        eyebrow="Client book"
        headline={
          authenticationRequired
            ? 'Operator sign-in required'
            : operatorRequired
              ? 'Operator access required'
              : unavailable
                ? 'Operator is temporarily unavailable'
                : 'The book is unavailable'
        }
        body={
          authenticationRequired ? (
            <>
              Sign in with the workshop operator account to read the client
              book. No database request was attempted.
            </>
          ) : operatorRequired ? (
            <>
              This signed-in account is not a member of the operator group. No
              database request was attempted.
            </>
          ) : unavailable ? (
            <>
              The governed service could not be reached, so no current client
              book was returned.
            </>
          ) : (
            <>
              The live database did not return the client list. If this is a
              fresh deployment, confirm migration{' '}
              <code>018_client_book.sql</code> has been applied.
            </>
          )
        }
        reason={unavailable ? undefined : error}
        action={authenticationRequired ? <OperatorSignInAction unlocks="read the client book" /> : !operatorRequired ? <button type="button" className="operator-button operator-button-inline" onClick={refresh}>Try again</button> : undefined}
      />
    )
  }

  if (!book) {
    return (
      <OperatorState
        level={1}
        data-testid="operator-book-loading"
        eyebrow="Client book"
        headline="Reading the live client book…"
      />
    )
  }

  const needle = query.trim().toLowerCase()
  const visible = book.clients.filter(
    (c) =>
      (!rungFilter || c.membership === rungFilter) &&
      (!needle ||
        c.name.toLowerCase().includes(needle) ||
        c.slug.toLowerCase().includes(needle) ||
        (c.note ?? '').toLowerCase().includes(needle)),
  )
  const jessicaCase = book.clients.find(
    (client) =>
      client.slug === 'jessica' &&
      /return|dispute|service/i.test(client.note),
  )
  const theo = book.clients.find(client => client.personaId === 'theo')

  // The entrance stagger walks the rendered order, so it has to be counted
  // where the rows are emitted rather than derived from an array index: a
  // section header and a client row are both children of the book, and only
  // the DOM knows the interleaving.
  let entranceStep = 0
  const entranceIndex = () =>
    Math.min(entranceStep++, ENTRANCE_STAGGER_CAP)

  // Richest rung first, and a rung with nobody in it is not a section.
  const sections = [...MEMBERSHIP_RUNGS]
    .reverse()
    .map((rung) => ({
      rung,
      clients: visible.filter((c) => c.membership === rung),
    }))
    .filter((section) => section.clients.length > 0)

  if (book.total === 0) {
    return (
      <OperatorState
        level={1}
        data-testid="operator-book-empty"
        eyebrow="Client book"
        headline="No clients seeded"
        body={
          <>
            The desk is wired but <code>pellier.customers</code> holds no
            client rows. Apply <code>018_client_book.sql</code> to seed the
            book.
          </>
        }
      />
    )
  }

  return (
    <div data-testid="operator-book" data-intent={intent}>
      {/* An introduction to the surface rather than a label for it: an advisor
          arriving here needs to know what they can do, not what the list is
          called. No kicker above the heading. */}
      <h1 className="operator-title">{chatEntry ? 'Operator chat' : 'Every client the house knows'}</h1>
      <p className="operator-lede">{chatEntry
        ? 'Choose a client to ask questions, examine the source records, and work toward a fair resolution.'
        : 'Open a client, investigate the evidence, and prepare a resolution for human review.'}</p>
      <details className="operator-source-details">
        <summary>How the desk works</summary>
        <div className="operator-service-sources">
          <ServiceSource service="aurora">Customer records, orders, inventory, and the audit ledger</ServiceSource>
          <ServiceSource service="agentcore">Governed tools, identity, and policy evaluation</ServiceSource>
        </div>
        <p>Operator Concierge runs a separate investigation and resolution graph over the same Aurora records the storefront reads. A person confirms the exact terms before policy and Aurora independently decide what may execute.</p>
      </details>

      {jessicaCase ? (
        <section
          className="operator-case-entry"
          data-testid="operator-jessica-case-entry"
          aria-labelledby="operator-jessica-case-title"
        >
          <ClientAvatar
            customerId={jessicaCase.customerId}
            name={jessicaCase.name}
            personaId={jessicaCase.personaId}
          />
          <div className="operator-case-entry-copy">
            {/* Name and standing on one line, then what is happening, then the
                client's brief. Three levels of decreasing weight rather than
                labelled columns: the labels were carrying facts the sentences
                already say. */}
            <div className="operator-case-entry-headline">
              <h2 id="operator-jessica-case-title">{jessicaCase.name}</h2>
              <span className="operator-case-entry-kicker">Service recovery</span>
            </div>
            {jessicaCase.openCase ? (
              <p className="operator-case-entry-case">{jessicaCase.openCase}</p>
            ) : null}
            <p className="operator-case-entry-brief">{jessicaCase.note}</p>
          </div>
          <div className="operator-case-entry-actions">
            <Link
              to={`/operator/clients/${encodeURIComponent(jessicaCase.customerId)}#operator-concierge`}
              className="operator-case-entry-action"
              onClick={rememberPosition}
              aria-label={`Open chat for ${jessicaCase.name}`}
            >
              Open chat
            </Link>
            <button
              type="button"
              className="operator-case-entry-guided"
              onClick={() => {
                rememberPosition()
                navigate(
                  `/operator/clients/${jessicaCase.customerId}` +
                    '?guided=service-recovery#operator-concierge-title',
                )
              }}
            >
              Start guided review
            </button>
            <span>A guided review starts a new investigation.</span>
          </div>
        </section>
      ) : null}

      {theo ? <section className="operator-case-entry" aria-labelledby="operator-theo-care-title">
        <ClientAvatar customerId={theo.customerId} name={theo.name} personaId={theo.personaId} />
        <div className="operator-case-entry-copy">
          <div className="operator-case-entry-headline">
            <h2 id="operator-theo-care-title">{theo.name}</h2>
            <span className="operator-case-entry-kicker">Replacement care</span>
          </div>
          <p className="operator-case-entry-brief">Review the exact order, discuss the remedy, and follow any approved replacement through fulfillment.</p>
        </div>
        <div className="operator-case-entry-actions">
          <Link className="operator-case-entry-action" onClick={rememberPosition} to={`/operator/clients/${encodeURIComponent(theo.customerId)}#operator-concierge`}>Open Theo’s chat</Link>
          <Link className="operator-case-entry-guided" onClick={rememberPosition} to={`/operator/clients/${encodeURIComponent(theo.customerId)}#operator-replacement-care`}>Open replacement care</Link>
        </div>
      </section> : null}

      <label className="operator-search" htmlFor="operator-book-search">
        <span>Find a client</span>
        <input
          id="operator-book-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name or note"
          autoComplete="off"
          data-testid="operator-book-search"
        />
      </label>

      {/* The ladder, defined where the choice is made. */}
      <div className="operator-ladder" data-testid="operator-book-summary">
        {MEMBERSHIP_RUNGS.map((rung: Membership) => {
          const active = rungFilter === rung
          const count = book.byMembership[rung] ?? 0
          return (
            <button
              type="button"
              className="operator-ladder-cell"
              key={rung}
              aria-pressed={active}
              data-rung={rung}
              data-testid={`operator-ladder-${rung}`}
              // A count beside a label already implies a filter. Clicking
              // again clears it rather than trapping the operator in a subset.
              onClick={() => setRungFilter(active ? null : rung)}
              title={
                active
                  ? `Showing ${MEMBERSHIP[rung].label} only. Click to show all.`
                  : `Show only ${MEMBERSHIP[rung].label} clients`
              }
            >
              <span className="operator-ladder-head">
                <MembershipRung membership={rung} />
                {/* The label is the brand; the descriptor is the
                    comprehension. An advisor new to the ladder still knows
                    what "private client" means. */}
                <span className="operator-ladder-descriptor">
                  {MEMBERSHIP[rung].descriptor}
                </span>
                <span className="operator-ladder-count">{count}</span>
              </span>
              <span className="operator-ladder-threshold">
                {MEMBERSHIP[rung].threshold}
              </span>
              <span className="operator-ladder-earns">
                {MEMBERSHIP[rung].earns}
              </span>
            </button>
          )
        })}
      </div>

      {rungFilter || needle ? (
        <p className="operator-filter-note" data-testid="operator-filter-note">
          <span>
            Showing {visible.length} of {book.total}
            {rungFilter ? ` · ${MEMBERSHIP[rungFilter].label}` : ''}
            {needle ? ` · matching "${query.trim()}"` : ''}
          </span>
          <button
            type="button"
            className="operator-filter-clear"
            onClick={() => {
              setRungFilter(null)
              setQuery('')
            }}
            data-testid="operator-filter-clear"
          >
            Show all clients
          </button>
        </p>
      ) : null}

      <div className="operator-book">
        {/* Unfiltered, the list is grouped and the mark appears once per
            section. Filtered, the caption above already names the rung, so
            neither headers nor per-row pills are repeated. */}
        {sections.map(({ rung, clients }) => (
          <React.Fragment key={rung}>
            {rungFilter ? null : (
              <div
                className="operator-section"
                data-rung={rung}
                style={
                  { '--op-row-index': entranceIndex() } as React.CSSProperties
                }
              >
                <MembershipRung membership={rung} />
                {/* Identity and benefit are separated by space, not a
                    middle dot: joined by a dot they read as one long
                    sentence. */}
                <span className="operator-section-descriptor">
                  {MEMBERSHIP[rung].descriptor}
                </span>
                <span className="operator-section-earns">
                  {MEMBERSHIP[rung].earns}
                </span>
                <span className="operator-section-count">
                  {clients.length}
                </span>
              </div>
            )}
            {clients.map((client) => (
          <Link
            key={client.customerId}
            to={`/operator/clients/${encodeURIComponent(client.customerId)}${chatEntry ? '#operator-concierge' : ''}`}
            className={`operator-book-row${chatEntry ? ' operator-chat-client-row' : ''}`}
            data-testid={`operator-client-${client.slug}`}
            style={{ '--op-row-index': entranceIndex() } as React.CSSProperties}
            onClick={rememberPosition}
          >
            <ClientAvatar
              customerId={client.customerId}
              name={client.name}
              personaId={client.personaId}
            />
            <span>
              <span className="operator-client-name">{client.name}</span>
              <span className="operator-client-note">{client.note}</span>
            </span>
            {chatEntry ? (
              <span className="operator-client-chat-label">Open chat</span>
            ) : <>
            <span className="operator-figure">
              <span className="operator-figure-label">12-month spend</span>
              {money(client.spend12mo)}
            </span>
            <span className="operator-figure">
              <span className="operator-figure-label">Orders</span>
              {client.orderCount}
            </span>
            </>}
          </Link>
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

export default ClientBook
