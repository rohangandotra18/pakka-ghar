// Keep Metro out of the Python backend (its virtualenv and database files are large and not JavaScript).
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.resolver.blockList = [/\/backend\/.*/, /\/contracts\/.*/];
module.exports = config;
