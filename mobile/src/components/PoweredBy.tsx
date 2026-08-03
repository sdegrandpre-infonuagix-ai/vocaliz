/**
 * "Powered by Infonuagix.ai" — the attribution carried on every screen.
 *
 * Linking comes from react-native rather than expo-linking: opening an external URL needs
 * nothing Expo adds, and the smaller dependency is the one that keeps working across SDK
 * upgrades.
 */
import React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing, MIN_TOUCH } from '../theme/tokens';

const URL = 'https://infonuagix.ai';

export default function PoweredBy() {
  // Failure is swallowed on purpose. openURL rejects when no browser can handle the
  // link — rare, and not worth interrupting someone mid-conversation with an alert about
  // a footer.
  const open = () => {
    Linking.openURL(URL).catch(() => {});
  };

  return (
    <View style={styles.row}>
      <Text style={styles.text}>Powered by </Text>
      <Pressable
        onPress={open}
        // The touch target is padded to the minimum rather than sized to the text: the
        // link is small by design, and a small link is not an excuse for a small target.
        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        accessibilityRole="link"
        accessibilityLabel="Infonuagix.ai, ouvre le site web"
      >
        <Text style={styles.link}>Infonuagix.ai</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: MIN_TOUCH,
    paddingVertical: spacing.sm,
  },
  text: {
    fontSize: 12,
    color: colors.muted,
  },
  link: {
    fontSize: 12,
    color: colors.burgundy,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
});
