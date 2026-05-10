/**
 * StateManagementArchPage — Atelier · Architecture · State Management
 * (Template D · Schema)
 *
 * Matches docs/atelier-state-management-architecture.html:
 *   - Title / subtitle / meta strip
 *   - Schema canvas: four table cards (products, customers, orders,
 *     session_state) with column rows. Touched tables get burgundy
 *     1px ring + soft shadow; touched columns get soft burgundy tint
 *   - Three-rules grid: reads through tools / writes gated / session
 *     as bridge
 *   - Live strip: rows of READ/WRITE op + table + truncated SQL + ms
 *
 * Data sources:
 *   - Schema: hardcoded (this is the teaching surface — the schema
 *     shape rarely changes and the page reads better when the shape
 *     is editorial rather than generated)
 *   - Live queries: localStorage "pellier-last-db-queries" written by
 *     useAgentChat on each ``db_queries`` SSE event. Falls back to a
 *     short stub list + demo-data caption until the backend ships the
 *     event.
 */
import { useMemo } from 'react'
import {
  DetailPageShell,
  SectionFrame,
  LiveStrip,
  MonoBlock,
} from '../atelier'
import { useDbQueries, type DbQuery } from './shared-catalog'
import '../../styles/atelier-arch.css'

interface TableColumn {
  name: string
  type: string
  flag?: 'PK' | 'FK' | 'IDX' | 'UNIQ' | 'IVF'
}

interface SchemaTable {
  name: string
  columns: TableColumn[]
  rowCount: string
  indexCount: number
  note: { label: string; body: React.ReactNode }
}

const SCHEMA: SchemaTable[] = [
  {
    name: 'products',
    columns: [
      { name: 'product_id', type: 'uuid', flag: 'PK' },
      { name: 'name', type: 'text', flag: 'IDX' },
      { name: 'brand', type: 'text' },
      { name: 'description', type: 'text' },
      { name: 'embedding', type: 'vector(1024)', flag: 'IVF' },
      { name: 'price_cents', type: 'int' },
      { name: 'category', type: 'enum', flag: 'IDX' },
      { name: 'created_at', type: 'timestamp' },
    ],
    rowCount: '444',
    indexCount: 3,
    note: {
      label: 'Source of truth',
      body: (
        <>
          The catalog. <em>semantic_search</em> reads via the <em>embedding</em> column.
        </>
      ),
    },
  },
  {
    name: 'customers',
    columns: [
      { name: 'customer_id', type: 'uuid', flag: 'PK' },
      { name: 'email', type: 'text', flag: 'UNIQ' },
      { name: 'display_name', type: 'text' },
      { name: 'tier', type: 'enum' },
      { name: 'created_at', type: 'timestamp' },
    ],
    rowCount: '12,840',
    indexCount: 2,
    note: {
      label: 'Identity anchor',
      body: (
        <>
          Foreign-key target for orders and session_state. Never written by the agent.
        </>
      ),
    },
  },
  {
    name: 'orders',
    columns: [
      { name: 'order_id', type: 'uuid', flag: 'PK' },
      { name: 'customer_id', type: 'uuid', flag: 'FK' },
      { name: 'items', type: 'jsonb' },
      { name: 'total_cents', type: 'int' },
      { name: 'status', type: 'enum', flag: 'IDX' },
      { name: 'created_at', type: 'timestamp', flag: 'IDX' },
    ],
    rowCount: '38,902',
    indexCount: 3,
    note: {
      label: 'Domain truth',
      body: (
        <>
          The agent reads order history via <em>get_order_history</em>. Writes
          are gated behind <em>support agent + user confirmation</em>.
        </>
      ),
    },
  },
  {
    name: 'session_state',
    columns: [
      { name: 'session_id', type: 'uuid', flag: 'PK' },
      { name: 'customer_id', type: 'uuid', flag: 'FK' },
      { name: 'cart', type: 'jsonb' },
      { name: 'last_active', type: 'timestamp', flag: 'IDX' },
      { name: 'turn_count', type: 'int' },
    ],
    rowCount: '~live',
    indexCount: 1,
    note: {
      label: 'Bridge',
      body: (
        <>
          The seam between the agent's runtime and durable Postgres.{' '}
          <em>cart</em> and <em>turn_count</em> updated at end of each turn.
        </>
      ),
    },
  },
]

// Stub fallback used until the backend ships the db_queries event.
const STUB_QUERIES: DbQuery[] = [
  {
    op: 'READ',
    table: 'products',
    sql: 'SELECT id, name, price FROM products ORDER BY embedding <=> $1 LIMIT 12',
    duration_ms: 274,
    timestamp: 0,
  },
  {
    op: 'READ',
    table: 'products',
    sql: 'SELECT stock FROM products WHERE id IN ($1, $2, $3)',
    duration_ms: 38,
    timestamp: 0,
  },
  {
    op: 'READ',
    table: 'orders',
    sql: 'SELECT items, total_cents FROM orders WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 5',
    duration_ms: 22,
    timestamp: 0,
  },
  {
    op: 'WRITE',
    table: 'session_state',
    sql: 'UPDATE session_state SET turn_count = $1, last_active = NOW() WHERE session_id = $2',
    duration_ms: 8,
    timestamp: 0,
  },
]

export default function StateManagementArchPage() {
  const live = useDbQueries()
  const queries = live.length > 0 ? live : STUB_QUERIES
  const isStub = live.length === 0

  // Derive which tables were touched this turn from the queries.
  const touchedTables = useMemo(
    () => new Set(queries.map((q) => q.table)),
    [queries],
  )
  const readCount = queries.filter((q) => q.op === 'READ').length
  const writeCount = queries.filter((q) => q.op === 'WRITE').length
  const touchedCount = touchedTables.size

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'State Management']}
      title={
        <>
          State, <em>where it lives.</em>
        </>
      }
      subtitle="The boutique runs on Postgres. Orders, customers, products, sessions — domain truth lives in named tables with foreign keys. The agent reads through tools, never directly. The schema is the contract."
      meta={[
        { label: 'Tables', value: '8 total' },
        { label: 'Touched', value: `${touchedCount} this turn` },
        { label: 'Reads', value: readCount },
        { label: 'Writes', value: writeCount },
      ]}
    >
      {/* ---- Schema canvas ---- */}
      <SectionFrame
        eyebrow="The schema"
        title={
          <>
            Four tables, <em>three touched.</em>
          </>
        }
        description="A trimmed view of the boutique's relational surface. The four tables below cover every read and write the agent does this turn — products, customers, orders, and the session-state table that ties the agent's runtime to durable storage."
      >
        <div className="sm-canvas">
          <div className="sm-canvas-head">
            <span className="sm-canvas-label">Schema · public · trimmed</span>
            <span className="sm-canvas-meta">
              <span className="arch-num">{touchedCount}</span> tables touched ·{' '}
              <span className="arch-num">{readCount}</span> reads ·{' '}
              <span className="arch-num">{writeCount}</span> writes
            </span>
          </div>
          <div className="sm-grid">
            {SCHEMA.map((table) => (
              <SchemaTableCard
                key={table.name}
                table={table}
                touched={touchedTables.has(table.name)}
              />
            ))}
          </div>
        </div>
      </SectionFrame>

      {/* ---- Three rules ---- */}
      <SectionFrame
        eyebrow="Three rules"
        title={
          <>
            How the agent talks <em>to the schema.</em>
          </>
        }
      >
        <div className="sm-rel-grid">
          <div className="sm-rel-cell">
            <div className="sm-rel-key">READS</div>
            <div className="sm-rel-name">
              Through tools, <em>never direct.</em>
            </div>
            <p className="sm-rel-text">
              The agent never writes raw SQL. Every read goes through a typed
              tool — <em>find_pieces</em>, <em>get_order_history</em>. The
              tool owns the query; the agent owns the question.
            </p>
            <MonoBlock>
              <MonoBlock.Comment># tool layer holds the SQL</MonoBlock.Comment>
              <br />
              <MonoBlock.Key>def</MonoBlock.Key> find_pieces(q: str):
              <br />
              &nbsp;&nbsp;<MonoBlock.Key>return</MonoBlock.Key> db.fetch(
              <br />
              &nbsp;&nbsp;&nbsp;&nbsp;
              <MonoBlock.Str>"SELECT … FROM products …"</MonoBlock.Str>
              <br />
              &nbsp;&nbsp;)
            </MonoBlock>
          </div>
          <div className="sm-rel-cell">
            <div className="sm-rel-key">WRITES</div>
            <div className="sm-rel-name">
              Gated, <em>and confirmed.</em>
            </div>
            <p className="sm-rel-text">
              Domain writes (orders, returns, restocks) require explicit user
              confirmation in the chat. The agent <em>proposes</em>, the
              customer <em>confirms</em>, the tool <em>commits</em>. Session
              writes are ambient and idempotent.
            </p>
            <MonoBlock>
              <MonoBlock.Key>if</MonoBlock.Key> user_confirmed:
              <br />
              &nbsp;&nbsp;db.execute(
              <br />
              &nbsp;&nbsp;&nbsp;&nbsp;
              <MonoBlock.Str>"INSERT INTO orders …"</MonoBlock.Str>
              <br />
              &nbsp;&nbsp;)
            </MonoBlock>
          </div>
          <div className="sm-rel-cell">
            <div className="sm-rel-key">SESSION</div>
            <div className="sm-rel-name">
              The bridge, <em>kept thin.</em>
            </div>
            <p className="sm-rel-text">
              The session table is what makes the agent's runtime durable.
              Cart contents, turn count, last-active stamp. Written end-of-turn,
              read at boot — small, hot, indexed.
            </p>
            <MonoBlock>
              session.upsert(
              <br />
              &nbsp;&nbsp;cart=cart,
              <br />
              &nbsp;&nbsp;turn_count=n,
              <br />)
            </MonoBlock>
          </div>
        </div>
      </SectionFrame>

      {/* ---- Live strip ---- */}
      <LiveStrip
        title={
          <>
            Queries, <em>row by row.</em>
          </>
        }
        meta={`${readCount} reads · ${writeCount} write${writeCount === 1 ? '' : 's'} · pool 4/16`}
        stubCaption={
          isStub
            ? '// demo data — db_queries SSE event not yet emitted by the backend'
            : undefined
        }
      >
        {queries.length === 0 ? (
          <div className="arch-empty">
            No queries yet. Send a query in the chat on the left — each
            read and write will appear here.
          </div>
        ) : (
          <div className="sm-live-table">
            <div className="sm-live-row sm-live-row-head">
              <span>Op</span>
              <span>Table</span>
              <span>Query</span>
              <span style={{ textAlign: 'right' }}>Elapsed</span>
            </div>
            {queries.slice(-10).reverse().map((q, i) => (
              <div
                className="sm-live-row"
                key={`${q.timestamp}-${q.sql.slice(0, 24)}-${i}`}
              >
                <span className={`sm-op sm-op-${q.op.toLowerCase()}`}>
                  {q.op}
                </span>
                <span className="sm-live-table-name">{q.table}</span>
                <span className="sm-live-query">{colorizeSql(q.sql)}</span>
                <span className="sm-live-ms">{q.duration_ms}ms</span>
              </div>
            ))}
          </div>
        )}
      </LiveStrip>
    </DetailPageShell>
  )
}

/* ---- Schema table card ---- */

function SchemaTableCard({
  table,
  touched,
}: {
  table: SchemaTable
  touched: boolean
}) {
  return (
    <article className={`sm-tbl ${touched ? 'sm-tbl-touched' : ''}`}>
      <div className="sm-tbl-head">
        <div className="sm-tbl-name">
          <em>{table.name}</em>
        </div>
        <span className="sm-tbl-tag">
          {touched ? 'touched · this turn' : 'cold · this turn'}
        </span>
      </div>
      {table.columns.map((col) => (
        <div
          key={col.name}
          className={`sm-tbl-row ${col.flag === 'PK' ? 'sm-tbl-row-pk' : ''} ${col.flag === 'FK' ? 'sm-tbl-row-fk' : ''}`}
        >
          <span className="sm-tbl-col">{col.name}</span>
          <span className="sm-tbl-type">{col.type}</span>
          {col.flag && (
            <span
              className={`sm-tbl-flag ${col.flag === 'IDX' || col.flag === 'IVF' ? 'sm-tbl-flag-idx' : ''} ${col.flag === 'UNIQ' ? 'sm-tbl-flag-uniq' : ''}`}
            >
              {col.flag}
            </span>
          )}
        </div>
      ))}
      <div className="sm-tbl-foot">
        <span>
          <span className="arch-num">{table.rowCount}</span> rows
        </span>
        <span>
          <span className="arch-num">{table.indexCount}</span> index
          {table.indexCount === 1 ? '' : 'es'}
        </span>
      </div>
      <div className="sm-tbl-note">
        <span className="sm-tbl-note-label">{table.note.label}</span>{' '}
        {table.note.body}
      </div>
    </article>
  )
}

/* ---- Minimal SQL colorizer — highlights keywords in burgundy ---- */

const SQL_KEYWORDS = new Set([
  'SELECT',
  'FROM',
  'WHERE',
  'ORDER',
  'BY',
  'LIMIT',
  'IN',
  'INSERT',
  'INTO',
  'UPDATE',
  'SET',
  'DELETE',
  'JOIN',
  'ON',
  'LEFT',
  'RIGHT',
  'INNER',
  'OUTER',
  'AND',
  'OR',
  'NOT',
  'DESC',
  'ASC',
  'NOW',
  'VALUES',
  'RETURNING',
])

function colorizeSql(sql: string): React.ReactNode {
  const tokens = sql.split(/(\s+|,|\(|\))/g)
  return (
    <>
      {tokens.map((token, i) => {
        if (SQL_KEYWORDS.has(token.toUpperCase())) {
          return (
            <span className="sm-sql-keyword" key={i}>
              {token}
            </span>
          )
        }
        return <span key={i}>{token}</span>
      })}
    </>
  )
}
