const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

/* The app is split so that one kind of change touches one place (see ARCHITECTURE.md, "Where code lives"):
   design/ is the look, core/ is the plumbing, shared/ holds widgets several features use, features/<name>/ is one
   feature, shell/ is the app frame, and app/ is only the URL map. These rules keep it that way: lint fails if a
   file reaches somewhere it shouldn't. */
const only = (message, group) => ({ 'no-restricted-imports': ['error', { patterns: [{ group, message }] }] });

module.exports = defineConfig([
  expoConfig,
  { ignores: ['dist/*', 'backend/*', 'src/core/api/schema.d.ts', 'src/shared/map/*.generated.ts'] },
  {
    files: ['src/design/**'],
    rules: only('design/ is only the look of the app; it must not know about the API, the session or any feature.',
      ['@/core', '@/core/**', '@/shared', '@/shared/**', '@/features', '@/features/**', '@/shell', '@/shell/**']),
  },
  {
    files: ['src/core/**'],
    rules: only('core/ is plumbing (API, session, device); it must not depend on the design, shared widgets or features.',
      ['@/design', '@/design/**', '@/shared', '@/shared/**', '@/features', '@/features/**', '@/shell', '@/shell/**']),
  },
  {
    files: ['src/shared/**'],
    rules: only('shared/ widgets are used by features, so they must not depend on one.',
      ['@/features', '@/features/**', '@/shell', '@/shell/**']),
  },
  {
    files: ['src/features/**'],
    rules: only('Use another feature only through its index (`@/features/<name>`), and the rest through `@/design`, `@/core/<part>` or `@/shared`. Never reach into another folder by path.',
      ['@/features/*/**', '@/shell', '@/shell/**', '../*', '@/design/*', '@/core/*/*', '@/shared/*']),
  },
  {
    files: ['src/shell/**'],
    rules: only('Use features only through their index.', ['@/features/*/**', '@/design/*', '@/core/*/*', '@/shared/*']),
  },
  {
    files: ['src/app/**'],
    rules: only('app/ is only the URL map: each route re-exports a screen from a feature (or a layout from the shell).',
      ['@/design', '@/design/**', '@/core', '@/core/**', '@/shared', '@/shared/**', '@/features/*/**', './*', '../*']),
  },
]);
