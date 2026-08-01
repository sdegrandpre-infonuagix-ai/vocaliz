import { NavigationContainer } from '@react-navigation/native';
import {
  PlayfairDisplay_700Bold,
  useFonts,
} from '@expo-google-fonts/playfair-display';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { registerGlobals } from '@livekit/react-native';

import { AuthProvider, useAuth } from './src/contexts/AuthContext';
import { LanguageProvider, useLanguage } from './src/contexts/LanguageContext';
import RootNavigator from './src/navigation/RootNavigator';
import { colors } from './src/theme/tokens';
import { getMyProfile } from './src/services/userApi';

// Register WebRTC globals before any LiveKit usage
registerGlobals();

// Keep splash screen visible while fonts load
SplashScreen.preventAutoHideAsync();

/**
 * Fetches the user's detected language from the API and offers it to the
 * LanguageContext whenever the auth token becomes available.
 * Renders nothing — side-effect only.
 *
 * A suggestion, not an assignment: the detected language comes from the speech the agent
 * heard, so it must not overrule a host who picked a language from the header switch.
 */
function LanguageBootstrap() {
  const { token } = useAuth();
  const { suggestLanguage } = useLanguage();

  useEffect(() => {
    if (!token) return;
    getMyProfile(token)
      .then(profile => {
        if (profile.detectedLanguage) {
          suggestLanguage(profile.detectedLanguage);
        }
      })
      .catch(() => {
        // Profile fetch is best-effort; fall back to default language silently
      });
  }, [token, suggestLanguage]);

  return null;
}

export default function App() {
  const [fontsLoaded] = useFonts({ PlayfairDisplay_700Bold });

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync();
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.ivory, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.burgundy} />
      </View>
    );
  }

  return (
    <LanguageProvider>
      <AuthProvider>
        <LanguageBootstrap />
        <NavigationContainer>
          <RootNavigator />
        </NavigationContainer>
      </AuthProvider>
    </LanguageProvider>
  );
}
