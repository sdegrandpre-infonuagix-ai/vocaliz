/**
 * The countdown to the agent opening the conversation.
 *
 * Shown only while one is running. A host who has just invited someone is otherwise sitting
 * in silence with nothing to tell them whether anything is happening — which is the exact
 * complaint this whole mechanism exists to answer.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing, typography } from '../theme/tokens';
import { useLanguage } from '../contexts/LanguageContext';

interface Props {
  /** null when nothing is running. Zero is a real state: the agent is starting. */
  secondsLeft: number | null;
}

export default function OpeningCountdown({ secondsLeft }: Props) {
  const { t } = useLanguage();
  if (secondsLeft === null) return null;

  return (
    <View style={styles.box} accessibilityRole="progressbar" accessibilityLiveRegion="polite">
      <Text style={styles.number}>{Math.max(secondsLeft, 0)}</Text>
      <Text style={styles.label}>
        {secondsLeft > 0 ? t.room.countdownWaiting : t.room.countdownNow}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.gold,
    backgroundColor: colors.ivory,
    alignItems: 'center',
  },
  number: { fontSize: 34, fontWeight: '700', color: colors.burgundy, lineHeight: 38 },
  label: {
    fontSize: typography.captionSize,
    color: colors.muted,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
});
