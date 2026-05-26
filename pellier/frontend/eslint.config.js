import { FlatCompat } from '@eslint/eslintrc'
import js from '@eslint/js'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const compat = new FlatCompat({
  baseDirectory: __dirname,
  recommendedConfig: js.configs.recommended,
  allConfig: js.configs.all,
})

export default [
  ...compat.config({
    root: true,
    env: { browser: true, es2020: true },
    extends: [
      'eslint:recommended',
      'plugin:@typescript-eslint/recommended',
      'plugin:react-hooks/recommended',
    ],
    ignorePatterns: [
      'dist',
      '.eslintrc.cjs',
      'src/stories',
      '.storybook',
      'src/__tests__/*.mjs',
    ],
    parser: '@typescript-eslint/parser',
    plugins: ['react-refresh'],
    rules: {
      'react-refresh/only-export-components': 'off',
      'react-hooks/exhaustive-deps': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',
      'no-useless-escape': 'off',
      'prefer-const': 'off',
    },
  }),
]
