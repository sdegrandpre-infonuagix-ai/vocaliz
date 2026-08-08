import React, { useCallback, useState } from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import RoomScreen from '../screens/RoomScreen';
import SalonCreationScreen from '../screens/SalonCreationScreen';
import { colors } from '../theme/tokens';

export type AppStackParamList = {
  SalonCreation: undefined;
};

const Stack = createNativeStackNavigator<AppStackParamList>();

/**
 * Creation and room are swapped in place rather than pushed as routes: the room owns a
 * live LiveKit connection and an audio session, so it must unmount — and run its
 * cleanup — the moment the host leaves, which a navigation stack would not guarantee.
 */
function HostFlow() {
  const [salonId, setSalonId] = useState<string | null>(null);

  const handleCreated = useCallback((id: string) => setSalonId(id), []);
  const handleLeft = useCallback(() => setSalonId(null), []);

  return salonId ? (
    <RoomScreen salonId={salonId} onLeft={handleLeft} />
  ) : (
    <SalonCreationScreen onSalonCreated={handleCreated} />
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
      <Stack.Screen name="SalonCreation" component={HostFlow} />
    </Stack.Navigator>
  );
}
