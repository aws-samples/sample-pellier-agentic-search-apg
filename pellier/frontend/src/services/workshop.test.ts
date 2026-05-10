/**
 * Tests for the Turn primitive ``eventsToTurn`` — pure grouping of
 * a single submit's event bundle into the categorized shape the
 * Atelier chat's AssistantTurn renderer consumes.
 */
import { describe, expect, it } from 'vitest'

import {
  eventsToTurn,
  type WorkshopPanelEvent,
  type WorkshopPlanEvent,
  type WorkshopResponseEvent,
  type WorkshopEvent,
} from './workshop'

function plan(overrides: Partial<WorkshopPlanEvent> = {}): WorkshopPlanEvent {
  return {
    type: 'plan',
    title: 'Decomposed into 5 steps',
    steps: ['parse', 'memory', 'search', 'filter', 'synthesize'],
    duration_ms: 45,
    ts_ms: 0,
    ...overrides,
  }
}

function panel(overrides: Partial<WorkshopPanelEvent> = {}): WorkshopPanelEvent {
  return {
    type: 'panel',
    agent: 'search',
    tag: 'TOOL · SEARCH',
    tag_class: 'cyan',
    title: 'Searched catalog',
    sql: 'SELECT * FROM products LIMIT 5',
    columns: ['name', 'score'],
    rows: [
      ['Linen Shirt', '0.88'],
      ['Camp Shirt', '0.81'],
    ],
    meta: '',
    duration_ms: 142,
    ts_ms: 100,
    ...overrides,
  }
}

function response(
  overrides: Partial<WorkshopResponseEvent> = {},
): WorkshopResponseEvent {
  return {
    type: 'response',
    text: 'Three pieces stand out, all under $150.',
    citations: [],
    confidence: null,
    ts_ms: 200,
    ...overrides,
  }
}

describe('eventsToTurn', () => {
  it('groups the user text + assistant text + panels', () => {
    const events: WorkshopEvent[] = [plan(), panel(), response()]
    const t = eventsToTurn('turn-1', 'find me linen shirts', events)
    expect(t.id).toBe('turn-1')
    expect(t.user_text).toBe('find me linen shirts')
    expect(t.assistant_text).toBe('Three pieces stand out, all under $150.')
    expect(t.plan).toBeDefined()
    expect(t.panels).toHaveLength(1)
    expect(t.panels[0].tag).toBe('TOOL · SEARCH')
  })

  it('handles empty events (turn in-flight, before response arrives)', () => {
    const t = eventsToTurn('turn-2', 'hi', [])
    expect(t.assistant_text).toBeNull()
    expect(t.plan).toBeUndefined()
    expect(t.panels).toEqual([])
    expect(t.confidence).toBeUndefined()
    expect(t.products).toBeUndefined()
  })

  it('lifts the MEMORY · CONFIDENCE panel into confidence, not panels', () => {
    const conf = panel({
      tag: 'MEMORY · CONFIDENCE',
      tag_class: 'green',
      columns: ['signal', 'contribution'],
      rows: [['result', '94 (clamped to [30, 98])']],
    })
    const t = eventsToTurn('turn-3', 'q', [plan(), panel(), conf, response()])
    expect(t.confidence?.tag).toBe('MEMORY · CONFIDENCE')
    expect(t.panels.every((p) => p.tag !== 'MEMORY · CONFIDENCE')).toBe(true)
  })

  it('lifts RECOMMENDATION panels into products and maps columns', () => {
    const rec = panel({
      tag: 'RECOMMENDATION · RANK',
      columns: ['name', 'price', 'attrs', 'product_id'],
      rows: [
        ['Italian Linen Camp Shirt', '$128', 'earl gray · relaxed', 'p-1'],
        ['Stonewashed Workshirt', '$142', 'camel · structured', 'p-2'],
      ],
    })
    const t = eventsToTurn('turn-4', 'q', [rec, response()])
    expect(t.products).toHaveLength(2)
    expect(t.products?.[0]).toEqual({
      product_id: 'p-1',
      name: 'Italian Linen Camp Shirt',
      price: '$128',
      attributes: 'earl gray · relaxed',
    })
    // The panel itself must NOT appear in the generic panels list.
    expect(t.panels.some((p) => p.tag === 'RECOMMENDATION · RANK')).toBe(false)
  })

  it('tolerates recommendation panels with unexpected column order', () => {
    const rec = panel({
      tag: 'RECOMMENDATION · RANK',
      columns: ['id', 'name'], // only two columns, no price/attrs
      rows: [['p-99', 'Linen Henley']],
    })
    const t = eventsToTurn('turn-5', 'q', [rec, response()])
    expect(t.products?.[0]).toEqual({
      product_id: 'p-99',
      name: 'Linen Henley',
      price: undefined,
      attributes: undefined,
    })
  })

  it('preserves response citations when present', () => {
    const resp = response({
      citations: [{ k: 'beans.b_colombia_huila', ref: 'trace 7' }],
    })
    const t = eventsToTurn('turn-6', 'q', [plan(), panel(), resp])
    expect(t.citations).toEqual([
      { k: 'beans.b_colombia_huila', ref: 'trace 7' },
    ])
  })

  it('returns panels in emission order', () => {
    const events: WorkshopEvent[] = [
      plan(),
      panel({ tag: 'TOOL · A', ts_ms: 50 }),
      panel({ tag: 'TOOL · B', ts_ms: 100 }),
      panel({ tag: 'TOOL · C', ts_ms: 150 }),
      response(),
    ]
    const t = eventsToTurn('turn-7', 'q', events)
    expect(t.panels.map((p) => p.tag)).toEqual([
      'TOOL · A',
      'TOOL · B',
      'TOOL · C',
    ])
  })
})
