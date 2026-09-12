import { FileText } from 'lucide-react'
import { imageSrc } from '../utils/assetPath'
import './service-identity.css'

export type ServiceName = 'aurora' | 'agentcore' | 'bedrock' | 'strands' | 'stepfunctions' | 'lambda' | 'cloudwatch'

const LOGOS: Record<ServiceName, string> = {
  aurora: '/assets/icons/aws/amazon-aurora.svg',
  agentcore: '/assets/icons/aws/amazon-bedrock-agentcore.svg',
  bedrock: '/assets/icons/aws/amazon-bedrock.svg',
  strands: '/services/strands.png',
  stepfunctions: '/assets/icons/aws/aws-step-functions.svg',
  lambda: '/assets/icons/aws/aws-lambda.svg',
  cloudwatch: '/assets/icons/aws/amazon-cloudwatch.svg',
}

export function ServiceLogo({ service, size = 24 }: { service: ServiceName; size?: number }) {
  return <img className="operator-service-logo" src={imageSrc(LOGOS[service])} alt="" width={size} height={size} />
}

/** Only identify named services. "Memory" alone does not prove AgentCore. */
export function serviceIdentity(source: string): { service?: ServiceName; role?: string } {
  const value = source.toLowerCase().replace(/[_-]/g, ' ')
  if (value.includes('aurora')) return { service: 'aurora', role: 'Database records' }
  if (value.includes('step functions')) return { service: 'stepfunctions', role: 'Fulfillment workflow' }
  if (value.includes('aws lambda')) return { service: 'lambda', role: 'Workflow task' }
  if (value.includes('cloudwatch')) return { service: 'cloudwatch', role: 'Operational telemetry' }
  if (value.includes('agentcore')) {
    const role = value.includes('memory') ? 'Remembered context'
      : value.includes('policy') ? 'Policy evaluation'
        : value.includes('gateway') ? 'Tool access'
          : value.includes('runtime') ? 'Managed execution'
            : 'Agent service'
    return { service: 'agentcore', role }
  }
  if (value.includes('strands')) return { service: 'strands', role: 'Agent orchestration' }
  if (value.includes('bedrock')) return { service: 'bedrock', role: 'Model response' }
  return {}
}

export default function ServiceIdentity({ source, showRole = true }: { source: string; showRole?: boolean }) {
  const { service, role } = serviceIdentity(source)
  return (
    <span className="service-identity" data-service={service ?? 'other'}>
      {service ? <ServiceLogo service={service} size={22} /> : <FileText size={17} aria-hidden="true" />}
      <span className="service-identity-copy">
        <span>{source}</span>
        {showRole && role ? <small>{role}</small> : null}
      </span>
    </span>
  )
}
