/**
 * The clients: who has an open request, and what they last ordered.
 *
 * The desk's first column. No tiers, no spend: the list shows what staff act
 * on. Reads the staff-gated `GET /api/operator/clients`; the counts come from
 * the API so the summary cannot disagree with the rows.
 */
import React from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { StatusTag } from '../../components/turn'
import { useClientBook } from '../hooks/useClientBook'
import type { OperatorClient } from '../../services/operator'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState, { describeOperatorError } from '../components/OperatorState'

export function shortDate(iso: string | null): string | null {
  if (!iso) return null
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime())
    ? null
    : parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function lastOrderLine(client: OperatorClient): string {
  if (!client.lastOrder) return 'No orders yet'
  const when = shortDate(client.lastOrder.placedAt)
  return when ? `${client.lastOrder.productName}, ${when}` : client.lastOrder.productName
}

const ClientRow: React.FC<{ client: OperatorClient; selected: boolean }> = ({ client, selected }) => (
  <li>
    <NavLink
      to={`/operator/clients/${encodeURIComponent(client.customerId)}`}
      className="op-row"
      aria-current={selected ? 'page' : undefined}
      data-testid={`operator-client-${client.slug}`}
    >
      <ClientAvatar customerId={client.customerId} name={client.name} personaId={client.personaId} />
      <span className="op-row-body">
        <span className="op-row-head">
          <span className="op-row-name">{client.name}</span>
          {client.openRequests > 0 ? (
            <StatusTag tone="pending" pulse>
              {client.openRequests === 1 ? '1 open request' : `${client.openRequests} open requests`}
            </StatusTag>
          ) : null}
        </span>
        <span className="op-row-line">
          {client.openRequest ? client.openRequest : lastOrderLine(client)}
        </span>
        {client.openRequest ? <span className="op-row-sub">{lastOrderLine(client)}</span> : null}
      </span>
    </NavLink>
  </li>
)

/** The list, as the desk's rail. Also the index page's only content. */
export const ClientList: React.FC = () => {
  const { book, error, refresh } = useClientBook()
  const { customerId = '' } = useParams()

  if (error) {
    const described = describeOperatorError(error, 'read the clients')
    return (
      <OperatorState
        level={2}
        data-testid="operator-book-error"
        eyebrow="Clients"
        headline={described.headline}
        body={described.body}
        reason={error === 'operator_unavailable' ? undefined : error}
        action={described.signIn
          ? <OperatorSignInAction unlocks="read the clients" />
          : error !== 'operator_group_required'
            ? <button type="button" className="op-button op-button-quiet" onClick={refresh}>Try again</button>
            : undefined}
      />
    )
  }
  if (!book) {
    return <OperatorState level={2} data-testid="operator-book-loading" eyebrow="Clients" headline="Reading the clients" busy />
  }
  if (book.total === 0) {
    return (
      <OperatorState
        level={2}
        data-testid="operator-book-empty"
        eyebrow="Clients"
        headline="No clients seeded"
        body={<>The desk is wired but <code>pellier.customers</code> holds no client rows.</>}
      />
    )
  }
  return (
    <nav className="op-list" aria-label="Clients" data-testid="operator-book">
      <div className="op-list-head">
        <h2 className="op-h2">Clients</h2>
        <span className="op-list-count">
          {book.openRequests === 1 ? '1 open request' : `${book.openRequests} open requests`}
        </span>
      </div>
      <ul>
        {book.clients.map(client => (
          <ClientRow key={client.customerId} client={client} selected={client.customerId === customerId} />
        ))}
      </ul>
    </nav>
  )
}

/** The index page: the rail carries the list; the desk waits for a choice. */
const ClientBook: React.FC = () => (
  <OperatorState
    level={1}
    data-testid="operator-book-choose"
    eyebrow="Operator desk"
    headline="Choose a client"
    body="Open a record to read the ticket, the orders and the credits, then let the Investigator and the Planner propose the next step."
  />
)

export default ClientBook
