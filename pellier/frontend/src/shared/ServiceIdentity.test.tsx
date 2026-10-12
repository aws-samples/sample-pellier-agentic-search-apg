import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ServiceIdentity, { serviceIdentity } from './ServiceIdentity'

describe('service provenance identity', () => {
  it.each([
    ['Amazon Aurora', 'aurora', 'Database records'],
    ['AgentCore Memory', 'agentcore', 'Remembered context'],
    ['Amazon Bedrock AgentCore Gateway', 'agentcore', 'Tool access'],
    ['AgentCore Policy', 'agentcore', 'Policy evaluation'],
    ['AgentCore Runtime', 'agentcore', 'Managed execution'],
    ['Amazon Bedrock', 'bedrock', 'Model response'],
    ['Strands Graph', 'strands', 'Agent orchestration'],
    ['AWS Step Functions', 'stepfunctions', 'Fulfillment workflow'],
    ['AWS Lambda', 'lambda', 'Workflow task'],
    ['Amazon CloudWatch', 'cloudwatch', 'Operational telemetry'],
  ])('identifies the recorded source %s without losing its role', (source, service, role) => {
    expect(serviceIdentity(source)).toEqual({ service, role })
    const { container } = render(<ServiceIdentity source={source} />)
    expect(screen.getByText(source)).toBeInTheDocument()
    expect(screen.getByText(role)).toBeInTheDocument()
    expect(container.querySelector('img')).toHaveAttribute('alt', '')
  })

  it.each(['Local PostgreSQL', 'Memory', 'Policy check', 'Ticket system'])('does not attribute %s to an AWS service', source => {
    expect(serviceIdentity(source)).toEqual({})
  })
})
