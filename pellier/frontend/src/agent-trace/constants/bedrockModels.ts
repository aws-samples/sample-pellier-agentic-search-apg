/**
 * Workshop Bedrock inference profile IDs (single source for copy + Telemetry).
 *
 * Aligns session fixtures, Telemetry tab, and teaching surfaces with the
 * Opus + Sonnet global inference profiles used by the workshop stack.
 */
export const BEDROCK_INFERENCE_PROFILES = {
  CLAUDE_OPUS_5: 'global.anthropic.claude-opus-5',
  CLAUDE_SONNET_5: 'global.anthropic.claude-sonnet-5',
  COHERE_EMBED_V4: 'us.cohere.embed-v4:0',
  COHERE_RERANK_V35: 'cohere.rerank-v3-5:0',
} as const
