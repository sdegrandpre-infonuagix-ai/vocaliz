import React, { createContext, useCallback, useContext, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { requestOtp, resendOtp, verifyOtp } from '../services/authApi';

const TOKEN_KEY = 'salon_jwt';
const USER_ID_KEY = 'salon_user_id';

interface AuthState {
  token: string | null;
  userId: string | null;
  isLoading: boolean;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  sendOtp: (phoneNumber: string) => Promise<void>;
  resendOtpCode: (phoneNumber: string) => Promise<void>;
  confirmOtp: (phoneNumber: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    userId: null,
    isLoading: false,
    error: null,
  });

  const setLoading = () => setState(s => ({ ...s, isLoading: true, error: null }));
  const setError = (error: string) => setState(s => ({ ...s, isLoading: false, error }));

  const sendOtp = useCallback(async (phoneNumber: string) => {
    setLoading();
    try {
      await requestOtp(phoneNumber);
      setState(s => ({ ...s, isLoading: false }));
    } catch (e: any) {
      setError(e.message ?? 'Impossible d\'envoyer le code.');
    }
  }, []);

  const resendOtpCode = useCallback(async (phoneNumber: string) => {
    setLoading();
    try {
      await resendOtp(phoneNumber);
      setState(s => ({ ...s, isLoading: false }));
    } catch (e: any) {
      setError(e.message ?? 'Impossible de renvoyer le code.');
    }
  }, []);

  const confirmOtp = useCallback(async (phoneNumber: string, code: string) => {
    setLoading();
    try {
      const { token, userId } = await verifyOtp(phoneNumber, code);
      await SecureStore.setItemAsync(TOKEN_KEY, token);
      await SecureStore.setItemAsync(USER_ID_KEY, userId);
      setState({ token, userId, isLoading: false, error: null });
    } catch (e: any) {
      setError(e.message ?? 'Code invalide ou expiré.');
    }
  }, []);

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
