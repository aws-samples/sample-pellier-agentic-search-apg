/**
 * Workshop Bedrock inference profile IDs (single source for copy + Telemetry).
 *
 * Current release defaults for Telemetry and teaching surfaces. Recorded
 * sessions retain the original model IDs that produced their evidence.
 */
export const BEDROCK_INFERENCE_PROFILES = {
  CLAUDE_OPUS_5: 'global.anthropic.claude-opus-5',
  CLAUDE_SONNET_5: 'global.anthropic.claude-sonnet-5',
  CLAUDE_HAIKU_4_5: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
  COHERE_EMBED_V4: 'us.cohere.embed-v4:0',
  COHERE_RERANK_V35: 'cohere.rerank-v3-5:0',
} as const
