import { describe, expect, it } from 'vitest'
import { awsServiceMark } from './awsServiceMarks'

describe('awsServiceMark', () => {
  it('names the managed service behind a source row', () => {
    expect(awsServiceMark('Aurora PostgreSQL')?.label).toBe('Amazon Aurora')
    expect(awsServiceMark('Amazon Bedrock')?.label).toBe('Amazon Bedrock')
    expect(awsServiceMark('AgentCore Memory')?.label).toBe(
      'Amazon Bedrock AgentCore',
    )
  })

  // The label already refuses to call a non-RDS host Aurora. An Aurora mark
  // beside it would re-assert precisely what the label declined to claim —
  // and every local box, including one tunnelled to a real cluster, reads
  // "Local PostgreSQL".
  it('gives a local database no Aurora mark', () => {
    expect(awsServiceMark('Local PostgreSQL')).toBeNull()
    expect(awsServiceMark('PostgreSQL')).toBeNull()
  })

  it('prefers the AgentCore mark over the plain Bedrock one', () => {
    expect(awsServiceMark('Bedrock AgentCore')?.src).toContain('agentcore')
  })

  it('returns null for anything that is not a named AWS service', () => {
    expect(awsServiceMark('Pellier build state')).toBeNull()
    expect(awsServiceMark('unavailable')).toBeNull()
    expect(awsServiceMark('')).toBeNull()
    expect(awsServiceMark(undefined)).toBeNull()
  })
})
