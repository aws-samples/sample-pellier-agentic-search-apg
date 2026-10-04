/**
 * agentVocabulary — canonical names + one-line glossaries for every
 * agent concept that appears in BOTH Pellier and Observatory.
 *
 * One source of truth so a workshop participant crossing between the
 * shopper-facing storefront and the operator-facing observatory sees
 * the same chip with the same name in both places. When a name needs
 * to change, change it here and both surfaces update.
 *
 * Naming rule: snake_dot — `<noun>.<verb>` lowercase, dot-separated.
 * Examples: memory.recall, inventory.live, trend.signal. Stays
 * consistent with the Observatory's existing tool-registry vocabulary
 * (`product_search`, `discover_tools`, `aurora_*`) while keeping the
 * Pellier-facing names compact enough to fit inline on a product
 * card.
 */

export type AgentToolName =
  | 'memory.recall'
  | 'memory.seed'
  | 'memory.write'
  | 'inventory.live'
  | 'inventory.watch'
  | 'inventory.search'
  | 'trend.signal'
  | 'pairing.score'
  | 'palette.match'
  | 'memory.holds'
  | 'experience.return'
  | 'weather.lookup'
  | 'tag.match'
  | 'store.pick'
  | 'tool.transparency'

interface AgentToolEntry {
  /** Canonical machine-readable name. */
  name: AgentToolName
  /** Human-readable label for tooltips and Observatory deep links. */
  label: string
  /** One-line glossary, attendee-friendly. */
  description: string
}

export const AGENT_VOCABULARY: Record<AgentToolName, AgentToolEntry> = {
  'memory.recall': {
    name: 'memory.recall',
    label: 'Saved taste',
    description:
      'A preference or saved piece from an earlier visit shaped this recommendation.',
  },
  'memory.seed': {
    name: 'memory.seed',
    label: 'Learns as you shop',
    description:
      'A first visit starts with broad signals and becomes more personal as you save and ask.',
  },
  'memory.write': {
    name: 'memory.write',
    label: 'Taste saved',
    description:
      'A new size, saved item, or taste signal is kept for the next visit.',
  },
  'inventory.live': {
    name: 'inventory.live',
    label: 'In stock',
    description: 'The recommendation is grounded in what is available right now.',
  },
  'inventory.watch': {
    name: 'inventory.watch',
    label: 'Restock watch',
    description: 'A piece you may care about has returned or changed availability.',
  },
  'inventory.search': {
    name: 'inventory.search',
    label: 'Catalog match',
    description: 'The catalog was matched to the words and intent in your request.',
  },
  'trend.signal': {
    name: 'trend.signal',
    label: 'Trending',
    description: 'This piece is moving quickly across the storefront right now.',
  },
  'pairing.score': {
    name: 'pairing.score',
    label: 'Pairs well',
    description: 'Palette, weight, occasion, and saved taste suggest these pieces work together.',
  },
  'palette.match': {
    name: 'palette.match',
    label: 'Palette match',
    description: 'The color and tone fit the palette already present in the edit.',
  },
  'memory.holds': {
    name: 'memory.holds',
    label: 'Bag hold',
    description: 'A piece from an earlier visit is still being held in your bag.',
  },
  'experience.return': {
    name: 'experience.return',
    label: 'Return update',
    description: 'A return, refund, or post-purchase request influenced this visit.',
  },
  'weather.lookup': {
    name: 'weather.lookup',
    label: 'Weather-aware',
    description: 'A live weather call to ground a recommendation in the conditions you’re shopping for.',
  },
  'tag.match': {
    name: 'tag.match',
    label: 'Category match',
    description: 'A direct match against the product taxonomy (linen, travel, ceramic, etc).',
  },
  'store.pick': {
    name: 'store.pick',
    label: "Editor's pick",
    description: 'An editorial pick the store is reaching for this week.',
  },
  'tool.transparency': {
    name: 'tool.transparency',
    label: 'Why it fits',
    description: 'Pellier names the signal behind each recommendation.',
  },
}

/** Skills router — loaded skill chips in Pellier chat attribution. */
const SKILL_VOCABULARY: Record<string, AgentToolEntry> = {
  'skill.packing-list': {
    name: 'skill.packing-list' as AgentToolName,
    label: 'The Packing List',
    description: 'Travel and capsule packing recommendations.',
  },
  'skill.gift-table': {
    name: 'skill.gift-table' as AgentToolName,
    label: 'The Gift Table',
    description: 'Curated gift-ready pieces for thoughtful giving.',
  },
  'skill.makers-shelf': {
    name: 'skill.makers-shelf' as AgentToolName,
    label: "The Maker's Shelf",
    description: 'Hand-thrown ceramics and slow-living home pieces.',
  },
  'skill.care-card': {
    name: 'skill.care-card' as AgentToolName,
    label: 'The Care Card',
    description: 'Care, return, and post-purchase handling guidance.',
  },
  'skill.proof-counter': {
    name: 'skill.proof-counter' as AgentToolName,
    label: 'The Proof Counter',
    description: 'Grounded proof, memory, and audit-receipt guidance.',
  },
}

/**
 * Look up a vocabulary entry, defaulting to a synthetic entry when an
 * unknown trace string flows through. Keeps consumers safe when the
 * upstream rolls out a new tool name before this module is updated.
 *
 * Trace strings often carry a trailing score/value suffix (e.g.
 * "palette.match · 0.92", "inventory.live · 2 left"). The lookup
 * peels the suffix before matching so the canonical entry still
 * resolves. The full suffixed string is preserved in `name` so
 * callers can render it verbatim.
 */
export function lookupVocab(name: string): AgentToolEntry {
  const canonical = name.split(' · ')[0]
  const known =
    (AGENT_VOCABULARY as Record<string, AgentToolEntry | undefined>)[canonical] ??
    SKILL_VOCABULARY[canonical]
  if (known) {
    // Preserve the caller's full label (including suffix) in `name`
    // but use the canonical entry for the description.
    return { ...known, name: name as AgentToolName }
  }
  const fallbackLabel = canonical
    .replace(/^tool\./, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
  return {
    name: name as AgentToolName,
    label: fallbackLabel,
    description: 'A catalog or service check used to prepare this recommendation.',
  }
}
