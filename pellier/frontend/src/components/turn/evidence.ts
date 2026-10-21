/**
 * The Builder view's mono evidence line, composed from structured fields the
 * backend emitted. Nothing here is parsed back out of prose.
 */
import { TURN_PRINCIPAL } from '../../copy'
import type { IdentityBinding, StepBuilder, TurnPrincipal, TurnStep } from './turnTypes'

/** "Workshop sign-in, CUST-THEO": who the server verified for one turn. */
export function principalLine(principal: TurnPrincipal): string {
  if (!principal.authenticated) return TURN_PRINCIPAL.NOT_SIGNED_IN
  const how = principal.signInMethod === 'workshop' ? TURN_PRINCIPAL.WORKSHOP : TURN_PRINCIPAL.SIGNED_IN
  return `${how}, ${principal.customerId ?? TURN_PRINCIPAL.NO_CUSTOMER}`
}

export function identitySentence(identity: IdentityBinding): string {
  const { binding, requested_customer: requested, bound_customer: bound, authorized_customer: authorized } = identity
  switch (binding) {
    case 'overwritten':
      // The managed rail emits a requested id only in the customer-id shape;
      // anything else the model named is reported as another customer.
      return `model asked for ${requested ?? 'another customer'}, server bound ${bound} (overwritten)`
    case 'matched':
    case 'bound':
      return `bound ${bound}`
    case 'refused':
      if (requested && authorized) return `model asked for ${requested}, server refused; signed in as ${authorized}`
      if (requested) return `model asked for ${requested}, refused: no signed-in account`
      return 'refused: no signed-in account'
    case 'unbound':
      return 'no signed-in account, handoff ran unbound'
    default:
      return ''
  }
}

/** "Remembered: AgentCore Memory record mem-1 (user preference)": what Memory gave the agent. */
export function rememberedSentence(records: string[]): string {
  const noun = records.length === 1 ? 'record' : 'records'
  return `Remembered: AgentCore Memory ${noun} ${records.join(', ')} (user preference)`
}

/** Memory was read for this customer and held no preference: the agent was given none. */
const REMEMBERED_NONE = 'Remembered: no AgentCore Memory record (user preference)'

/** The read failed: the turn went on with no remembered preference, and says which failure. */
export function rememberedFailedSentence(error: string): string {
  return `Remembered: AgentCore Memory read failed (${error}); none given`
}

/**
 * "Stock agent may call: check_stock; prompt rule: "Every stock answer starts
 * from check_stock"": the tools the running agent was built with, beside the
 * prompt's rule that keeps it on the right one.
 */
export function grantSentence(agent: string | undefined, grant: { tools: string[]; rule?: string | null }): string {
  const tools = grant.tools.length ? grant.tools.join(', ') : 'no store tools'
  const head = `${agent || 'The agent'} may call: ${tools}`
  return grant.rule ? `${head}; prompt rule: "${grant.rule}"` : head
}

export function evidenceLine(step: TurnStep): string {
  const builder = step.builder
  if (!builder) return ''
  const parts: string[] = []
  if (builder.tool === null) {
    if (builder.intent) parts.push(`intent ${builder.intent}`)
    if (builder.model_id) parts.push(`model ${builder.model_id}`)
    if (builder.grant) parts.push(grantSentence(builder.agent, builder.grant))
    if (builder.memory) parts.push(`${builder.memory.facts} facts, ${builder.memory.orders} orders from ${builder.memory.source}`)
    if (builder.remembered?.error) parts.push(rememberedFailedSentence(builder.remembered.error))
    else if (builder.remembered?.records.length) parts.push(rememberedSentence(builder.remembered.records))
    else if (builder.remembered) parts.push(REMEMBERED_NONE)
    if (builder.skills && builder.skills.length > 0) {
      const mode = builder.skills[0].loaded
      parts.push(`skills ${builder.skills.map(skill => skill.name).join(', ')} (${mode})`)
    } else if (builder.skill_mode === 'on_demand') {
      parts.push('skills on demand')
    }
    if (builder.note) parts.push(builder.note)
    // Thinking and the answer share one token budget; a turn that stopped at
    // max_tokens is a cut answer, not a short one.
    if (builder.stop_reason === 'max_tokens') parts.push('answer cut short (max_tokens)')
    else if (builder.stop_reason && builder.stop_reason !== 'end_turn') parts.push(`stop ${builder.stop_reason}`)
    return parts.join('; ')
  }
  if (builder.tool) parts.push(`tool ${builder.tool}`)
  if (builder.model_id) parts.push(`model ${builder.model_id}`)
  if (builder.outcome && builder.outcome !== 'ok') parts.push(`outcome ${builder.outcome}`)
  if (builder.query) parts.push(`searched "${builder.query}"`)
  if (builder.identity) parts.push(identitySentence(builder.identity))
  if (builder.requirements?.carried?.length) {
    parts.push(`kept from earlier: ${builder.requirements.carried.join(', ')}`)
  }
  if (builder.audit_id != null) parts.push(`audit row ${builder.audit_id}`)
  if (builder.receipt_id != null) parts.push(`receipt ${builder.receipt_id}`)
  if (builder.tool === 'skills' && builder.skills?.length) {
    parts.push(builder.skills.map(skill => skill.path).join(', '))
  }
  if (builder.rail) parts.push(`rail ${builder.rail}`)
  if (builder.duration_ms != null) parts.push(`${builder.duration_ms} ms`)
  return parts.join('; ')
}

/** One piece of a fact's value: plain words, a code chip, or an id chip with a copy control. */
export type FactPart =
  | { kind: 'text'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'id'; text: string; noun: string }

/** One labelled row of a step's Builder evidence. */
export interface EvidenceFact {
  label: string
  parts: FactPart[]
}

const text = (value: string): FactPart => ({ kind: 'text', text: value })
const code = (value: string): FactPart => ({ kind: 'code', text: value })
const id = (value: string | number, noun: string): FactPart => ({ kind: 'id', text: String(value), noun })
const codes = (values: string[]): FactPart[] => values.map(code)

function routerMemoryFacts(builder: StepBuilder): EvidenceFact[] {
  const facts: EvidenceFact[] = []
  if (builder.memory) {
    const { facts: count, orders, source } = builder.memory
    facts.push({ label: 'Customer record', parts: [text(`${count} facts, ${orders} orders from ${source}`)] })
  }
  const remembered = builder.remembered
  if (!remembered) return facts
  if (remembered.error) {
    facts.push({ label: 'Memory', parts: [text(`AgentCore Memory read failed (${remembered.error}); none given`)] })
  } else if (remembered.records.length > 0) {
    const noun = remembered.records.length === 1 ? 'record' : 'records'
    facts.push({
      label: 'Memory',
      parts: [
        text(`AgentCore Memory ${noun}, user preference`),
        ...remembered.records.map(record => id(record, 'memory record id')),
      ],
    })
  } else {
    facts.push({ label: 'Memory', parts: [text('No AgentCore Memory record (user preference)')] })
  }
  return facts
}

function routerFacts(builder: StepBuilder): EvidenceFact[] {
  const facts: EvidenceFact[] = []
  if (builder.intent) facts.push({ label: 'Intent', parts: [text(builder.intent)] })
  if (builder.model_id) facts.push({ label: 'Model', parts: [code(builder.model_id)] })
  if (builder.grant) {
    const { tools, rule } = builder.grant
    const who = text(`${builder.agent || 'The agent'}:`)
    facts.push({ label: 'May call', parts: [who, ...(tools.length ? codes(tools) : [text('no store tools')])] })
    if (rule) facts.push({ label: 'Prompt rule', parts: [text(`"${rule}"`)] })
  }
  facts.push(...routerMemoryFacts(builder))
  if (builder.skills && builder.skills.length > 0) {
    facts.push({
      label: 'Skills',
      parts: [...codes(builder.skills.map(skill => skill.name)), text(`(${builder.skills[0].loaded})`)],
    })
  } else if (builder.skill_mode === 'on_demand') {
    facts.push({ label: 'Skills', parts: [text('Loaded on demand')] })
  }
  if (builder.note) facts.push({ label: 'Note', parts: [text(builder.note)] })
  if (builder.stop_reason === 'max_tokens') {
    facts.push({ label: 'Stop', parts: [text('Answer cut short (max_tokens)')] })
  } else if (builder.stop_reason && builder.stop_reason !== 'end_turn') {
    facts.push({ label: 'Stop', parts: [code(builder.stop_reason)] })
  }
  return facts
}

/**
 * A tool step names the tool and the model that called it, and how a call that did
 * not answer ended: failed, invalid input, denied by policy, not held or cancelled.
 */
function toolFacts(builder: StepBuilder): EvidenceFact[] {
  const facts: EvidenceFact[] = []
  if (builder.tool) facts.push({ label: 'Tool', parts: [code(builder.tool)] })
  if (builder.model_id) facts.push({ label: 'Model', parts: [code(builder.model_id)] })
  if (builder.outcome && builder.outcome !== 'ok') {
    facts.push({ label: 'Outcome', parts: [code(builder.outcome)] })
  }
  if (builder.query) facts.push({ label: 'Searched', parts: [text(`"${builder.query}"`)] })
  if (builder.identity) facts.push({ label: 'Identity', parts: [text(identitySentence(builder.identity))] })
  if (builder.requirements?.carried?.length) {
    facts.push({ label: 'Kept from earlier', parts: [text(builder.requirements.carried.join(', '))] })
  }
  if (builder.audit_id != null) facts.push({ label: 'Audit row', parts: [id(builder.audit_id, 'audit row id')] })
  if (builder.receipt_id != null) facts.push({ label: 'Receipt', parts: [id(builder.receipt_id, 'receipt id')] })
  if (builder.tool === 'skills' && builder.skills?.length) {
    facts.push({ label: 'Files', parts: codes(builder.skills.map(skill => skill.path)) })
  }
  if (builder.rail) facts.push({ label: 'Rail', parts: [code(builder.rail)] })
  if (builder.duration_ms != null) facts.push({ label: 'Took', parts: [text(`${builder.duration_ms} ms`)] })
  return facts
}

/**
 * The same evidence `evidenceLine` joins with semicolons, as labelled rows: what the
 * Builder view draws. Both read the backend's structured fields; nothing is parsed
 * back out of the joined line.
 */
export function evidenceFacts(step: TurnStep): EvidenceFact[] {
  const builder = step.builder
  if (!builder) return []
  return builder.tool === null ? routerFacts(builder) : toolFacts(builder)
}
