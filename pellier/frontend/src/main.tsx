import React from 'react'
import ReactDOM from 'react-dom/client'

// Self-hosted typefaces (@fontsource). Bundled into dist/assets at
// build time so the workshop runs on corporate networks that block
// fonts.gstatic.com. Five families cover both storefront
// (Fraunces italic, Inter) and Atelier (Instrument Sans/Serif,
// JetBrains Mono for SQL + telemetry tags). Ordered so the most
// visible weights load first.
import '@fontsource-variable/inter'
import '@fontsource-variable/fraunces'
import '@fontsource-variable/fraunces/full-italic.css'
import '@fontsource/instrument-sans/400.css'
import '@fontsource/instrument-sans/500.css'
import '@fontsource/instrument-sans/600.css'
import '@fontsource/instrument-serif/400.css'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource-variable/jetbrains-mono'

import App from './App.tsx'
import './index.css'

// ``?reset=1`` — nuke every piece of persisted client state and reload
// clean. The workshop runs in sequence for hundreds of attendees and a
// stale session-id / cart / preferences / chat transcript from the
// previous lab poisons demos. Any attendee (or presenter) can append
// ``?reset=1`` to the URL and land on a pristine storefront.
//
// Runs BEFORE React mounts so providers initialise from the cleared
// stores, not from pre-reset values.
(() => {
  const params = new URLSearchParams(window.location.search)
  if (params.get('reset') !== '1') return
  try {
    localStorage.clear()
    sessionStorage.clear()
    // Cookies scoped to this host only — defensive. We don't touch
    // HttpOnly cookies (the browser won't let us) but those aren't
    // used for client-side state today.
    document.cookie.split(';').forEach((c) => {
      const name = c.split('=')[0].trim()
      if (!name) return
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
    })
  } catch {
    // Private mode / storage disabled → nothing to clear; let the
    // app continue with whatever state the browser does have.
  }
  // Strip the reset flag and reload so the fresh state takes effect.
  params.delete('reset')
  const clean = window.location.pathname + (params.toString() ? `?${params}` : '')
  window.location.replace(clean)
})()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)