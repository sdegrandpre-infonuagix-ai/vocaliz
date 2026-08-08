/**
 * Every key this app stores on the device, and the one-time move off the old namespace.
 *
 * The keys were prefixed `salon_`, after the project this code came from. That word now
 * names the conversation itself, so the prefix had stopped describing anything — and
 * `vocaliz.captionLang` had already been written under the new convention, leaving the
 * device holding two namespaces at once.
 *
 * Collected in one file because a storage key is a contract with the installed base: it
 * is the one kind of string that cannot be changed by changing it. Scattered across
 * contexts, the next rename would silently orphan whatever it missed.
 *
 * SecureStore keys accept only letters, digits, dot, dash and underscore.
 */
import * as SecureStore from 'expo-secure-store';

export const JWT = 'vocaliz.jwt';
export const USER_ID = 'vocaliz.userId';
export const LANGUAGE = 'vocaliz.language';
export const CAPTION_LANG = 'vocaliz.captionLang';

/**
 * Old key → new key, for values worth carrying across.
 *
 * The credentials are deliberately absent. They are written and deleted but never read
 * back — the app re-authenticates on every launch — so migrating them would move a value
 * nothing consumes. They are dropped below instead.
 */
const CARRY_OVER: ReadonlyArray<readonly [string, string]> = [
  ['salon_language', LANGUAGE],
];

/** Written by a previous version, read by nothing. Removed so the keychain does not keep
 *  a stale token for the life of the install. */
const ABANDONED = ['salon_jwt', 'salon_user_id'];

/**
 * Move what is worth moving, drop what is not. Runs once per launch, costs a handful of
 * keychain reads, and does nothing at all after the first time.
 *
 * Every step is best-effort and independent: SecureStore can fail on a locked device, and
 * a language preference is not worth failing a launch over. An interrupted run resumes on
 * the next one, because a value is only deleted after its new key is written.
 */
export async function migrateLegacyKeys(): Promise<void> {
  for (const [legacy, current] of CARRY_OVER) {
    try {
      const existing = await SecureStore.getItemAsync(current);
      if (existing !== null) {
        // Already migrated, or written fresh under the new key. Either way the old one
        // is stale and must not be allowed to overwrite it.
        await SecureStore.deleteItemAsync(legacy).catch(() => {});
        continue;
      }
      const stored = await SecureStore.getItemAsync(legacy);
      if (stored === null) continue;
      await SecureStore.setItemAsync(current, stored);
      await SecureStore.deleteItemAsync(legacy);
    } catch {
      // Left in place; the next launch tries again.
    }
  }

  for (const legacy of ABANDONED) {
    try {
      await SecureStore.deleteItemAsync(legacy);
    } catch {
      // Nothing reads it, so failing to remove it is harmless.
    }
  }
}
