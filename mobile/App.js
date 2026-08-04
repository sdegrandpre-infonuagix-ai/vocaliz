import { NavigationContainer } from '@react-navigation/native';
import {
  PlayfairDisplay_700Bold,
  useFonts,
} from '@expo-google-fonts/playfair-display';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { registerGlobals } from '@livekit/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

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
  const { suggestLanguage, adoptSavedLanguage } = useLanguage();

  useEffect(() => {
    if (!token) return;
    getMyProfile(token)
      .then(profile => {
        // A choice made on another device outranks anything inferred here, so it is applied
        // first and the detected language below can only fill a gap it left.
        if (profile.interfaceLanguage) {
          adoptSavedLanguage(profile.interfaceLanguage);
        }
        if (profile.detectedLanguage) {
          suggestLanguage(profile.detectedLanguage);
        }
      })
      .catch(() => {
        // Profile fetch is best-effort; fall back to default language silently
      });
  }, [token, suggestLanguage, adoptSavedLanguage]);

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
    // The dependency was installed but never mounted, so every SafeAreaView in the app would
    // have reported zero insets. Needed now that a coloured bar sits at the very top of the
    // screen: without real insets it slides under the notch and the wordmark meets the clock.
    <SafeAreaProvider>
      <LanguageProvider>
        <AuthProvider>
          <LanguageBootstrap />
          <NavigationContainer>
            <RootNavigator />
          </NavigationContainer>
        </AuthProvider>
      </LanguageProvider>
    </SafeAreaProvider>
  );
}
