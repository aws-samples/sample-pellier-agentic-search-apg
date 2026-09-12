/**
 * Operator Concierge API client and types.
 *
 * Server truth only. The browser submits an operator message and nothing else — no
 * role, no turn id, no artifact, no evidence, no review state. Every one of those is
 * a claim about what happened rather than a request to do something, so the backend
 * owns them.
 */

export type TurnState = 'incomplete' | 'complete' | 'failed' | ''

export interface ConciergeInvestigationStep {
  kind: string
  label: string
  /** Only systems that actually participated. No architecture theatre. */
  source: string
  status: string
  durationMs?: number | null
  result?: string
  metadata?: ConciergeOrchestration
}

export interface ShopperHandoff {
  schemaVersion: string
  trust: 'UNTRUSTED_SHOPPER_CONTEXT' | string
  checkpoint: 'WAITING_FOR_HUMAN' | string
  customerId: string
  source: {
    sessionId?: string | null
    turnId: string
  }
  shopperRequest: string
  transcriptExcerpt?: {
    role: 'user' | 'assistant'
    content: string
    truncated?: string
  }[]
  assistantResponseExcerpt?: string
  routing: {
    specialist?: string
    tools?: string[]
  }
  proposal: {
    reviewId: number
    action: string
    actionHash: string
  }
  evidenceRefs?: { kind: string; id: string | number }[]
}

export interface ConciergeGraphNode {
  nodeId: string
  kind?: string
  status: string
  durationMs?: number | null
}

export interface ConciergeOrchestration {
  graphId?: string
  pattern?: string
  execution?: string
  deploymentTarget?: string
  runtimeArn?: string
  runtimeSessionId?: string
  buildFingerprint?: string
  fingerprintMatches?: boolean
  requestId?: string
  agents?: string[]
  executedNodes?: ConciergeGraphNode[]
  durationMs?: number | null
  status?: string
  checkpoint?: {
    state?: string
    reviewId?: number | null
    actionHash?: string
  }
}

export interface ConciergeEvidenceItem {
  kind: string
  /**
   * The epistemic role, and the reason this contract exists. A ticket REPORTING a
   * return is `context`; the returns table holding zero rows is `fact`. Rendering
   * them identically is how "a support ticket says a return arrived" becomes
   * "she returned it".
   */
  role?: 'fact' | 'context' | 'inference' | string
  status: 'verified' | 'unverified' | 'unavailable' | string
  source: string
  label?: string
  recordId?: string
  note?: string
  data?: Record<string, unknown>
}

/** One labelled prose block beneath the primary answer. */
export interface ConciergeSection {
  id: string
  label: string
  /** `context` marks operator-only or unconfirmed material, styled apart. */
  tone: string
  body: string
}

/**
 * One canonical recommendation. The narrative and the product card both render from
 * this object, which is what makes the reference implementation's contradiction —
 * prose saying "remains in stock" beside a card reading "Out of stock" — impossible
 * rather than merely discouraged. Price, identity and availability are backend facts;
 * the model contributes none of them.
 */
export interface ConciergeRecommendation {
  productId: string
  name: string
  brand: string
  category: string
  price: number
  imgUrl: string
  /** `best_match` or `alternative`. There is no `upgrade`: see the backend note. */
  role: string
  fitReasons: string[]
  priceDeltaUsd?: number | null
  /** The same object `inventory_evidence.py` produces. One availability truth. */
  inventoryEvidence: {
    status: string
    availableQuantity?: number | null
    authority?: string | null
    reconciledToLedger?: boolean
    aggregateCacheStale?: boolean
    catalogCacheQuantity?: number | null
    catalogLedgerQuantity?: number | null
    disagreements?: { warehouseId: string; cacheQuantity: number; ledgerQuantity: number }[]
    locations?: {
      warehouseId: string
      quantity: number
      cacheQuantity?: number
      ledgerQuantity?: number | null
      displayName?: string | null
      city?: string | null
    }[]
    note?: string
  }
  /** Backend-authored sentence. Never assembled in the browser. */
  availabilitySentence: string
  retrievalEvidence?: { rerankScore?: number | null; rrfScore?: number | null }
}

/** What a Replacement Search turn established. */
/** One recorded outcome from Aurora episodic memory, and how it was matched. */
export interface ConciergePriorResolutions {
  episodes: ConciergeEpisode[]
  retrieval?: {
    /** `semantic` when an embedding was available, `recent` when it was not. */
    mode: 'semantic' | 'recent'
    matched: number
  }
}

/**
 * A derived memory of one reviewed execution.
 *
 * The three outcomes stay separate for the same reason the Action Assurance axes do:
 * they answer different questions and regularly disagree.
 */
export interface ConciergeEpisode {
  episodeId: number | null
  customerId: string
  episodeType: string
  situation: string
  resolution: string
  humanOutcome: string
  policyOutcome: string
  auroraOutcome: string
  /** The human decision this outcome ran under, and the link to its evidence. */
  reviewId: number | null
  executionTurnId: string
  sourceTurnId: string
  createdAt: string | null
  /** Cosine similarity when the recall was semantic. Not shown on the operator card. */
  similarity: number | null
  evidenceSummary: Record<string, unknown>
  actionSummary: Record<string, unknown>
}

export interface ConciergeReplacement {
  plan?: {
    original?: {
      orderId: number
      productId: string
      name: string
      category: string
      price: number
      imgUrl?: string
    }
    hardConstraints?: {
      priceMaxUsd?: number | null
      categories?: string[]
      availabilityRequirement?: string
      excludesProductId?: string
    }
    priceAnchorUsd?: number | null
    priceCeilingSource?: string
    describeHardControls?: string[]
  }
  available?: ConciergeRecommendation[]
  closeMatches?: ConciergeRecommendation[]
  retrieval?: {
    poolSize: number
    afterHardConstraints: number
    reranked: number
    reconciledCount?: number
    rerankApplied: boolean
    strategy: string
  }
  coverageNote?: string
  grounding?: {
    resolved: boolean
    reason?: string
    matchedOn?: string
    candidates?: { orderId: number; productId: string; name: string; price: number }[]
  }
}

/**
 * One consequential action prepared for human review.
 *
 * Five states that do not imply one another: this object says an action was PREPARED.
 * It does not say a human decided, that AgentCore Policy authorized it, that Aurora
 * permitted it, or that anything executed. `executionCapability` is separate from the
 * review for exactly that reason.
 */
export interface ConciergeProposedAction {
  tool: string
  /**
   * `review_required` a review is open and awaiting a person
   * `review_already_open` this exact action was already awaiting a decision
   * `not_enabled` the capability is not published, so no review was created
   * `could_not_prepare_review` the action was established, the review was not
   */
  state: string
  reviewId?: number | null
  customer?: { customerId?: string }
  order?: { orderId?: number | null; placedAt?: string | null }
  product?: {
    productId?: string
    name?: string
    category?: string
    price?: number
    imgUrl?: string
  }
  /** Exactly the parameters the fingerprint covers and a human confirms. */
  material?: { customer_id?: string; product_id?: number; reason?: string }
  actionHash?: string
  executionCapability?: { state: string; reason?: string; executable?: boolean }
  reviewSourceTurnId?: string
  note?: string
}

/** Persisted assistant output. Structured, never arbitrary Markdown. */
export interface ConciergeArtifact {
  /** Which read workflow produced this. Absent on turns written before v2. */
  workflow?: string
  investigation?: ConciergeInvestigationStep[]
  evidence?: ConciergeEvidenceItem[]
  summary?: string
  /**
   * How to label `summary`. Empty for a plain summary; a draft carries
   * "Draft — not sent", because unlabelled customer-facing copy invites being
   * treated as something Pellier already sent.
   */
  primaryLabel?: string
  /** A standing caveat rendered with the primary block. */
  primaryNote?: string
  /** Additional labelled blocks. Empty sections are never sent. */
  sections?: ConciergeSection[]
  recommendation?: { title?: string; body?: string } | null
  /** Present only on a `replacement_search` turn. */
  replacement?: ConciergeReplacement
  /**
   * Present only when the operator asked what happened in comparable situations.
   *
   * Not attached to every turn on purpose: recall costs a Bedrock embedding call and a
   * vector scan, and a prior-resolution card that appears beside every summary is one
   * an operator learns to skip.
   */
  priorResolutions?: ConciergePriorResolutions
  products?: unknown[]
  /** Empty for every read workflow. Only explicit consequential intent fills it. */
  proposedActions?: ConciergeProposedAction[]
  /** Only systems that actually participated, with what each contributed. */
  sources?: { source: string; detail: string }[]
  modelId?: string
  capabilityObservation?: { capability: string; state: string; observedAt?: string }[]
  /** Immutable shopper context, kept separate from current PostgreSQL facts. */
  shopperHandoff?: ShopperHandoff | null
  /** Actual graph metadata, never a reconstructed reasoning trace. */
  orchestration?: ConciergeOrchestration
}

export interface ConciergeMessage {
  messageId: number
  role: 'user' | 'assistant'
  content: string
  turnId: string
  turnState: TurnState
  actorType: string
  artifact?: ConciergeArtifact | null
  artifactVersion?: number | null
  createdAt: string | null
}

export interface ConciergeSession {
  sessionId: string
  customerId: string
  surface: string
  createdBy: string
  messages: ConciergeMessage[]
  truncated: boolean
}

export interface ConciergeConfig {
  composerEnabled: boolean
  /** Runtime truth: Local PostgreSQL here, Aurora PostgreSQL on the workshop box. */
  dataSource?: string
  /**
   * The workflow kinds the orchestrator actually implements, published by the server.
   *
   * The UI gates suggestion visibility on this. A template that advertises a workflow
   * the backend does not run would execute something else — the exact semantic drift
   * this surface exists to eliminate — so the server's list is the authority for what
   * may be offered, not a frontend constant that can fall out of step.
   */
  supportedWorkflowKinds?: string[]
  orchestrationAvailable?: boolean
  orchestration: string
  note: string
}

export interface ConciergeTurn {
  messageId: number
  sessionId: string
  turnId: string
  role: string
  content: string
  turnState: TurnState
  replayed: boolean
}

/** A server-owned answer emitted only after the durable transcript write succeeds. */
export interface ConciergeStreamAnswer extends ConciergeArtifact {
  sessionId: string
  turnId: string
  status: TurnState
  replayed: boolean
  summary: string
}
