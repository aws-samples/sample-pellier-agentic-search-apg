/**
 * Official AWS Architecture Icons for the sources a turn actually used.
 *
 * A generic database cylinder and a sparkle cannot say *which* managed service
 * answered, and naming the service is most of what the source rows are for.
 * The marks are used unmodified and only scaled; see
 * `public/assets/icons/aws/AWS-ARCHITECTURE-ICONS-NOTICE.txt`.
 */
export interface AwsServiceMark {
  /** Root-relative path; resolve through `imageSrc()` before assigning to src. */
  src: string
  /** The service's full name, for an accessible label or a tooltip. */
  label: string
}

/**
 * Order matters. `agentcore` is tested before `bedrock` so a label like
 * "Bedrock AgentCore" resolves to the AgentCore mark rather than the plain
 * Bedrock one.
 */
const MARKS: ReadonlyArray<{ match: string } & AwsServiceMark> = [
  {
    match: 'aurora',
    src: '/assets/icons/aws/amazon-aurora.svg',
    label: 'Amazon Aurora',
  },
  {
    match: 'agentcore',
    src: '/assets/icons/aws/amazon-bedrock-agentcore.svg',
    label: 'Amazon Bedrock AgentCore',
  },
  {
    match: 'bedrock',
    src: '/assets/icons/aws/amazon-bedrock.svg',
    label: 'Amazon Bedrock',
  },
]

/**
 * The AWS mark for a source label, or null when the source is not a named
 * AWS service.
 *
 * `Local PostgreSQL` and a bare `PostgreSQL` deliberately return null.
 * `database_source_label()` refuses to call a non-RDS host Aurora — a local
 * box, or a tunnel to one — and an Aurora mark beside that label would
 * re-assert exactly what the label just declined to claim.
 */
export function awsServiceMark(source: string | null | undefined): AwsServiceMark | null {
  if (!source) return null
  const value = source.toLowerCase()
  const hit = MARKS.find((mark) => value.includes(mark.match))
  return hit ? { src: hit.src, label: hit.label } : null
}
