/**
 * Telemetry trace helpers — resolve product picks to timeline panel indices.
 */
import type { ChatTurn, ProductCard, SessionDetail } from '../../types';
import type { TelemetryPanel } from '../../types';

/** Parse fixture trace refs (`panel-3`, `#telemetry-3`, `trace 3`) to panel index. */
export function parseTelemetryPanelIndex(ref: string | undefined | null): number | null {
  if (!ref) return null;
  const trimmed = ref.trim();
  const telemetryHash = trimmed.match(/^#?telemetry-(\d+)$/i);
  if (telemetryHash) return parseInt(telemetryHash[1], 10);
  const panelTag = trimmed.match(/^panel-(\d+)$/i);
  if (panelTag) return parseInt(panelTag[1], 10);
  const traceNum = trimmed.match(/^trace\s*(\d+)$/i);
  if (traceNum) return parseInt(traceNum[1], 10);
  if (/^\d+$/.test(trimmed)) return parseInt(trimmed, 10);
  return null;
}

/** Hero pick: last product from the first assistant recommendation turn. */
export function getTopPickProduct(session: SessionDetail): ProductCard | null {
  const firstRec = session.chat.find(
    (t) => t.role === 'assistant' && t.products && t.products.length > 0,
  );
  if (firstRec?.products?.length) {
    return firstRec.products[firstRec.products.length - 1];
  }
  if (session.brief?.products?.length) {
    return session.brief.products[session.brief.products.length - 1];
  }
  return null;
}

export function findRecommendationTurn(
  session: SessionDetail,
  product: ProductCard,
): ChatTurn | undefined {
  return session.chat.find(
    (t) =>
      t.role === 'assistant' &&
      t.products?.some((p) => p.name === product.name),
  );
}

/** Panel where ranking / retrieval decided the pick (rerank → vector → SQL). */
export function findPrimaryPickPanelIndex(panels: TelemetryPanel[]): number {
  const predicates = [
    (p: TelemetryPanel) => /rerank/i.test(p.title),
    (p: TelemetryPanel) => /rrf/i.test(p.title),
    (p: TelemetryPanel) => /semantic|vector|bm25|hybrid/i.test(p.title),
    (p: TelemetryPanel) => Boolean(p.sql),
    (p: TelemetryPanel) => /composition|compose|editorial/i.test(p.title),
  ];
  for (const pred of predicates) {
    const hit = panels.find(pred);
    if (hit) return hit.index;
  }
  return panels[0]?.index ?? 1;
}

export function resolveTracePanelIndex(
  product: ProductCard | null,
  panels: TelemetryPanel[],
): number {
  if (product?.traceRef) {
    const parsed = parseTelemetryPanelIndex(product.traceRef);
    if (parsed != null && panels.some((p) => p.index === parsed)) {
      return parsed;
    }
  }
  return findPrimaryPickPanelIndex(panels);
}

export function buildWhyThisPickReasons(
  session: SessionDetail,
  product: ProductCard,
  panels: TelemetryPanel[],
): string[] {
  const turn = findRecommendationTurn(session, product);
  if (turn?.confidence?.reasoning) {
    return [turn.confidence.reasoning];
  }

  const retrieval = panels.filter((p) =>
    /rerank|rrf|vector|bm25|semantic|hybrid|similarity|cosine/i.test(
      `${p.title} ${p.description}`,
    ),
  );
  if (retrieval.length > 0) {
    return retrieval.slice(0, 4).map((p) => `${p.title}: ${p.description}`);
  }

  return [
    `Matched session intent for “${product.name}”`,
    'Ranked against in-stock catalog candidates',
    'Composed into the assistant reply for this turn',
  ];
}

export function estimateTokenCount(panels: TelemetryPanel[]): number {
  const totalMs = panels.reduce((sum, p) => sum + p.durationMs, 0);
  return Math.round(totalMs * 2.8);
}

export function blurbForProduct(turn: ChatTurn | undefined, product: ProductCard): string {
  if (!turn) {
    return `${product.name} from ${product.brand}.`;
  }
  const sentences = turn.content.split(/(?<=[.!?])\s+/);
  const hit = sentences.find((s) => s.includes(product.name));
  return hit ?? turn.content;
}
