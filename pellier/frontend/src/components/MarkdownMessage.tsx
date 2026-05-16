/**
 * Markdown Message Renderer - Formats agent responses with markdown
 */

interface Props {
  content: string
}

const MarkdownMessage = ({ content }: Props) => {

  const formatText = (text: string) => {
    // Replace stars with gold colored stars
    const parts = text.split(/(\d+\.\d+★)/)
    return parts.map((part, i) => {
      if (part.match(/\d+\.\d+★/)) {
        return <span key={i} className="text-yellow-500 font-semibold">{part}</span>
      }
      // Handle inline bold
      const boldParts = part.split(/(\*\*.*?\*\*)/)
      return boldParts.map((bp, j) => {
        if (bp.startsWith('**') && bp.endsWith('**')) {
          return <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>
        }
        return <span key={`${i}-${j}`}>{bp}</span>
      })
    })
  }

  const renderContent = (raw: string) => {
    // Pre-clean: strip artifacts the backend should have removed
    let text = raw
      // Remove markdown table rows (| col | col |)
      .replace(/^\|.*$/gm, '')
      // Remove horizontal rules (---, ***, ___)
      .replace(/^[-*_]{3,}\s*$/gm, '')
      // Remove "Products:" / "Suggestions:" labels
      .replace(/^(?:Products?|Suggestions?):?\s*$/gim, '')
      // Collapse blank lines
      .replace(/\n{3,}/g, '\n\n')
      .trim()

    // Split on code fences, preserving the blocks
    const segments = text.split(/(```(?:\w+)?\s*\n?[\s\S]*?```)/g)
    const elements: JSX.Element[] = []
    let segKey = 0

    segments.forEach((segment) => {
      const fenceMatch = segment.match(/^```(?:\w+)?\s*\n?([\s\S]*?)```$/)
      if (fenceMatch) {
        const code = fenceMatch[1].trim()
        // If it's valid JSON, skip it (products are rendered separately via ProductCardCompact)
        try {
          JSON.parse(code)
          return // pure JSON block — products rendered as cards, not text
        } catch {
          // Not JSON — render as a styled code block
          elements.push(
            <pre key={`code-${segKey++}`} className="dl-code-block" style={{ margin: '12px 0' }}>
              {code}
            </pre>
          )
        }
      } else {
        // Regular text — parse lines
        const lines = segment.split('\n')
        let currentList: string[] = []
        let listKey = 0

        const flushList = () => {
          if (currentList.length > 0) {
            elements.push(
              <ul key={`list-${segKey}-${listKey++}`} className="list-disc list-inside space-y-1 my-2 ml-4">
                {currentList.map((item, idx) => (
                  <li key={idx} className="text-text-primary">{formatText(item)}</li>
                ))}
              </ul>
            )
            currentList = []
          }
        }

        lines.forEach((line, idx) => {
          // Bold text with emoji
          if (line.match(/^\*\*.*\*\*/)) {
            flushList()
            const text = line.replace(/\*\*/g, '')
            elements.push(
              <p key={`${segKey}-${idx}`} className="font-semibold text-text-primary my-2">
                {formatText(text)}
              </p>
            )
          }
          // List items (- or •)
          else if (line.match(/^[-•]\s/)) {
            const text = line.replace(/^[-•]\s*/, '').replace(/\*\*/g, '')
            currentList.push(text)
          }
          // Regular paragraphs (skip empty/whitespace-only)
          else if (line.trim()) {
            flushList()
            elements.push(
              <p key={`${segKey}-${idx}`} className="text-text-primary my-2">
                {formatText(line)}
              </p>
            )
          }
          // Empty lines
          else {
            flushList()
          }
        })

        flushList()
        segKey++
      }
    })
    return elements
  }

  return (
    <div className="space-y-1">
      {renderContent(content)}
    </div>
  )
}

export default MarkdownMessage
