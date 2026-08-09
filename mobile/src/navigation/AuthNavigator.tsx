import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import EmailScreen from '../screens/EmailScreen';
import OtpScreen from '../screens/OtpScreen';
import { colors } from '../theme/tokens';

export type AuthStackParamList = {
  Email: undefined;
  // The name travels with the address because the API asks for it on every request,
  // resends included — and this screen has no form to ask for it again.
  Otp: { email: string; name: string };
};

const Stack = createNativeStackNavigator<AuthStackParamList>();

export default function AuthNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.ivory },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="Email" component={EmailScreen} />
      <Stack.Screen name="Otp" component={OtpScreen} />
    </Stack.Navigator>
  );
}
