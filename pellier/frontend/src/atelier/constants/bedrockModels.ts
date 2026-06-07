/**
 * Workshop Bedrock inference profile IDs (single source for copy + Telemetry).
 *
 * Aligns session fixtures, Telemetry tab, and teaching surfaces with the
 * models available in this deployment — no Sonnet SKU.
 */
export const BEDROCK_INFERENCE_PROFILES = {
  CLAUDE_OPUS_46: 'global.anthropic.claude-opus-4-6-v1',
  CLAUDE_HAIKU_45: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
  COHERE_EMBED_V4: 'us.cohere.embed-v4:0',
  COHERE_RERANK_V35: 'cohere.rerank-v3-5:0',
} as const
