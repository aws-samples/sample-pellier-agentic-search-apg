/**
 * The Builder view's mono evidence line, composed from structured fields the
 * backend emitted. Nothing here is parsed back out of prose.
 */
import type { IdentityBinding, TurnStep } from './turnTypes'

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

export function evidenceLine(step: TurnStep): string {
  const builder = step.builder
  if (!builder) return ''
  const parts: string[] = []
  if (builder.tool === null) {
    if (builder.intent) parts.push(`intent ${builder.intent}`)
    if (builder.model_id) parts.push(`model ${builder.model_id}`)
    if (builder.memory) parts.push(`${builder.memory.facts} facts, ${builder.memory.orders} orders from ${builder.memory.source}`)
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
