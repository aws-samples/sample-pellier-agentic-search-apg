# `static/introduction/` — placeholder images

The five PNGs here are **placeholders**, generated programmatically.
Each carries a "PLACEHOLDER · pre-deploy capture pending" stamp in
the upper-right and a dashed border so no reviewer mistakes them
for real screenshots.

| File | Used by | What it stands in for |
| --- | --- | --- |
| `pellier-hero.png` | `content/index.en.md` | Boutique hero — full-bleed photograph + presence pill + "Search, re:Engineered." headline + search bar |
| `marco-pill-4-fixed.png` | `content/02-closing-marcos-gap/` | Boutique chat drawer after the participant wires Stock Keeper — turn 4 lands with `floor_check` trace chips |
| `atelier-memory.png` | `content/04-step-into-the-atelier/` | Atelier · Memory orbit — persona at centre, STM inner ring, LTM outer ring |
| `atelier-tools.png` | `content/04-step-into-the-atelier/` | Atelier · Tools registry — 8 tool cards, `floor_check` bordered burgundy because participants wired it |
| `atelier-agents.png` | `content/04-step-into-the-atelier/` | Atelier · Agents board — 5 specialists, Stock Keeper bordered burgundy |

## Replacing with real screenshots

Once a Workshop Studio deploy is up, capture each surface against a
live Pellier instance and overwrite the matching file in this
directory. Keep the same filename — every `content/**/*.md` page
references these by name. The lab guide will pick up the real
captures automatically.

Recommended capture sizes:

- `pellier-hero.png` — 1440 × 720 (storefront)
- `marco-pill-4-fixed.png` — 1280 × 720 (storefront with drawer)
- `atelier-*.png` — 1280 × 720 (Atelier full canvas including sidebar)

## Regenerating the placeholders

If a placeholder needs tweaking before the real captures land, run:

```sh
python3 scripts/gen_placeholders.py
```

The generator uses the Pellier daylight palette (cream / espresso /
terracotta / burgundy) defined in the file's header. Edit the colour
constants or per-image `make_*` functions to adjust.

The script depends only on Pillow and DejaVu fonts (DejaVu Serif
Italic stands in for Fraunces; DejaVu Sans + Sans Mono stand in
for Inter and JetBrains Mono).
