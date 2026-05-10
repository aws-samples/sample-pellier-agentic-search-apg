/**
 * Storybook config — scaffolding for visual regression via Chromatic.
 *
 * Owned by task 7.2 in `.kiro/specs/pellier-storefront/tasks.md`.
 * Setup instructions live in `tests/visual-regression/README.md`.
 *
 * This file imports `@storybook/react-vite`, which is NOT in
 * `package.json` yet. Install it when turning Chromatic on:
 *
 *   npm install --save-dev @storybook/react-vite @storybook/addon-viewport \
 *                           @storybook/addon-essentials storybook
 */
import type { StorybookConfig } from '@storybook/react-vite'

const config: StorybookConfig = {
  // Stories live alongside the components they snapshot, under
  // `src/stories/`. Any new story file picked up by this glob is
  // automatically included in the Chromatic run.
  stories: ['../src/stories/**/*.stories.@(ts|tsx)'],

  addons: [
    '@storybook/addon-essentials',
    // Viewport addon powers the mobile / tablet / desktop breakpoints
    // required by Req 5.2.1–5.2.3. Chromatic reads the same
    // `parameters.chromatic.viewports` list per story.
    '@storybook/addon-viewport',
  ],

  framework: {
    name: '@storybook/react-vite',
    options: {},
  },

  docs: {
    autodocs: false,
  },

  // Match Vite's TypeScript handling from the main app.
  typescript: {
    check: false,
    reactDocgen: 'react-docgen-typescript',
  },

  staticDirs: ['../public'],
}

export default config
