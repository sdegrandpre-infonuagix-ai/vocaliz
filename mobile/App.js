import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';
import { registerGlobals } from '@livekit/react-native';

// Register WebRTC globals before any LiveKit usage
registerGlobals();

export default function App() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Salon</Text>
      <Text style={styles.subtitle}>Chargement…</Text>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8F3E8',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#6B0F1A',
    letterSpacing: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#8C7853',
    marginTop: 8,
  },
});
