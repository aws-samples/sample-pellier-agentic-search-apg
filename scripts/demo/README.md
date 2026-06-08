# Demo capture scripts

## `capture-chatui-gif.mjs`

Captures a 12–15 second screen recording of the Pellier Boutique
(signed in as Marco, hero-pill chat turn) and encodes it as
`docs/demo-assets/chatui.gif`. To publish it in the lab manual, copy the
file into the Workshop Studio repo's `static/imgs/`.

### Why a script (not a manual recording)

The lab guide references the GIF from Workshop Studio:

```
:image[Chat UI Demo]{src="/static/imgs/chatui.gif"}
```

Re-running the script regenerates the file deterministically whenever
the storefront copy, persona art, or hero pills change.

### One-time install

```bash
npm i -D playwright          # bundled Chromium
brew install ffmpeg          # encode step
```

If Playwright's bundled Chromium is missing, the script automatically
falls back to system Chrome at
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

### Run

```bash
# 1. start the dev servers (two terminals)
npm --prefix pellier/frontend run dev
cd pellier/backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 2. capture
node scripts/demo/capture-chatui-gif.mjs
```

The script:

1. Opens `http://localhost:5173`, viewport 1440×900 @ 2× scale.
2. Starts a 12 fps screenshot loop in the background.
3. Selects Marco via the `persona-pill` dropdown.
4. Smooth-scrolls down, then back up.
5. Clicks Marco's first hero pill ("What linen do you have for 10
   days in Goa?").
6. Waits for `chat-drawer` to mount and the answer to stream.
7. Stops capture and runs a two-pass `ffmpeg` encode (palette → GIF)
   at 1280 px wide.
8. Prints width, height, duration, frame count, and file size.

### Tunable knobs

Top of `main()`:

- `FPS` — capture and encode rate. 12 is the sweet spot for size; 10
  is smaller, 15 is smoother.
- `VIEWPORT` — change to `{ width: 1280, height: 800 }` for a smaller
  GIF.
- The `scale=1280:-1` filter in `encodeGif()` controls output width.

Target output is **under 10 MB**, ~14 s long, 1280 px wide.
