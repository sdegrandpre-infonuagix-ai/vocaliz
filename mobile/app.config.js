/**
 * Dynamic Expo config — layers environment-driven values on top of app.json.
 *
 * Expo CLI reads app.json first and passes the normalized result in as `config`,
 * so this file only needs to add what depends on the environment. .env / .env.local
 * are loaded before this is evaluated, which is what makes EXPO_PUBLIC_* readable here.
 *
 * The services read these through Constants.expoConfig.extra (see src/services/*.ts);
 * on a physical device `localhost` points at the phone itself, so EXPO_PUBLIC_API_URL
 * must be set to the dev machine's LAN address (or a tunnel URL).
 */
module.exports = ({ config }) => ({
  ...config,
  extra: {
    ...config.extra,
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000',
    livekitUrl: process.env.EXPO_PUBLIC_LIVEKIT_URL ?? '',
  },
});
