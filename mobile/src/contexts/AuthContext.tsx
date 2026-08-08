import React, { createContext, useCallback, useContext, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { requestOtp, resendOtp, verifyOtp } from '../services/authApi';
import { useLanguage } from './LanguageContext';

import { JWT as TOKEN_KEY, USER_ID as USER_ID_KEY } from '../services/secureStoreKeys';

interface AuthState {
  token: string | null;
  userId: string | null;
  isLoading: boolean;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  sendOtp: (email: string) => Promise<void>;
  resendOtpCode: (email: string) => Promise<void>;
  confirmOtp: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // AuthProvider is mounted inside LanguageProvider, so these fallbacks follow the
  // interface language instead of being French whatever the user picked.
  const { t } = useLanguage();

  const [state, setState] = useState<AuthState>({
    token: null,
    userId: null,
    isLoading: false,
    error: null,
  });

  const setLoading = () => setState(s => ({ ...s, isLoading: true, error: null }));
  const setError = (error: string) => setState(s => ({ ...s, isLoading: false, error }));

  const sendOtp = useCallback(async (email: string) => {
    setLoading();
    try {
      await requestOtp(email);
      setState(s => ({ ...s, isLoading: false }));
    } catch (e: any) {
      setError(e.message ?? t.auth.errorSendCode);
    }
  }, [t]);

  const resendOtpCode = useCallback(async (email: string) => {
    setLoading();
    try {
      await resendOtp(email);
      setState(s => ({ ...s, isLoading: false }));
    } catch (e: any) {
      setError(e.message ?? t.auth.errorResendCode);
    }
  }, [t]);

  const confirmOtp = useCallback(async (email: string, code: string) => {
    setLoading();
    try {
      const { token, userId } = await verifyOtp(email, code);
      await SecureStore.setItemAsync(TOKEN_KEY, token);
      await SecureStore.setItemAsync(USER_ID_KEY, userId);
      setState({ token, userId, isLoading: false, error: null });
    } catch (e: any) {
      setError(e.message ?? t.auth.errorInvalidCode);
    }
  }, [t]);

  const signOut = useCallback(async () => {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(USER_ID_KEY);
    setState({ token: null, userId: null, isLoading: false, error: null });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, sendOtp, resendOtpCode, confirmOtp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
