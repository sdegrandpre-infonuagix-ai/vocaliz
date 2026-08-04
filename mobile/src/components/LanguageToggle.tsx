/**
 * EN | FR switch.
 *
 * The choice it records is explicit and persisted, and outranks the language the agent
 * detects from the host's speech — see LanguageContext. Labels stay in their own language
 * ("EN", "FR") rather than being translated, so each is recognisable to the person
 * looking for it whichever language is currently showing.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing, MIN_TOUCH } from '../theme/tokens';
import { useLanguage } from '../contexts/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { saveLanguagePreferences } from '../services/userApi';
import type { SupportedLanguage } from '../i18n/translations';

const OPTIONS: { code: SupportedLanguage; label: string; a11y: string }[] = [
  { code: 'en', label: 'EN', a11y: 'English' },
  { code: 'fr', label: 'FR', a11y: 'Français' },
];

export default function LanguageToggle() {
  const { language, setLanguage } = useLanguage();
  const { token } = useAuth();

  // The choice is recorded on the account as well as on this device, so it follows the person
  // to their phone or their laptop. Saved here rather than inside LanguageContext because the
  // provider sits outside AuthProvider and has no token to send.
  //
  // Fire-and-forget: the language has already changed locally, and failing to remember a
  // preference must not interrupt anything. Before sign-in there is no account, and the device
  // copy carries the choice until there is one.
  function choose(code: SupportedLanguage) {
    setLanguage(code);
    if (!token) return;
    saveLanguagePreferences(token, { interfaceLanguage: code }).catch(() => {
      // Kept on the device regardless.
    });
  }

  return (
    <View style={styles.row}>
      {OPTIONS.map(({ code, label, a11y }) => {
        const active = language === code;
        return (
          <Pressable
            key={code}
            onPress={() => choose(code)}
            style={[styles.button, active && styles.buttonActive]}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            accessibilityLabel={a11y}
          >
            <Text style={[styles.label, active && styles.labelActive]}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignSelf: 'flex-end',
    gap: spacing.xs,
  },
  button: {
    minWidth: MIN_TOUCH,
    minHeight: MIN_TOUCH,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
  },
  buttonActive: {
    backgroundColor: colors.burgundy,
    borderColor: colors.burgundy,
  },
  label: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1,
    color: colors.muted,
  },
  labelActive: {
    color: colors.ivory,
  },
});
