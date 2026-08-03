/**
 * What the server says the app may offer.
 *
 * Read at runtime rather than compiled in. The one flag here waits on an AWS review, not
 * on a decision of ours, and a value baked into the bundle would mean a store build to
 * turn it on days after the capability actually arrived.
 */
import Constants from 'expo-constants';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface PublicConfig {
  /** Whether inviting by text message is offered. */
  smsEnabled: boolean;
}

/**
 * Fetch the server's public configuration.
 *
 * Every failure resolves to everything off rather than throwing. That is the safe
 * direction: a host never sees a channel that cannot deliver, and a network hiccup at
 * launch must not take the invitation screen down with it.
 */
export async function getPublicConfig(): Promise<PublicConfig> {
  try {
    const res = await fetch(`${API_URL}/config`);
    if (!res.ok) return { smsEnabled: false };
    const body = await res.json();
    return { smsEnabled: body?.smsEnabled === true };
  } catch {
    return { smsEnabled: false };
  }
}
