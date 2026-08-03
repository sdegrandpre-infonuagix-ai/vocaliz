/**
 * The live caption panel: what is being said, in the language the reader picked.
 *
 * The language is chosen from a row of chips rather than a picker. React Native has no
 * cross-platform select — the iOS wheel and the Android dropdown behave and look nothing
 * alike — and a horizontal strip of chips is one component, readable at a glance, and
 * usable with a thumb while holding a conversation.
 */
import React, { useEffect, useRef } from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';

import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useLanguage } from '../contexts/LanguageContext';
import { CAPTION_LANGUAGES, captionText, type Caption } from '../hooks/useCaptions';

interface Props {
  captions: Caption[];
  language: string;
  onLanguageChange: (code: string) => void;
}

export default function CaptionsPanel({ captions, language, onLanguageChange }: Props) {
  const { t } = useLanguage();
  const logRef = useRef<ScrollView | null>(null);

  // Follow the conversation. Someone who has scrolled back to reread a line will be
  // pulled forward again by the next turn, which is the lesser annoyance: a caption
  // panel that silently stops updating looks broken.
  useEffect(() => {
    logRef.current?.scrollToEnd({ animated: true });
  }, [captions.length]);

  return (
    <View style={styles.panel}>
      <Text style={styles.sectionTitle}>{t.room.captionsTitle}</Text>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipRow}
        accessibilityLabel={t.room.captionsLanguageLabel}
      >
        {CAPTION_LANGUAGES.map((option) => {
          const selected = option.code === language;
          return (
            <Pressable
              key={option.code || 'as-spoken'}
              style={[styles.chip, selected && styles.chipSelected]}
              onPress={() => onLanguageChange(option.code)}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={option.label || t.room.captionsAsSpoken}
            >
              <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
                {/* The "as spoken" option is interface text, so it follows the interface
                    language; every other label is written in its own language. */}
                {option.label || t.room.captionsAsSpoken}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView
        ref={logRef}
        style={styles.log}
        nestedScrollEnabled
        accessibilityLiveRegion="polite"
      >
        {captions.length === 0 ? (
          <Text style={styles.empty}>{t.room.captionsEmpty}</Text>
        ) : (
          captions.map((caption) => {
            const shown = captionText(caption, language);
            return (
              <View key={caption.sequence} style={styles.line}>
                <Text style={styles.who}>{caption.speaker}</Text>
                <Text style={styles.text}>{shown}</Text>
                {/* The spoken words, under the translation. A translation with no
                    original is a claim the reader cannot check. */}
                {shown !== caption.text ? (
                  <Text style={styles.source}>{caption.text}</Text>
                ) : null}
              </View>
            );
          })
        )}
      </ScrollView>

      <Text style={styles.notice}>{t.room.captionsNotice}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { marginTop: spacing.lg },
  sectionTitle: {
    fontSize: typography.subtitleSize,
    color: colors.burgundy,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  chipRow: { gap: spacing.sm, paddingVertical: spacing.xs, paddingRight: spacing.md },
  chip: {
    minHeight: MIN_TOUCH,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.white,
  },
  chipSelected: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { fontSize: typography.captionSize, color: colors.muted },
  chipTextSelected: { color: colors.charcoal, fontWeight: '700' },
  // Bounded and scrolling: a ten-minute salon is a few hundred turns, and a panel that
  // grows without limit pushes every other control off the screen.
  log: {
    maxHeight: 260,
    marginTop: spacing.sm,
    backgroundColor: colors.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  line: { borderLeftWidth: 2, borderLeftColor: colors.gold, paddingLeft: spacing.sm, marginBottom: spacing.md },
  who: { fontSize: 11, letterSpacing: 0.5, textTransform: 'uppercase', color: colors.muted },
  text: { fontSize: typography.bodySize, color: colors.charcoal, lineHeight: 22 },
  source: { fontSize: typography.captionSize, color: colors.muted, fontStyle: 'italic', marginTop: 2 },
  empty: { fontSize: typography.captionSize, color: colors.muted },
  notice: {
    fontSize: typography.captionSize,
    color: colors.muted,
    lineHeight: 19,
    marginTop: spacing.sm,
  },
});
