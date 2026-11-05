const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([expoConfig, { ignores: ['dist/*', 'backend/*', 'src/api/schema.d.ts', 'src/components/mapEngine.generated.ts'] }]);
