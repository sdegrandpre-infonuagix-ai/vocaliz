import React from 'react';
import { Alert } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import SessionCreationScreen from '../screens/SessionCreationScreen';
import { colors } from '../theme/tokens';

export type AppStackParamList = {
  SessionCreation: undefined;
};

const Stack = createNativeStackNavigator<AppStackParamList>();

/**
 * The in-app room UI does not exist yet — the agent conversation currently only
 * runs in the web guest client (api/web/join.html). Until a room screen lands,
 * surface the provisioned room so the created session can be verified on-device.
 */
function handleSessionCreated(sessionId: string, roomName: string) {
  Alert.alert('Session créée', `Salon : ${roomName}\nSession : ${sessionId}`);
}

// Declared at module scope so React Navigation sees a stable component identity.
function SessionCreationRoute() {
  return <SessionCreationScreen onSessionCreated={handleSessionCreated} />;
}

export default function AppNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.ivory },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="SessionCreation" component={SessionCreationRoute} />
    </Stack.Navigator>
  );
}
