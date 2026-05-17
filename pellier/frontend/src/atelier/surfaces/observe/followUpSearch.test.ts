import { describe, expect, it } from 'vitest';
import marcoSession from '../../fixtures/session-marco-opening-demo.json';
import annaSession from '../../fixtures/session-anna-housewarming.json';
import theoSession from '../../fixtures/session-theo-pour-over.json';
import type { SessionDetail } from '../../types';
import {
  buildFollowUpSql,
  followUpHintsForSession,
  parseFollowUpConstraints,
  selectFollowUpProducts,
} from './ChatTab';

const noisyProducts = [
  {
    id: 1001,
    brand: 'Hadley',
    name: 'Hadley Linen Shirt',
    price: 248,
    imageUrl: '/x.png',
    category: 'Apparel',
  },
  {
    id: 1002,
    brand: 'Pellier Editions',
    name: 'Alba Linen Lounge Set',
    price: 298,
    imageUrl: '/x.png',
    category: 'Apparel',
  },
  {
    id: 1003,
    brand: 'Pellier Home',
    name: 'Raw Linen Throw',
    price: 195,
    imageUrl: '/x.png',
    category: 'Home Decor',
  },
  {
    id: 1004,
    brand: 'Pellier Home',
    name: 'Monogrammed Linen Napkins',
    price: 72,
    imageUrl: '/x.png',
    category: 'Home Decor',
  },
  {
    id: 1005,
    brand: 'Pellier Editions',
    name: 'Cotton-Linen Crew Tee',
    price: 68,
    imageUrl: '/x.png',
    category: 'Apparel',
  },
];

describe('Atelier follow-up search planner', () => {
  it('limits "Three linen pieces under $150" to three in-budget linen results', () => {
    const constraints = parseFollowUpConstraints(
      'Three linen pieces under $150',
      marcoSession as SessionDetail,
    );
    const products = selectFollowUpProducts(noisyProducts, constraints);

    expect(products).toHaveLength(3);
    expect(products.every((product) => product.price < 150)).toBe(true);
    expect(products.every((product) => `${product.name} ${product.category ?? ''} ${(product.tags ?? []).join(' ')}`.toLowerCase().includes('linen'))).toBe(true);

    const sql = buildFollowUpSql('Three linen pieces under $150', constraints);
    expect(sql).toContain('price < 150');
    expect(sql).toContain("ILIKE '%linen%'");
    expect(sql).toContain('LIMIT 3');
  });

  it('treats Brooklyn stock and fastest shipping pills as inventory-filtered searches', () => {
    for (const query of [
      'What is in stock at Brooklyn right now?',
      'What ships fastest from Brooklyn?',
    ]) {
      const constraints = parseFollowUpConstraints(query, marcoSession as SessionDetail);
      const sql = buildFollowUpSql(query, constraints);

      expect(constraints.brooklynInventory).toBe(true);
      expect(constraints.requiredTerms).toContain('linen');
      expect(sql).toContain('warehouse_inventory');
      expect(sql).toContain("w.id = 'BK-01'");
      expect(sql).toContain('wi.quantity > 0');
    }
  });

  it('applies price ceilings for one-more and gift-home pills', () => {
    const oneMore = parseFollowUpConstraints(
      'One more option under $100',
      marcoSession as SessionDetail,
    );
    expect(oneMore.limit).toBe(1);
    expect(oneMore.maxPrice).toBe(100);

    const giftHome = parseFollowUpConstraints(
      'Gift-ready home accents under $80',
      annaSession as SessionDetail,
    );
    const products = selectFollowUpProducts([], giftHome);

    expect(giftHome.maxPrice).toBe(80);
    expect(giftHome.requiredTerms).toContain('home');
    expect(products.length).toBeGreaterThan(0);
    expect(products.every((product) => product.price < 80)).toBe(true);
    expect(products.every((product) => `${product.name} ${product.category ?? ''} ${(product.tags ?? []).join(' ')}`.toLowerCase().includes('home'))).toBe(true);
  });

  it('handles cheapest, substitute, and ceramic follow-up pills', () => {
    const cheapest = parseFollowUpConstraints(
      'Cheapest piece that goes with the overshirt',
      marcoSession as SessionDetail,
    );
    const cheapestProducts = selectFollowUpProducts(noisyProducts, cheapest);
    expect(cheapest.limit).toBe(1);
    expect(cheapestProducts).toHaveLength(1);

    const substitute = parseFollowUpConstraints(
      'Close substitute if my size is gone',
      marcoSession as SessionDetail,
    );
    expect(substitute.requiredTerms).toContain('linen');

    const ceramic = parseFollowUpConstraints(
      'Ceramic tabletop in warm neutrals',
      theoSession as SessionDetail,
    );
    const ceramicProducts = selectFollowUpProducts([], ceramic);
    expect(ceramic.requiredTerms).toContain('ceramic');
    expect(ceramicProducts.length).toBeGreaterThan(0);
    expect(ceramicProducts.every((product) => `${product.name} ${product.category ?? ''} ${(product.tags ?? []).join(' ')}`.toLowerCase().includes('ceramic'))).toBe(true);
  });

  it('validates every generated Anna follow-up pill', () => {
    const session = annaSession as SessionDetail;
    const pills = followUpHintsForSession(session);

    expect(pills).toEqual([
      'Gift-ready home accents under $80',
      'What ships fastest from Brooklyn?',
      'One more option under $100',
      'Close substitute if my size is gone',
    ]);

    for (const pill of pills) {
      const constraints = parseFollowUpConstraints(pill, session);
      const products = selectFollowUpProducts([], constraints);
      const sql = buildFollowUpSql(pill, constraints);

      expect(products.length).toBeGreaterThan(0);
      expect(products.length).toBeLessThanOrEqual(constraints.limit);

      if (pill.includes('under $80')) {
        expect(constraints.maxPrice).toBe(80);
        expect(constraints.requiredTerms).toContain('home');
        expect(products.every((product) => product.price < 80)).toBe(true);
      }

      if (pill.includes('under $100')) {
        expect(constraints.maxPrice).toBe(100);
        expect(products).toHaveLength(1);
        expect(products[0].price).toBeLessThan(100);
      }

      if (pill.includes('Brooklyn')) {
        expect(constraints.brooklynInventory).toBe(true);
        expect(constraints.requiredTerms).toContain('gift');
        expect(sql).toContain('warehouse_inventory');
        expect(sql).toContain("w.id = 'BK-01'");
      }

      if (pill.includes('substitute')) {
        expect(constraints.requiredTerms).toContain('gift');
      }
    }
  });

  it('validates every generated Theo follow-up pill', () => {
    const session = theoSession as SessionDetail;
    const pills = followUpHintsForSession(session);

    expect(pills).toEqual([
      'Ceramic tabletop in warm neutrals',
      'What ships fastest from Brooklyn?',
      'One more option under $100',
      'Close substitute if my size is gone',
    ]);

    for (const pill of pills) {
      const constraints = parseFollowUpConstraints(pill, session);
      const products = selectFollowUpProducts([], constraints);
      const sql = buildFollowUpSql(pill, constraints);

      expect(products.length).toBeGreaterThan(0);
      expect(products.length).toBeLessThanOrEqual(constraints.limit);

      if (pill.includes('Ceramic')) {
        expect(constraints.requiredTerms).toContain('ceramic');
        expect(products.every((product) => `${product.name} ${product.category ?? ''} ${(product.tags ?? []).join(' ')}`.toLowerCase().includes('ceramic'))).toBe(true);
      }

      if (pill.includes('under $100')) {
        expect(constraints.maxPrice).toBe(100);
        expect(products).toHaveLength(1);
        expect(products[0].price).toBeLessThan(100);
      }

      if (pill.includes('Brooklyn')) {
        expect(constraints.brooklynInventory).toBe(true);
        expect(constraints.requiredTerms).toContain('home');
        expect(sql).toContain('warehouse_inventory');
        expect(sql).toContain("w.id = 'BK-01'");
      }

      if (pill.includes('substitute')) {
        expect(constraints.requiredTerms).toContain('home');
      }
    }
  });
});
