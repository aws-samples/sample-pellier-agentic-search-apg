/**
 * The contrast sweep, run inside the page by `theme-surfaces.spec.ts`.
 *
 * For every element whose box is in the viewport it measures what a reader
 * sees against what is painted behind it, found with `elementsFromPoint` so
 * overlays, portals and stacked panels resolve to the surface actually under
 * the element:
 *
 * - text (an element's own text nodes): 4.5:1;
 * - icons, 3:1: an inline `<svg>` by its strongest painted shape, and an
 *   `<img>` of icon size by the 90th percentile of its opaque pixels, so a
 *   black mark served as a file on a black page fails;
 * - borders and rules, 1.25:1: every visible border side of every element,
 *   blended over the element's own background (which runs under the border),
 *   against the surface outside it, plus one- and two-pixel rules drawn as
 *   backgrounds.
 *
 * Text and marks over a photograph or video are skipped: their contrast
 * depends on the picture. Disabled controls are exempt, as in WCAG 1.4.3.
 * The function is serialized into the page, so it is self-contained.
 */
export interface ContrastFinding {
  kind: 'text' | 'icon' | 'border' | 'rule'
  ratio: number
  min: number
  fg: string
  bg: string
  text: string
  path: string
}

export function sweepContrast(): ContrastFinding[] {
  type RGBA = { r: number; g: number; b: number; a: number }
  const MIN = { text: 4.5, icon: 3, border: 1.25, rule: 1.25 }
  const MEDIA = new Set(['IMG', 'VIDEO', 'CANVAS', 'PICTURE', 'IFRAME'])

  const parse = (value: string): RGBA | null => {
    const rgb = value.match(/rgba?\(([^)]+)\)/)
    if (rgb) {
      const v = rgb[1].split(/[\s,/]+/).filter(Boolean).map(Number)
      return { r: v[0], g: v[1], b: v[2], a: v[3] ?? 1 }
    }
    const srgb = value.match(/color\(srgb\s+([^)]+)\)/)
    if (srgb) {
      const v = srgb[1].split(/[\s/]+/).filter(Boolean).map(Number)
      return { r: v[0] * 255, g: v[1] * 255, b: v[2] * 255, a: v[3] ?? 1 }
    }
    return null
  }
  const over = (top: RGBA, under: RGBA): RGBA => ({
    r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a),
    a: 1,
  })
  const luminance = ({ r, g, b }: RGBA) => {
    const f = (x: number) => {
      const v = x / 255
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  const ratio = (a: RGBA, b: RGBA) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }
  const hex = ({ r, g, b }: RGBA) =>
    '#' + [r, g, b].map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')

  const pageGround = (): RGBA => {
    const html = parse(getComputedStyle(document.documentElement).backgroundColor)
    if (html && html.a > 0) return { ...html, a: 1 }
    const body = parse(getComputedStyle(document.body).backgroundColor)
    return body && body.a > 0 ? { ...body, a: 1 } : { r: 255, g: 255, b: 255, a: 1 }
  }
  /* A gradient counts as the mean of its stops: close enough for the soft
     editorial washes, which run between two neighbouring tokens. */
  const gradientMean = (image: string): RGBA | null => {
    const stops = Array.from(image.matchAll(/rgba?\([^)]+\)|color\(srgb[^)]+\)/g), (m) => parse(m[0]))
      .filter((c): c is RGBA => c !== null)
    if (stops.length === 0) return null
    const sum = stops.reduce((acc, c) => ({ r: acc.r + c.r, g: acc.g + c.g, b: acc.b + c.b, a: acc.a + c.a }),
      { r: 0, g: 0, b: 0, a: 0 })
    return { r: sum.r / stops.length, g: sum.g / stops.length, b: sum.b / stops.length, a: sum.a / stops.length }
  }

  /** What is painted under (x, y), below every element `skip` rejects. */
  const backdrop = (x: number, y: number, skip: (el: Element) => boolean): { color: RGBA; owner: Element | null } | null => {
    const layers: RGBA[] = []
    let owner: Element | null = null
    for (const el of document.elementsFromPoint(x, y)) {
      if (skip(el) || !(el instanceof HTMLElement)) continue
      if (MEDIA.has(el.tagName)) return null
      const style = getComputedStyle(el)
      if (/url\(/.test(style.backgroundImage)) return null
      const layer = style.backgroundImage !== 'none' ? gradientMean(style.backgroundImage) : null
      const color = parse(style.backgroundColor)
      const opacity = Number(style.opacity)
      for (const c of [layer, color]) {
        if (c && c.a > 0) {
          layers.push({ ...c, a: c.a * opacity })
          owner = owner ?? el
        }
      }
      if (layers.length && layers[layers.length - 1].a >= 0.99) break
    }
    let ground = pageGround()
    for (const layer of layers.reverse()) ground = over(layer, ground)
    return { color: ground, owner }
  }

  const visible = (el: Element) => {
    const rect = el.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return false
    const style = getComputedStyle(el)
    return style.visibility === 'visible' && style.display !== 'none'
  }
  const inView = (x: number, y: number) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight
  /** The opacity between an element and the surface its color is read on. */
  const fade = (el: Element, until: Element | null) => {
    let opacity = 1
    for (let e: Element | null = el; e && e !== until; e = e.parentElement) {
      opacity *= Number(getComputedStyle(e).opacity)
    }
    return opacity
  }
  const disabled = (el: Element) => el.closest(':disabled, [aria-disabled="true"]') !== null
  /** Covered by something unrelated (a dialog, a scrim): not what a reader sees here. */
  const covered = (el: Element, x: number, y: number) => {
    const top = document.elementsFromPoint(x, y)[0]
    return !!top && top !== el && !el.contains(top) && !top.contains(el)
  }
  const path = (el: Element) => {
    const parts: string[] = []
    for (let e: Element | null = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      const id = e.getAttribute('data-testid')
      const cls = typeof e.className === 'string' ? e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''
      parts.unshift(e.tagName.toLowerCase() + (id ? `[${id}]` : cls ? `.${cls}` : ''))
    }
    return parts.join(' > ')
  }

  const findings: ContrastFinding[] = []
  const report = (kind: ContrastFinding['kind'], el: Element, fg: RGBA, bg: RGBA, label = '') => {
    const value = ratio(fg, bg)
    if (value >= MIN[kind]) return
    findings.push({
      kind, ratio: Math.round(value * 100) / 100, min: MIN[kind], fg: hex(fg), bg: hex(bg),
      text: label.trim().replace(/\s+/g, ' ').slice(0, 60), path: path(el),
    })
  }

  const SHAPES = 'path, circle, rect, line, polyline, polygon, ellipse, text, use'
  const imageInk = (img: HTMLImageElement, bg: RGBA): RGBA | null => {
    const w = Math.round(img.getBoundingClientRect().width)
    const h = Math.round(img.getBoundingClientRect().height)
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const context = canvas.getContext('2d')
    if (!context) return null
    try {
      context.drawImage(img, 0, 0, w, h)
      const data = context.getImageData(0, 0, w, h).data
      const inks: Array<{ c: RGBA; v: number }> = []
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 128) continue
        const c = over({ r: data[i], g: data[i + 1], b: data[i + 2], a: data[i + 3] / 255 }, bg)
        inks.push({ c, v: ratio(c, bg) })
      }
      if (inks.length < 4) return null
      inks.sort((a, b) => a.v - b.v)
      return inks[Math.floor(inks.length * 0.9)].c
    } catch {
      return null
    }
  }

  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    const svgRoot = el.closest('svg')
    if (!visible(el) || (svgRoot !== null && svgRoot !== el)) continue
    const rect = el.getBoundingClientRect()
    const style = getComputedStyle(el)
    // Screen-reader-only text and one-pixel boxes are not read by eye.
    const boxed = rect.width > 1 && rect.height > 1

    // Text: the element's own text nodes.
    const ownText = Array.from(el.childNodes).filter((n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim())
    if (boxed && ownText.length && !disabled(el) && !['INPUT', 'TEXTAREA', 'SELECT', 'OPTION'].includes(el.tagName)) {
      const range = document.createRange()
      range.selectNodeContents(ownText[0])
      const box = range.getBoundingClientRect()
      const x = box.left + box.width / 2
      const y = box.top + box.height / 2
      const fill = style.getPropertyValue('-webkit-text-fill-color')
      const color = parse(fill && !/currentcolor/i.test(fill) ? fill : style.color)
      if (box.width > 1 && inView(x, y) && color && color.a > 0 && !covered(el, x, y)) {
        const under = backdrop(x, y, (e) => e !== el && el.contains(e))
        if (under) {
          const opacity = fade(el, under.owner)
          if (opacity > 0.05) report('text', el, over({ ...color, a: color.a * opacity }, under.color), under.color, ownText[0].textContent ?? '')
        }
      }
    }

    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2

    // Icons drawn inline: the strongest painted shape against the ground.
    if (boxed && el.tagName.toLowerCase() === 'svg' && !disabled(el) && inView(cx, cy) && !covered(el, cx, cy)) {
      const under = backdrop(cx, cy, (e) => el.contains(e))
      if (under) {
        const opacity = fade(el, under.owner)
        let best: RGBA | null = null
        const shapes = el.querySelectorAll(SHAPES)
        for (const shape of Array.from(shapes.length ? shapes : [el])) {
          const s = getComputedStyle(shape)
          for (const [paint, alpha] of [[s.stroke, s.strokeOpacity], [s.fill, s.fillOpacity]] as const) {
            const c = paint && paint !== 'none' ? parse(paint) : null
            if (!c || c.a === 0) continue
            const ink = over({ ...c, a: c.a * Number(alpha) * opacity }, under.color)
            if (!best || ratio(ink, under.color) > ratio(best, under.color)) best = ink
          }
        }
        if (best && opacity > 0.05) report('icon', el, best, under.color, el.getAttribute('aria-label') ?? '')
      }
    }

    // Icons served as images: the mark's own pixels, which a theme cannot change.
    if (boxed && el instanceof HTMLImageElement && rect.width <= 64 && rect.height <= 64 && el.complete && el.naturalWidth > 0
      && inView(cx, cy) && !covered(el, cx, cy)) {
      const under = backdrop(cx, cy, (e) => e === el)
      const ink = under ? imageInk(el, under.color) : null
      if (under && ink) report('icon', el, ink, under.color, el.getAttribute('src') ?? '')
    }

    // Borders: blended over the element's own background, against the outside.
    const sides = [
      ['Top', cx, rect.top + 0.5], ['Bottom', cx, rect.bottom - 0.5],
      ['Left', rect.left + 0.5, cy], ['Right', rect.right - 0.5, cy],
    ] as const
    for (const [side, x, y] of sides) {
      const width = parseFloat(style.getPropertyValue(`border-${side.toLowerCase()}-width`))
      const lineStyle = style.getPropertyValue(`border-${side.toLowerCase()}-style`)
      const color = parse(style.getPropertyValue(`border-${side.toLowerCase()}-color`))
      if (!(width >= 0.5) || lineStyle === 'none' || lineStyle === 'hidden' || !color || color.a === 0) continue
      if (!inView(x, y) || covered(el, x, y)) continue
      const outside = backdrop(x, y, (e) => e === el || el.contains(e))
      if (!outside) continue
      const own = parse(style.backgroundColor)
      const beneath = own && own.a > 0 ? over(own, outside.color) : outside.color
      const opacity = fade(el, outside.owner)
      report('border', el, over({ ...color, a: color.a * opacity }, beneath), outside.color, `border-${side.toLowerCase()}`)
    }

    // Rules drawn as a background: one or two pixels thick, no content.
    if (!ownText.length && el.children.length === 0 && (rect.height <= 2 || rect.width <= 2)) {
      const color = parse(style.backgroundColor)
      if (color && color.a > 0 && inView(cx, cy) && !covered(el, cx, cy)) {
        const outside = backdrop(cx, cy, (e) => e === el)
        if (outside) report('rule', el, over({ ...color, a: color.a * fade(el, outside.owner) }, outside.color), outside.color)
      }
    }
  }
  return findings
}

export interface GroundReport {
  /** How many bands were measured, the page and the shared header included. */
  checked: number
  /**
   * How many of them the routed page itself supplied, inside `.pellier-stage`.
   * The page and the header are always counted, so this is the number that
   * shows the sweep reached the route: one that matches nothing proves nothing.
   */
  inStage: number
  findings: Array<{ ground: string; path: string }>
}

/**
 * The page ground under a route's main bands, run in the dark theme, where it
 * must be true black (#000000). A band is the page itself, the shared header,
 * the routed page's own root, and every visible, in-flow `main`, `section`,
 * `header` or `footer`, or direct child of `main`, that spans the routed
 * page's full width. The Operator desk has no full-width `main`, so its root
 * is the only band it supplies. Panels and cards are narrower than the page,
 * so they are not bands and may sit on the panel token (`--dl-paper`).
 *
 * A band's ground is its own background composited over its ancestors', not
 * what `elementsFromPoint` finds on top: a dialog or scrim over the page is
 * not the page's ground. So a section painted with the panel token reads as
 * #0f0f0f here even though, in light, panel and page are both white and the
 * misuse cannot be seen. A band over a photograph is skipped. INK_BANDS are
 * filled with the ink by design, black in light and ivory in dark.
 */
export function sweepGrounds(): GroundReport {
  type RGBA = { r: number; g: number; b: number; a: number }
  const INK_BANDS = '[data-testid="announcement-bar"]'
  const WANT = '#000000'

  const parse = (value: string): RGBA | null => {
    const rgb = value.match(/rgba?\(([^)]+)\)/)
    if (rgb) {
      const v = rgb[1].split(/[\s,/]+/).filter(Boolean).map(Number)
      return { r: v[0], g: v[1], b: v[2], a: v[3] ?? 1 }
    }
    const srgb = value.match(/color\(srgb\s+([^)]+)\)/)
    if (srgb) {
      const v = srgb[1].split(/[\s/]+/).filter(Boolean).map(Number)
      return { r: v[0] * 255, g: v[1] * 255, b: v[2] * 255, a: v[3] ?? 1 }
    }
    return null
  }
  const over = (top: RGBA, under: RGBA): RGBA => ({
    r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a),
    a: 1,
  })
  const hex = ({ r, g, b }: RGBA) =>
    '#' + [r, g, b].map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')
  const gradientMean = (image: string): RGBA | null => {
    const stops = Array.from(image.matchAll(/rgba?\([^)]+\)|color\(srgb[^)]+\)/g), (m) => parse(m[0]))
      .filter((c): c is RGBA => c !== null)
    if (stops.length === 0) return null
    const sum = stops.reduce((acc, c) => ({ r: acc.r + c.r, g: acc.g + c.g, b: acc.b + c.b, a: acc.a + c.a }),
      { r: 0, g: 0, b: 0, a: 0 })
    return { r: sum.r / stops.length, g: sum.g / stops.length, b: sum.b / stops.length, a: sum.a / stops.length }
  }
  const path = (el: Element) => {
    const parts: string[] = []
    for (let e: Element | null = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      const id = e.getAttribute('data-testid')
      const cls = typeof e.className === 'string' ? e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''
      parts.unshift(e.tagName.toLowerCase() + (id ? `[${id}]` : cls ? `.${cls}` : ''))
    }
    return parts.join(' > ')
  }

  /** The element's own background over every ancestor's, from the root down; null over a photo. */
  const groundOf = (el: Element): RGBA | null => {
    const chain: Element[] = []
    for (let e: Element | null = el; e; e = e.parentElement) chain.unshift(e)
    let ground: RGBA = { r: 255, g: 255, b: 255, a: 1 }
    for (const e of chain) {
      const style = getComputedStyle(e)
      if (/url\(/.test(style.backgroundImage)) return null
      const opacity = Number(style.opacity)
      const color = parse(style.backgroundColor)
      if (color && color.a > 0) ground = over({ ...color, a: color.a * opacity }, ground)
      const wash = style.backgroundImage !== 'none' ? gradientMean(style.backgroundImage) : null
      if (wash && wash.a > 0) ground = over({ ...wash, a: wash.a * opacity }, ground)
    }
    return ground
  }

  const routed = document.querySelector('.pellier-stage')
  const stage = routed ?? document.body
  const stageStyle = getComputedStyle(stage)
  const pageWidth = stage.getBoundingClientRect().width
    - parseFloat(stageStyle.paddingLeft) - parseFloat(stageStyle.paddingRight)
  const bands = new Set<Element>([document.body, ...Array.from(document.querySelectorAll('.pellier-surface-bar'))])
  const candidates = stage.querySelectorAll(':scope > *, main, main > *, section, header, footer')
  for (const el of Array.from(candidates)) {
    const rect = el.getBoundingClientRect()
    const style = getComputedStyle(el)
    if (rect.width < pageWidth - 2 || rect.height < 24) continue
    if (style.display === 'none' || style.visibility !== 'visible') continue
    if (el.closest('[role="dialog"], [aria-modal="true"]') || el.closest(INK_BANDS)) continue
    if (['fixed', 'absolute'].includes(style.position)) continue
    bands.add(el)
  }

  const findings: GroundReport['findings'] = []
  for (const el of bands) {
    const ground = groundOf(el)
    if (ground && hex(ground) !== WANT) findings.push({ ground: hex(ground), path: path(el) || el.tagName.toLowerCase() })
  }
  const inStage = routed ? Array.from(bands).filter((band) => routed.contains(band)).length : 0
  return { checked: bands.size, inStage, findings }
}
