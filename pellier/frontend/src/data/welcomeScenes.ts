/** Existing editorial photography. Catalog and account facts remain live reads. */
const scenes: Record<string, { image: string; alt: string; label: string }> = {
  fresh: {
    image: '/products/landing-hero-weekender.webp',
    alt: 'Leather weekender beside folded linen and an olive branch in warm daylight',
    label: 'The weekend edit',
  },
  marco: {
    image: '/products/hero-marco.png',
    alt: 'Leather weekender with folded linen and brass travel details in warm daylight',
    label: 'The weekend edit',
  },
  anna: {
    image: '/products/hero-anna.png',
    alt: 'Ribbon-wrapped gift beside an amber candle and a ceramic bud vase',
    label: 'The gifting edit',
  },
  theo: {
    image: '/products/hero-theo.png',
    alt: 'Charcoal stoneware beside natural linen, a beeswax candle, and olive branches',
    label: 'The everyday ritual',
  },
}

export function welcomeScene(personaId: string) {
  return scenes[personaId] ?? scenes.fresh
}
