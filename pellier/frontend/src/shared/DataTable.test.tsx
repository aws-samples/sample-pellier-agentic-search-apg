/**
 * DataTable contract.
 *
 * The reason this primitive exists is that a column of durations could not be
 * compared by eye: numerics were left-aligned proportional text in three of
 * the four tables. Right alignment and tabular figures together are what make
 * digits line up by place value, so both are asserted, and asserted on the
 * numeric column only. Forcing every column to mono would be the opposite
 * mistake.
 *
 * The contract is split across two places on purpose, so the assertions are
 * too. Type (family, size, tabular figures) is inline on the element and is
 * asserted through the DOM. Padding, the row hairline and alignment are in
 * primitives.css, because the stacked layout below 560px has to override them
 * and an inline style beats a media query -- the first version kept them
 * inline and the narrow layout silently did nothing. Vitest runs with CSS
 * disabled, so those are asserted against the stylesheet source, the same way
 * governed_tokens_import.test.ts checks its import contract.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DataTable, type DataTableColumn } from './DataTable'

const PRIMITIVES_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), 'primitives.css'),
  'utf8',
)

interface Row {
  strategy: string
  recall: string
  path: string
}

const ROWS: Row[] = [
  { strategy: 'HNSW', recall: '0.98', path: '/observatory/search' },
  { strategy: 'IVFFlat', recall: '0.91', path: '/observatory/performance' },
]

const COLUMNS: DataTableColumn<Row>[] = [
  { key: 'strategy', header: 'Strategy', rowHeader: true, render: (r) => r.strategy },
  { key: 'recall', header: 'Recall', align: 'numeric', render: (r) => r.recall },
  { key: 'path', header: 'Reads from', align: 'code', render: (r) => r.path },
]

function renderTable(props: Partial<React.ComponentProps<typeof DataTable<Row>>> = {}) {
  return render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      rowKey={(row) => row.strategy}
      data-testid="table"
      {...props}
    />,
  )
}

describe('DataTable', () => {
  it('renders one header recipe: sans 12/600 in sentence case', () => {
    renderTable()
    const header = screen.getByRole('columnheader', { name: 'Recall' })
    expect(header).toHaveStyle({
      fontFamily: 'var(--obs-heading)',
      fontSize: '12px',
      fontWeight: '600',
    })
    expect(header.style.textTransform).toBe('')
  })

  it('sets numerics in mono with tabular figures', () => {
    renderTable()
    const cell = screen.getByRole('cell', { name: '0.98' })
    expect(cell).toHaveStyle({
      fontFamily: 'var(--obs-mono)',
      fontSize: '13px',
      fontVariantNumeric: 'tabular-nums',
    })
    expect(cell).toHaveAttribute('data-align', 'numeric')
  })

  it('right-aligns the numeric column and nothing else', () => {
    // Right alignment plus tabular figures is what makes digits line up by
    // place value; a path is not a magnitude, so it stays left.
    expect(PRIMITIVES_CSS).toMatch(
      /\.gov-data-table \[data-align='numeric'\]\s*\{\s*text-align:\s*right;/,
    )
    expect(PRIMITIVES_CSS).toMatch(
      /\[data-align='text'\],\s*\.gov-data-table \[data-align='code'\]\s*\{\s*text-align:\s*left;/,
    )
  })

  it('keeps prose columns in sans at 13px', () => {
    renderTable({
      columns: [
        { key: 'strategy', header: 'Strategy', render: (r: Row) => r.strategy },
      ],
    })
    const cell = screen.getByRole('cell', { name: 'HNSW' })
    expect(cell).toHaveStyle({
      fontFamily: 'var(--obs-sans)',
      fontSize: '13px',
    })
    expect(cell).toHaveAttribute('data-align', 'text')
  })

  it('sets identifiers in mono without tabular figures', () => {
    renderTable()
    const cell = screen.getByRole('cell', { name: '/observatory/search' })
    expect(cell).toHaveStyle({ fontFamily: 'var(--obs-mono)' })
    expect(cell).toHaveAttribute('data-align', 'code')
    expect(cell.getAttribute('style') ?? '').not.toMatch(/tabular-nums/)
  })

  it('names each row with a row header so a screen reader can place a cell', () => {
    renderTable()
    const rowHeader = screen.getByRole('rowheader', { name: 'HNSW' })
    expect(rowHeader).toHaveAttribute('scope', 'row')
  })

  it('separates rows with a hairline and no zebra fill', () => {
    expect(PRIMITIVES_CSS).toMatch(
      /border-top:\s*1px solid var\(--obs-rule-1\)/,
    )
    renderTable()
    const style =
      screen.getByRole('cell', { name: '0.98' }).getAttribute('style') ?? ''
    expect(style).not.toMatch(/background/)
  })

  it('keeps cell padding and the row rule where a media query can win', () => {
    // The whole point of the stacked layout is that it overrides these. An
    // inline padding or border-top would beat the media query and the narrow
    // layout would render as three rules per row.
    renderTable()
    const style =
      screen.getByRole('cell', { name: '0.98' }).getAttribute('style') ?? ''
    expect(style).not.toMatch(/padding/)
    expect(style).not.toMatch(/border-top/)
  })

  it('strips the header, padding and rules from a stacked row below 560px', () => {
    const stacked = PRIMITIVES_CSS.slice(
      PRIMITIVES_CSS.indexOf('@media (max-width: 560px)'),
    )
    expect(stacked).toMatch(/\[data-stacked='true'\] thead\s*\{\s*display:\s*none;/)
    expect(stacked).toMatch(/\[data-stacked='true'\] tr\s*\{\s*display:\s*grid;/)
    expect(stacked).toMatch(/padding:\s*0;/)
    expect(stacked).toMatch(/border-top:\s*0;/)
  })

  it('sticks the header at the offset it is given, and not otherwise', () => {
    const { unmount } = renderTable({ stickyHeaderTop: 64 })
    expect(screen.getByTestId('table')).toHaveAttribute(
      'data-sticky-header',
      'true',
    )
    expect(screen.getByRole('columnheader', { name: 'Recall' })).toHaveStyle({
      top: '64px',
    })
    unmount()

    renderTable()
    expect(screen.getByTestId('table')).not.toHaveAttribute('data-sticky-header')
  })

  it('opts into the stacked narrow layout by default and can opt out', () => {
    const { unmount } = renderTable()
    expect(screen.getByTestId('table')).toHaveAttribute('data-stacked', 'true')
    unmount()

    renderTable({ stackOnNarrow: false })
    expect(screen.getByTestId('table')).not.toHaveAttribute('data-stacked')
  })

  it('puts the table in its own horizontal scroll container', () => {
    // Wide evidence must scroll inside itself. A table that widens the page
    // makes every other panel scroll sideways with it.
    const { container } = renderTable()
    const scroller = container.querySelector('.gov-data-table-scroll')
    expect(scroller).not.toBeNull()
    expect(scroller?.querySelector('table')).toBe(screen.getByTestId('table'))
  })

  it('renders every row in source order, keyed by the caller', () => {
    renderTable()
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByRole('rowheader')).toHaveTextContent('HNSW')
    expect(within(rows[1]).getByRole('rowheader')).toHaveTextContent('IVFFlat')
  })

  it('renders an empty body without inventing a placeholder row', () => {
    // Naming an absence is EmptyState's job; a table that draws a fake row
    // would make an empty result look like a measured one.
    renderTable({ rows: [] })
    expect(screen.getAllByRole('row')).toHaveLength(1)
  })
})
