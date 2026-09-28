/**
 * DataTable — one register for every table on the technical surfaces.
 *
 * Three header recipes were live at once: sans 11/500 in Performance, mono
 * 11/500 in the reference index, sans 11/600 on the desk. Body text ran 13px
 * to 14px, numerics were sometimes mono and sometimes not, and nothing was
 * right-aligned or tabular, so a column of durations could not be compared by
 * eye, which is the only reason to put durations in a column.
 *
 * The register:
 *
 *   header    Instrument Sans, 12px, 600, sentence case. A column head is a
 *             label, set in the same register as SectionEyebrow at table size.
 *   text      Instrument Sans, 13px.
 *   numeric   JetBrains Mono, 13px, right-aligned, tabular figures. Right
 *             alignment plus tabular figures is what makes digits line up by
 *             place value; either one alone does not.
 *   code      JetBrains Mono, 13px, left. Identifiers and paths read
 *             left-to-right and are not compared by magnitude.
 *   rows      A hairline between rows, no zebra fill. Zebra striping is a
 *             workaround for rows that are too tall to track.
 *
 * `stickyHeaderTop` is an offset in px because the surfaces have different
 * fixed headers to clear.
 *
 * Below 560px the table stops being a table (see primitives.css): the header
 * is removed and each row becomes a stacked block. That is the layout the
 * reference-view index already shipped; it lives here now so every table
 * inherits it instead of the one that happened to be written first.
 */
import type React from 'react'

import './primitives.css'

export type DataTableAlign = 'text' | 'numeric' | 'code'

export interface DataTableColumn<Row> {
  /** Stable identity for the column. Not rendered. */
  key: string
  header: React.ReactNode
  /** Defaults to `text`. */
  align?: DataTableAlign
  /**
   * Render this cell as the row's `<th scope="row">`. At most one column
   * should set it: it names the row for a screen reader.
   */
  rowHeader?: boolean
  /** Column width hint, applied to the header cell. */
  width?: string
  render: (row: Row, rowIndex: number) => React.ReactNode
}

export interface DataTableProps<Row> {
  columns: ReadonlyArray<DataTableColumn<Row>>
  rows: ReadonlyArray<Row>
  rowKey: (row: Row, rowIndex: number) => string
  /** Accessible name for the table. Not rendered as text. */
  ariaLabel?: string
  /** Sticky header offset in px. Omit for a header that scrolls away. */
  stickyHeaderTop?: number
  /** Stack rows below 560px. Default true; turn it off for a two-column table
   *  that is already narrow enough to read. */
  stackOnNarrow?: boolean
  className?: string
  'data-testid'?: string
}

/* Type only. Padding, the row hairline and alignment live in primitives.css,
   because the stacked layout below 560px has to override them and an inline
   style beats a media query. */
const ALIGN_STYLE: Record<DataTableAlign, React.CSSProperties> = {
  text: {
    fontFamily: 'var(--obs-sans)',
    fontSize: '13px',
  },
  numeric: {
    fontFamily: 'var(--obs-mono)',
    fontSize: '13px',
    fontVariantNumeric: 'tabular-nums',
  },
  code: {
    fontFamily: 'var(--obs-mono)',
    fontSize: '13px',
  },
}

const HEADER_STYLE: React.CSSProperties = {
  fontFamily: 'var(--obs-heading)',
  fontSize: '12px',
  fontWeight: 600,
  color: 'var(--obs-ink-4)',
  whiteSpace: 'nowrap',
}

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  ariaLabel,
  stickyHeaderTop,
  stackOnNarrow = true,
  className,
  'data-testid': testId,
}: DataTableProps<Row>) {
  const sticky = typeof stickyHeaderTop === 'number'

  return (
    <div className="gov-data-table-scroll">
      <table
        className={`gov-data-table${className ? ` ${className}` : ''}`}
        aria-label={ariaLabel}
        data-testid={testId}
        data-stacked={stackOnNarrow ? 'true' : undefined}
        data-sticky-header={sticky ? 'true' : undefined}
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          borderSpacing: 0,
          fontFamily: 'var(--obs-sans)',
          fontSize: '13px',
          lineHeight: 1.45,
          color: 'var(--obs-ink-2)',
        }}
      >
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                data-align={column.align ?? 'text'}
                style={{
                  ...HEADER_STYLE,
                  top: sticky ? `${stickyHeaderTop}px` : undefined,
                  width: column.width,
                }}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowKey(row, rowIndex)}>
              {columns.map((column) => {
                const align = column.align ?? 'text'
                const style = ALIGN_STYLE[align]
                return column.rowHeader ? (
                  <th key={column.key} scope="row" data-align={align} style={style}>
                    {column.render(row, rowIndex)}
                  </th>
                ) : (
                  <td key={column.key} data-align={align} style={style}>
                    {column.render(row, rowIndex)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default DataTable
