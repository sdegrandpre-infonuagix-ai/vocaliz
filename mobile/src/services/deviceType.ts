/**
 * What kind of device this is, as one of the categories the API accepts.
 *
 * Deliberately no new dependency. expo-device would answer this directly, but adding a native
 * module changes the fingerprint the update channel is keyed on — every installed copy would
 * stop receiving updates until it was rebuilt and reinstalled. Platform and Dimensions are
 * already here and answer well enough.
 *
 * A category, never a device model or a user agent. The model plus the OS build identifies
 * somebody across sessions; the shape of their screen does not.
 */
import { Dimensions, Platform } from 'react-native';

/**
 * Android's own breakpoint for a tablet layout: 600 density-independent pixels on the shorter
 * edge. Measured on the shorter edge rather than the height so that a phone held sideways is
 * still a phone.
 */
const TABLET_MIN_DP = 600;

export function deviceType(): string {
  if (Platform.OS === 'ios') {
    // Set by React Native from the UIDevice idiom, so this is the system's own answer rather
    // than a guess from a string — which is exactly what the web has to resort to, where
    // iPadOS Safari claims to be a Macintosh.
    return Platform.isPad ? 'ipad' : 'iphone';
  }

  if (Platform.OS === 'android') {
    const { width, height } = Dimensions.get('screen');
    const shorter = Math.min(width, height);
    return shorter >= TABLET_MIN_DP ? 'android-tablet' : 'android-phone';
  }

  // Anything else — web, or a platform added later. Better empty than wrong: the server treats
  // an unknown value as absent anyway, and a category invented here would be a count nobody
  // could trust.
  return '';
}
