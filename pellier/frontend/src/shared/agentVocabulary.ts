/**
 * agentVocabulary — canonical names + one-line glossaries for every
 * agent concept that appears on BOTH the Boutique and the Atelier.
 *
 * One source of truth so a re:Invent attendee crossing between the
 * shopper-facing storefront and the operator-facing observatory sees
 * the same chip with the same name in both places. When a name needs
 * to change, change it here and both surfaces update.
 *
 * Naming rule: snake_dot — `<noun>.<verb>` lowercase, dot-separated.
 * Examples: memory.recall, inventory.live, trend.signal. Stays
 * consistent with the Atelier's existing tool-registry vocabulary
 * (`product_search`, `discover_tools`, `aurora_*`) while keeping the
 * Boutique-facing names compact enough to fit inline on a product
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
  | 'curator.signal'
  | 'tool.transparency'

interface AgentToolEntry {
  /** Canonical machine-readable name. */
  name: AgentToolName
  /** Human-readable label for tooltips and Atelier deep links. */
  label: string
  /** One-line glossary, attendee-friendly. */
  description: string
  /**
   * Atelier route this concept is explained on. Used by the
   * "How this works" link from a Boutique chip into the Atelier.
   */
  atelierPath: string
}

export const AGENT_VOCABULARY: Record<AgentToolName, AgentToolEntry> = {
  'memory.recall': {
    name: 'memory.recall',
    label: 'Memory recall',
    description:
      'The agent surfacing something it remembers about you from a previous session.',
    atelierPath: '/atelier/memory',
  },
  'memory.seed': {
    name: 'memory.seed',
    label: 'Memory seed',
    description:
      'First-time-visitor onboarding — the agent hasn’t learned your taste yet, but it will.',
    atelierPath: '/atelier/memory',
  },
  'memory.write': {
    name: 'memory.write',
    label: 'Memory write',
    description:
      'The agent recording a new fact about you (saved item, size, taste signal) for next time.',
    atelierPath: '/atelier/memory',
  },
  'inventory.live': {
    name: 'inventory.live',
    label: 'Live inventory',
    description: 'A live read against the catalog — what is actually in stock right now.',
    atelierPath: '/atelier/tools',
  },
  'inventory.watch': {
    name: 'inventory.watch',
    label: 'Inventory watch',
    description: 'The agent tracking restocks and surfacing them when something you wanted returns.',
    atelierPath: '/atelier/tools',
  },
  'inventory.search': {
    name: 'inventory.search',
    label: 'Inventory search',
    description: 'A semantic search over the catalog driven by a shopper’s natural-language query.',
    atelierPath: '/atelier/tools',
  },
  'trend.signal': {
    name: 'trend.signal',
    label: 'Trend signal',
    description: 'Aggregated shopping behavior — what is moving fast across the floor right now.',
    atelierPath: '/atelier/tools',
  },
  'pairing.score': {
    name: 'pairing.score',
    label: 'Pairing score',
    description: 'How well two pieces go together — palette, weight, occasion, style memory.',
    atelierPath: '/atelier/tools',
  },
  'palette.match': {
    name: 'palette.match',
    label: 'Palette match',
    description: 'A color-and-tone match between a candidate piece and a shopper’s saved palette.',
    atelierPath: '/atelier/tools',
  },
  'memory.holds': {
    name: 'memory.holds',
    label: 'Memory holds',
    description: 'Items the agent is keeping in your bag from a previous session.',
    atelierPath: '/atelier/memory',
  },
  'experience.return': {
    name: 'experience.return',
    label: 'Returns & experience',
    description: 'The Experience Guide handling a return, refund, or post-purchase issue.',
    atelierPath: '/atelier/agents',
  },
  'weather.lookup': {
    name: 'weather.lookup',
    label: 'Weather lookup',
    description: 'A live weather call to ground a recommendation in the conditions you’re shopping for.',
    atelierPath: '/atelier/tools',
  },
  'tag.match': {
    name: 'tag.match',
    label: 'Tag match',
    description: 'A direct match against the product taxonomy (linen, travel, ceramic, etc).',
    atelierPath: '/atelier/tools',
  },
  'curator.signal': {
    name: 'curator.signal',
    label: 'Curator signal',
    description: 'An editorial pick — a piece our human curators are reaching for this week.',
    atelierPath: '/atelier/agents',
  },
  'tool.transparency': {
    name: 'tool.transparency',
    label: 'Tool transparency',
    description: 'Every recommendation cites the tool that produced it. No black box.',
    atelierPath: '/atelier/tools',
  },
}

/** Skills router — loaded skill chips in Boutique chat attribution. */
const SKILL_VOCABULARY: Record<string, AgentToolEntry> = {
  'skill.style-advisor': {
    name: 'skill.style-advisor' as AgentToolName,
    label: 'Style Advisor',
    description: 'Personal styling and wardrobe pairing for the active shopper.',
    atelierPath: '/atelier/skills',
  },
  'skill.gift-concierge': {
    name: 'skill.gift-concierge' as AgentToolName,
    label: 'Gift Concierge',
    description: 'Gift-ready picks with wrapping and occasion context.',
    atelierPath: '/atelier/skills',
  },
  'skill.packing-list': {
    name: 'skill.packing-list' as AgentToolName,
    label: 'The Packing List',
    description: 'Travel and capsule packing recommendations.',
    atelierPath: '/atelier/skills',
  },
  'skill.gift-table': {
    name: 'skill.gift-table' as AgentToolName,
    label: 'The Gift Table',
    description: 'Curated gift-ready pieces for thoughtful giving.',
    atelierPath: '/atelier/skills',
  },
  'skill.makers-shelf': {
    name: 'skill.makers-shelf' as AgentToolName,
    label: "The Maker's Shelf",
    description: 'Hand-thrown ceramics and slow-living home pieces.',
    atelierPath: '/atelier/skills',
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
    // but use the canonical entry for the description + atelierPath.
    return { ...known, name: name as AgentToolName }
  }
  return {
    name: name as AgentToolName,
    label: canonical,
    description: 'An agent tool call. See the Atelier for details.',
    atelierPath: '/atelier/tools',
  }
}
