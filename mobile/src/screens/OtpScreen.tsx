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
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import type { AuthStackParamList } from '../navigation/AuthNavigator';

const OTP_LENGTH = 6;
const RESEND_COOLDOWN = 30; // seconds

type Props = {
  navigation: NativeStackNavigationProp<AuthStackParamList, 'Otp'>;
  route: RouteProp<AuthStackParamList, 'Otp'>;
};

export default function OtpScreen({ navigation, route }: Props) {
  const { phoneNumber } = route.params;
  const [code, setCode] = useState('');
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN);
  const { confirmOtp, resendOtpCode, isLoading, error } = useAuth();
  const inputRef = useRef<TextInput>(null);

  // Countdown timer for resend button
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown(c => Math.max(0, c - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function handleVerify(finalCode: string) {
    if (finalCode.length !== OTP_LENGTH) return;
    await confirmOtp(phoneNumber, finalCode);
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
    await resendOtpCode(phoneNumber);
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

  const maskedPhone = phoneNumber.replace(/(\+\d{1,3})\d+(\d{4})/, '$1 ••••• $2');

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar style="dark" />
      <View style={styles.container}>
        {/* ── Back button ── */}
        <Pressable
          style={styles.backButton}
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="Retour"
          hitSlop={8}
        >
          <Text style={styles.backText}>← Retour</Text>
        </Pressable>

        {/* ── Heading ── */}
        <Text style={styles.title} accessibilityRole="header">
          Code de vérification
        </Text>
        <Text style={styles.subtitle}>
          Entrez le code à {OTP_LENGTH} chiffres envoyé au{'\n'}
          <Text style={styles.phone}>{maskedPhone}</Text>
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
          accessibilityLabel={`Code OTP à ${OTP_LENGTH} chiffres`}
          accessibilityHint="Entrez les 6 chiffres reçus par SMS"
          accessibilityValue={{ text: `${code.length} chiffres saisis` }}
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
          accessibilityLabel="Valider le code"
          accessibilityState={{ disabled: code.length < OTP_LENGTH || isLoading, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.ivory} />
          ) : (
            <Text style={styles.buttonText}>Valider</Text>
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
              ? `Renvoyer le code dans ${cooldown} secondes`
              : 'Renvoyer le code'
          }
          accessibilityState={{ disabled: cooldown > 0 }}
          hitSlop={8}
        >
          <Text style={[styles.resendText, cooldown > 0 && styles.resendDisabled]}>
            {cooldown > 0 ? `Renvoyer dans ${cooldown}s` : 'Renvoyer le code'}
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
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
  phone: {
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
