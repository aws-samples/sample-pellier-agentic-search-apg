import type React from 'react';

export const ARCHITECTURE_CODE_BLOCK: React.CSSProperties = {
  fontFamily: 'var(--dl-font-mono)',
  fontSize: '12.5px',
  lineHeight: 1.6,
  background: 'var(--dl-ink)',
  color: 'var(--dl-accent-soft)',
  borderRadius: 'var(--dl-r-lg)',
  border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
  padding: '14px 16px',
  margin: 0,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

export const ARCHITECTURE_CODE_BLOCK_COMPACT: React.CSSProperties = {
  ...ARCHITECTURE_CODE_BLOCK,
  fontSize: '11.5px',
  padding: '10px 12px',
};
