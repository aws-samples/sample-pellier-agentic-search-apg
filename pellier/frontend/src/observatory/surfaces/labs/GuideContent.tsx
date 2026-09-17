import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { imageSrc } from '../../../utils/assetPath';

export interface GuideNode {
  kind: string;
  text?: string;
  title?: string;
  tone?: string;
  id?: string;
  level?: number;
  headers?: string[];
  rows?: string[][];
  children?: GuideNode[];
}

function plainText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(plainText).join('');
  if (node && typeof node === 'object' && 'props' in node) {
    return plainText((node.props as { children?: ReactNode }).children);
  }
  return '';
}

function CopyableCode({ children }: { children?: ReactNode }) {
  const [state, setState] = useState('Copy code');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plainText(children).replace(/\n$/, ''));
      setState('Copied');
    } catch {
      setState('Select and copy the code below');
    }
  };
  return <div className="guide-code">
    <button type="button" onClick={() => void copy()}>{state}</button>
    <span className="sr-only" role="status">{state === 'Copy code' ? '' : state}</span>
    <pre tabIndex={0}>{children}</pre>
  </div>;
}

function Markdown({ text }: { text: string }) {
  return <ReactMarkdown components={{
    a: ({ href, children }) => href?.startsWith('/observatory/')
      ? <Link to={href}>{children}</Link>
      : <a href={href?.startsWith('/workshop-guides/') ? imageSrc(href) : href}>{children}</a>,
    img: ({ src, alt }) => <img src={src?.startsWith('/') ? imageSrc(src) : src} alt={alt ?? ''} loading="lazy" decoding="async" />,
    pre: ({ children }) => <CopyableCode>{children}</CopyableCode>,
  }}>{text}</ReactMarkdown>;
}

export default function GuideContent({ nodes }: { nodes: GuideNode[] }) {
  return <>{nodes.map((node, index) => {
    const children = <GuideContent nodes={node.children ?? []} />;
    if (node.kind === 'markdown') return <Markdown key={index} text={node.text ?? ''} />;
    if (node.kind === 'heading') {
      const Heading = `h${Math.min(6, Math.max(2, node.level ?? 2))}` as 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
      return <Heading key={index} id={node.id}>{node.text}</Heading>;
    }
    if (node.kind === 'expand') return <details key={index} className="guide-expander">
      <summary>{node.title}</summary><div>{children}</div>
    </details>;
    if (node.kind === 'alert') return <aside key={index} className="guide-notice" data-tone={node.tone}>
      {node.title && <strong>{node.title}</strong>}{children}
    </aside>;
    if (node.kind === 'tab') return <details key={index} className="guide-expander" open={node.title?.toLowerCase().includes('manual')}>
      <summary>{node.title}</summary><div>{children}</div>
    </details>;
    if (node.kind === 'table') return <div key={index} className="guide-table-scroll" tabIndex={0} role="region" aria-label="Guide reference table">
      <table><thead><tr>{node.headers?.map((cell, i) => <th key={i} scope="col"><Markdown text={cell} /></th>)}</tr></thead>
        <tbody>{node.rows?.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}><Markdown text={cell} /></td>)}</tr>)}</tbody>
      </table>
    </div>;
    return <div key={index} className="guide-build-paths">{children}</div>;
  })}</>;
}
