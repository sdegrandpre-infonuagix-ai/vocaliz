import React, { useCallback, useState } from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import RoomScreen from '../screens/RoomScreen';
import SessionCreationScreen from '../screens/SessionCreationScreen';
import { colors } from '../theme/tokens';

export type AppStackParamList = {
  SessionCreation: undefined;
};

const Stack = createNativeStackNavigator<AppStackParamList>();

/**
 * Creation and room are swapped in place rather than pushed as routes: the room owns a
 * live LiveKit connection and an audio session, so it must unmount — and run its
 * cleanup — the moment the host leaves, which a navigation stack would not guarantee.
 */
function HostFlow() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  const handleCreated = useCallback((id: string) => setSessionId(id), []);
  const handleLeft = useCallback(() => setSessionId(null), []);

  return sessionId ? (
    <RoomScreen sessionId={sessionId} onLeft={handleLeft} />
  ) : (
    <SessionCreationScreen onSessionCreated={handleCreated} />
  );
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
      <Stack.Screen name="SessionCreation" component={HostFlow} />
    </Stack.Navigator>
  );
}
