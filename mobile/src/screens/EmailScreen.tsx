/**
 * Email entry screen — first step of OTP registration flow (UX-DR10).
 * Palette: Salon Parisien (UX-DR1). Telegraph icon as the brand mark (UX-DR6).
 * WCAG AA: contrast ≥ 4.5:1, touch targets ≥ 44×44px (UX-DR7).
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import TelegraphIcon from '../components/TelegraphIcon';
import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import type { AuthStackParamList } from '../navigation/AuthNavigator';

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Email'>;
};


export default function EmailScreen({ navigation }: Props) {
  const [email, setEmail] = useState('');
  const { sendOtp, isLoading, error } = useAuth();
  const { t } = useLanguage();

  // Deliberately loose: the API validates properly, this only gates the button.
  const normalized = email.trim().toLowerCase();
  const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(normalized);

  async function handleSend() {
    if (!isValid) return;
    await sendOtp(normalized);
    // Navigate on success (error state handled by AuthContext)
    if (!error) {
      navigation.navigate('Otp', { email: normalized });
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        {/* ── Telegraph icon ── */}
        <View style={styles.iconContainer} accessibilityElementsHidden>
          <TelegraphIcon size={160} />
        </View>

        {/* ── Title ── */}
        <Text style={styles.title} accessibilityRole="header">
          Salon
        </Text>
        <Text style={styles.subtitle}>
          {t.email.subtitle}
        </Text>

        {/* ── Email input ── */}
        <TextInput
          style={[styles.input, error ? styles.inputError : null]}
          value={email}
          onChangeText={setEmail}
          placeholder="vous@exemple.com"
          placeholderTextColor={colors.muted}
          keyboardType="email-address"
          textContentType="emailAddress"
          autoComplete="email"
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={t.email.inputLabel}
          accessibilityHint={t.email.inputHint}
          autoFocus
          maxLength={254}
        />

        {/* ── Error message ── */}
        {error ? (
          <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}

        {/* ── CTA button ── */}
        <Pressable
          style={({ pressed }) => [
            styles.button,
            !isValid && styles.buttonDisabled,
            pressed && isValid && styles.buttonPressed,
          ]}
          onPress={handleSend}
          disabled={!isValid || isLoading}
          accessibilityRole="button"
          accessibilityLabel={t.email.button}
          accessibilityState={{ disabled: !isValid || isLoading, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.ivory} />
          ) : (
            <Text style={styles.buttonText}>{t.email.button}</Text>
          )}
        </Pressable>

        <Text style={styles.legal}>
          {t.email.legal}
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
  container: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xxl,
    backgroundColor: colors.ivory,
  },
  iconContainer: {
    marginBottom: spacing.xl,
  },
  title: {
    fontFamily: typography.titleFamily,
    fontSize: typography.titleSize,
    color: colors.burgundy,
    letterSpacing: 6,
    marginBottom: spacing.sm,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: typography.bodySize,
    color: colors.charcoal,
    textAlign: 'center',
    marginBottom: spacing.xl,
    lineHeight: typography.bodySize * 1.5,
  },
  input: {
    width: '100%',
    minHeight: MIN_TOUCH,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: typography.bodySize,
    color: colors.charcoal,
    backgroundColor: colors.white,
    marginBottom: spacing.md,
  },
  inputError: {
    borderColor: colors.error,
  },
  errorText: {
    fontSize: typography.captionSize,
    color: colors.error,
    marginBottom: spacing.md,
    textAlign: 'center',
  },
  button: {
    width: '100%',
    minHeight: MIN_TOUCH,
    backgroundColor: colors.burgundy,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    marginBottom: spacing.lg,
  },
  buttonDisabled: {
    backgroundColor: colors.muted,
    opacity: 0.6,
  },
  buttonPressed: {
    backgroundColor: colors.burgundyDark,
  },
  buttonText: {
    fontSize: typography.bodySize,
    fontWeight: '600',
    color: colors.ivory,
    letterSpacing: 0.5,
  },
  legal: {
    fontSize: typography.captionSize,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: typography.captionSize * 1.5,
  },
});
