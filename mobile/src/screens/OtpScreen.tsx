/**
 * OTP code entry screen — second step of registration flow (UX-DR10).
 * Palette: Salon Parisien (UX-DR1). WCAG AA accessibility (UX-DR7).
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';

import Wordmark from '../components/Wordmark';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import PoweredBy from '../components/PoweredBy';
import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import type { AuthStackParamList } from '../navigation/AuthNavigator';

const OTP_LENGTH = 6;
const RESEND_COOLDOWN = 30; // seconds

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Otp'>;
  route: RouteProp<AuthStackParamList, 'Otp'>;
};

export default function OtpScreen({ navigation, route }: Props) {
  const { email, name } = route.params;
  const [code, setCode] = useState('');
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN);
  const { confirmOtp, resendOtpCode, isLoading, error } = useAuth();
  const { t } = useLanguage();
  const inputRef = useRef<TextInput>(null);

  // Countdown timer for resend button
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown(c => Math.max(0, c - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function handleVerify(finalCode: string) {
    if (finalCode.length !== OTP_LENGTH) return;
    await confirmOtp(email, finalCode);
    // Navigation to home is handled by the root navigator watching auth state
  }

  function handleCodeChange(text: string) {
    const digits = text.replace(/\D/g, '').slice(0, OTP_LENGTH);
    setCode(digits);
    if (digits.length === OTP_LENGTH) {
      handleVerify(digits);
    }
  }

  async function handleResend() {
    if (cooldown > 0) return;
    setCode('');
    await resendOtpCode(email, name);
    setCooldown(RESEND_COOLDOWN);
    inputRef.current?.focus();
  }

  // Render individual digit boxes above the hidden real input
  function renderDigitBoxes() {
    return (
      <View style={styles.boxRow} accessibilityElementsHidden>
        {Array.from({ length: OTP_LENGTH }).map((_, i) => (
          <View
            key={i}
            style={[
              styles.digitBox,
              i < code.length ? styles.digitBoxFilled : null,
              error && code.length === OTP_LENGTH ? styles.digitBoxError : null,
            ]}
          >
            <Text style={styles.digitText}>{code[i] ?? ''}</Text>
          </View>
        ))}
      </View>
    );
  }


  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Light content on the burgundy bar, as on the site. */}
      <StatusBar style="light" />

      <SafeAreaView edges={['top']} style={styles.bar}>
        <Wordmark />
      </SafeAreaView>

      <View style={styles.container}>
        {/* ── Back button ── */}
        <Pressable
          style={styles.backButton}
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel={t.otp.back}
          hitSlop={8}
        >
          <Text style={styles.backText}>{t.otp.back}</Text>
        </Pressable>

        {/* ── Heading ── */}
        <Text style={styles.title} accessibilityRole="header">
          {t.otp.title}
        </Text>
        <Text style={styles.subtitle}>
          {t.otp.subtitle.replace('{n}', String(OTP_LENGTH))}{'\n'}
          <Text style={styles.recipient}>{email}</Text>
        </Text>

        {/* ── Digit boxes (visual only) + hidden real input ── */}
        <Pressable
          onPress={() => inputRef.current?.focus()}
          accessibilityRole="none"
          accessible={false}
        >
          {renderDigitBoxes()}
        </Pressable>

        {/* Hidden but real TextInput for keyboard + accessibility */}
        <TextInput
          ref={inputRef}
          value={code}
          onChangeText={handleCodeChange}
          keyboardType="number-pad"
          maxLength={OTP_LENGTH}
          textContentType="oneTimeCode"
          autoComplete="one-time-code"
          autoFocus
          style={styles.hiddenInput}
          accessibilityLabel={t.otp.inputLabel.replace('{n}', String(OTP_LENGTH))}
          accessibilityHint={t.otp.inputHint}
          accessibilityValue={{ text: t.otp.inputValue.replace('{n}', String(code.length)) }}
        />

        {/* ── Error message ── */}
        {error ? (
          <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}

        {/* ── Verify button ── */}
        <Pressable
          style={({ pressed }) => [
            styles.button,
            code.length < OTP_LENGTH && styles.buttonDisabled,
            pressed && code.length === OTP_LENGTH && styles.buttonPressed,
          ]}
          onPress={() => handleVerify(code)}
          disabled={code.length < OTP_LENGTH || isLoading}
          accessibilityRole="button"
          accessibilityLabel={t.otp.verifyButtonLabel}
          accessibilityState={{ disabled: code.length < OTP_LENGTH || isLoading, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.ivory} />
          ) : (
            <Text style={styles.buttonText}>{t.otp.verifyButton}</Text>
          )}
        </Pressable>

        {/* ── Resend link ── */}
        <Pressable
          onPress={handleResend}
          disabled={cooldown > 0}
          style={styles.resendContainer}
          accessibilityRole="button"
          accessibilityLabel={
            cooldown > 0
              ? t.otp.resendWaitingLabel.replace('{n}', String(cooldown))
              : t.otp.resend
          }
          accessibilityState={{ disabled: cooldown > 0 }}
          hitSlop={8}
        >
          <Text style={[styles.resendText, cooldown > 0 && styles.resendDisabled]}>
            {cooldown > 0
              ? t.otp.resendWaiting.replace('{n}', String(cooldown))
              : t.otp.resend}
          </Text>
        </Pressable>
      </View>
        <PoweredBy />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
  // Burgundy behind the inset as well as the bar, so the notch area matches the header.
  bar: { backgroundColor: colors.burgundy },
  container: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xxl,
    paddingBottom: spacing.xl,
    backgroundColor: colors.ivory,
  },
  backButton: {
    minHeight: MIN_TOUCH,
    justifyContent: 'center',
    marginBottom: spacing.lg,
    alignSelf: 'flex-start',
  },
  backText: {
    fontSize: typography.bodySize,
    color: colors.burgundy,
    fontWeight: '600',
  },
  title: {
    fontFamily: typography.titleFamily,
    fontSize: typography.subtitleSize,
    color: colors.burgundy,
    marginBottom: spacing.sm,
  },
  subtitle: {
    fontSize: typography.bodySize,
    color: colors.charcoal,
    lineHeight: typography.bodySize * 1.6,
    marginBottom: spacing.xl,
  },
  recipient: {
    fontWeight: '700',
    color: colors.burgundy,
  },
  boxRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  digitBox: {
    width: 46,
    height: 56,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
  },
  digitBoxFilled: {
    borderColor: colors.burgundy,
    backgroundColor: colors.ivory,
  },
  digitBoxError: {
    borderColor: colors.error,
  },
  digitText: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.charcoal,
    letterSpacing: 2,
  },
  // Offscreen but accessible to screen readers
  hiddenInput: {
    position: 'absolute',
    opacity: 0,
    width: 1,
    height: 1,
  },
  errorText: {
    fontSize: typography.captionSize,
    color: colors.error,
    marginBottom: spacing.md,
    textAlign: 'center',
  },
  button: {
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
  resendContainer: {
    minHeight: MIN_TOUCH,
    alignItems: 'center',
    justifyContent: 'center',
  },
  resendText: {
    fontSize: typography.bodySize,
    color: colors.burgundy,
    fontWeight: '600',
  },
  resendDisabled: {
    color: colors.muted,
  },
});
