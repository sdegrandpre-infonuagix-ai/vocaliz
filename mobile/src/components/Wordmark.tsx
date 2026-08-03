/**
 * The Vocaliz wordmark, as the website sets it.
 *
 * The app and the site had drifted into looking like two products: the site opens on a
 * burgundy bar carrying VOCALIZ in letter-spaced capitals with a gold role badge beside it,
 * while the app opened on an ivory field with "Salon" set in Playfair. Same palette, no
 * shared silhouette — and, since the rename, not even the same name.
 *
 * Deliberately not the Playfair title face used elsewhere in the app. The site sets its
 * wordmark in the system sans at weight 700 with 0.06em of tracking, and a wordmark is the
 * one element that has to be the same object in both places rather than a local
 * interpretation of it.
 *
 * Values mirror the header rules in api/web/host.html — 1.4rem at 16px root is 22px, and the
 * badge's 0.65rem is 10px. Changing one side without the other is what produced the drift
 * this component exists to close.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../theme/tokens';

type Props = {
  /** Short role label shown in the gold badge, as "Host console" is on the site. */
  badge?: string;
};

export default function Wordmark({ badge }: Props) {
  return (
    <View style={styles.bar}>
      {/* The name is not translated: a wordmark is the same in every language, and the site
          keeps it out of its dictionaries for that reason. */}
      <Text style={styles.mark} accessibilityRole="header">
        VOCALIZ
      </Text>
      {badge ? <Text style={styles.badge}>{badge.toUpperCase()}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: colors.burgundy,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  mark: {
    color: colors.ivory,
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: 1.3,
  },
  badge: {
    backgroundColor: colors.gold,
    color: colors.charcoal,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 4,
    overflow: 'hidden',
  },
});
