import React from 'react';

import { useAuth } from '../contexts/AuthContext';
import AppNavigator from './AppNavigator';
import AuthNavigator from './AuthNavigator';

/**
 * Auth gate: the OTP flow until a JWT is held, the session flow afterwards.
 * confirmOtp() sets the token in AuthContext, which flips this over.
 */
export default function RootNavigator() {
  const { token } = useAuth();
  return token ? <AppNavigator /> : <AuthNavigator />;
}
