/**
 * PellierCollections - the mood rail under the hero.
 *
 * Four photographs as an editorial entry point into the catalog. Every tile
 * opens the same floor: these are moods, not routes, and inventing four
 * category pages the router does not serve would be a dead end for a shopper
 * and a false claim in a workshop about grounded answers.
 */
import { COLLECTIONS } from '../copy'
import ResponsiveImage from './ResponsiveImage'

interface PellierCollectionsProps {
  onOpenCatalog: () => void
}

export default function PellierCollections({
  onOpenCatalog,
}: PellierCollectionsProps) {
  return (
    <section
      data-testid="pellier-collections"
      aria-labelledby="pellier-collections-title"
      className="pellier-moods"
    >
      <div className="pellier-moods-inner">
        <header className="pellier-moods-anchor">
          <div className="flex flex-col gap-3">
            <span className="pellier-eyebrow">{COLLECTIONS.EYEBROW}</span>
            <h2
              id="pellier-collections-title"
              className="pellier-statement"
            >
              {COLLECTIONS.TITLE}
            </h2>
          </div>
          <button
            type="button"
            className="pellier-action-quiet"
            onClick={onOpenCatalog}
          >
            {COLLECTIONS.VIEW_ALL}
          </button>
        </header>

        <div className="pellier-moods-grid">
          {COLLECTIONS.ITEMS.map((collection) => (
            /* An <article> rather than a <button>: a heading is flow content
               and is invalid inside a button. The stretched hit area below
               keeps the whole tile clickable. */
            <article
              key={collection.title}
              className="pellier-mood"
              data-tone={collection.tone}
            >
              <ResponsiveImage
                src={collection.image}
                alt={collection.alt}
                widths={[480, 960]}
                sizes="(min-width: 1160px) 24vw, (min-width: 640px) 46vw, 90vw"
                loading="lazy"
                decoding="async"
                pictureClassName="block h-full w-full"
              />
              <div className="pellier-mood-copy">
                <h3>{collection.title}</h3>
                <p>{collection.description}</p>
              </div>
              <button
                type="button"
                className="pellier-mood-hit"
                aria-label={`${collection.title}. ${collection.description} Browse the collection.`}
                onClick={onOpenCatalog}
              />
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
