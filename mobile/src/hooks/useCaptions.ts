/**
 * Live captions: what is said in the Salon, in the language the reader chose.
 *
 * Each finalised turn arrives over the room's data channel, already translated by the
 * agent into the languages the participants said they were reading. The choice travels
 * the other way as a participant attribute, so changing it takes effect on the next turn
 * without the agent having to be told anything.
 *
 * The chosen language is kept on the device rather than on the account: someone may
 * follow a French salon in English on the train and in French at home, and it is a
 * property of how they are reading right now, not of who they are.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
// The same store the interface language already uses. Nothing here is a secret, but
// adding a second persistence library for one string would be worse than the mismatch.
import * as SecureStore from 'expo-secure-store';
import { Room, RoomEvent } from 'livekit-client';

/** The room data topic captions travel on, matching the agent's. */
export const CAPTION_TOPIC = 'captions';

/** The attribute a client sets on itself to say what it is reading. */
export const CAPTION_LANGUAGE_ATTRIBUTE = 'caption_lang';

// SecureStore keys accept only letters, digits, dot, dash and underscore.
const STORAGE_KEY = 'vocaliz.captionLang';

export interface Caption {
  sequence: number;
  speaker: string;
  role: string;
  /** As spoken. Kept beside the translation so an odd rendering can be checked. */
  text: string;
  language: string | null;
  /** Keyed by language. A language whose translation failed is absent, not echoed. */
  translations: Record<string, string>;
}

/** An empty value means "as spoken" — no translation, which is also the default. */
export const CAPTION_LANGUAGES: Array<{ code: string; label: string }> = [
  { code: '', label: '' }, // labelled from the interface dictionary, not here
  { code: 'en', label: "English" },
  { code: 'fr', label: "Français" },
  { code: 'es', label: "Español" },
  { code: 'pt', label: "Português" },
  { code: 'de', label: "Deutsch" },
  { code: 'it', label: "Italiano" },
  { code: 'ar', label: "العربية" },
  { code: 'fa', label: "فارسی" },
  { code: 'bn', label: "বাংলা" },
  { code: 'zh', label: "中文" },
  { code: 'hi', label: "हिन्दी" },
  { code: 'id', label: "Indonesia" },
  { code: 'ja', label: "日本語" },
  { code: 'ko', label: "한국어" },
  { code: 'ru', label: "Русский" },
  { code: 'tr', label: "Türkçe" },
  { code: 'vi', label: "Tiếng Việt" },
  { code: 'af', label: "Afrikaans" },
  { code: 'am', label: "አማርኛ" },
  { code: 'az', label: "azərbaycan" },
  { code: 'bg', label: "български" },
  { code: 'bs', label: "bosanski" },
  { code: 'ca', label: "català" },
  { code: 'cs', label: "čeština" },
  { code: 'cy', label: "Cymraeg" },
  { code: 'da', label: "dansk" },
  { code: 'el', label: "Ελληνικά" },
  { code: 'et', label: "eesti" },
  { code: 'fi', label: "suomi" },
  { code: 'ga', label: "Gaeilge" },
  { code: 'gu', label: "ગુજરાતી" },
  { code: 'ha', label: "Hausa" },
  { code: 'he', label: "עברית" },
  { code: 'hr', label: "hrvatski" },
  { code: 'ht', label: "Kreyòl ayisyen" },
  { code: 'hu', label: "magyar" },
  { code: 'hy', label: "հայերեն" },
  { code: 'is', label: "íslenska" },
  { code: 'ka', label: "ქართული" },
  { code: 'kk', label: "қазақ тілі" },
  { code: 'kn', label: "ಕನ್ನಡ" },
  { code: 'lt', label: "lietuvių" },
  { code: 'lv', label: "latviešu" },
  { code: 'mk', label: "македонски" },
  { code: 'ml', label: "മലയാളം" },
  { code: 'mn', label: "монгол" },
  { code: 'mr', label: "मराठी" },
  { code: 'ms', label: "Melayu" },
  { code: 'mt', label: "Malti" },
  { code: 'nl', label: "Nederlands" },
  { code: 'no', label: "norsk" },
  { code: 'pa', label: "ਪੰਜਾਬੀ" },
  { code: 'pl', label: "polski" },
  { code: 'ps', label: "پښتو" },
  { code: 'ro', label: "română" },
  { code: 'si', label: "සිංහල" },
  { code: 'sk', label: "slovenčina" },
  { code: 'sl', label: "slovenščina" },
  { code: 'so', label: "Soomaali" },
  { code: 'sq', label: "shqip" },
  { code: 'sr', label: "српски" },
  { code: 'sv', label: "svenska" },
  { code: 'sw', label: "Kiswahili" },
  { code: 'ta', label: "தமிழ்" },
  { code: 'te', label: "తెలుగు" },
  { code: 'th', label: "ไทย" },
  { code: 'tl', label: "Filipino" },
  { code: 'uk', label: "українська" },
  { code: 'ur', label: "اردو" },
  { code: 'uz', label: "o‘zbek" },
];

export function useCaptions(room: Room | null) {
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [language, setLanguageState] = useState('');

  // Read once, before the first attribute is published, so a returning participant does
  // not spend the first turn of a conversation reading a language they did not choose.
  const restored = useRef(false);
  useEffect(() => {
    SecureStore.getItemAsync(STORAGE_KEY)
      .then((stored) => {
        if (stored) setLanguageState(stored);
      })
      .catch(() => {})
      .finally(() => {
        restored.current = true;
      });
  }, []);

  // Publishing is how the agent learns what to translate into. Sent on connect and on
  // every change; a failure costs captions in that language and nothing else, so it is
  // deliberately swallowed rather than surfaced.
  useEffect(() => {
    if (!room) return;
    try {
      room.localParticipant.setAttributes({ [CAPTION_LANGUAGE_ATTRIBUTE]: language });
    } catch (e) {
      // Logged rather than swallowed. This call is the whole mechanism: if the token
      // lacks canUpdateOwnMetadata the server refuses it, the agent sees nobody asking
      // for a translation, and captions arrive in the language they were spoken —
      // indistinguishable from a broken translator unless the refusal is visible.
      console.warn('Vocaliz: could not publish the caption language', e);
    }
  }, [room, language]);

  useEffect(() => {
    if (!room) return;

    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string,
    ) => {
      if (topic !== CAPTION_TOPIC) return;
      let message: any;
      try {
        message = JSON.parse(new TextDecoder().decode(payload));
      } catch {
        return;
      }
      if (!message || message.type !== 'caption' || !message.text) return;

      setCaptions((previous) => {
        // The agent may retry a turn; one row per sequence stops a caption appearing
        // twice, which reads as the speaker having repeated themselves.
        if (previous.some((c) => c.sequence === message.sequence)) return previous;
        return [
          ...previous,
          {
            sequence: message.sequence,
            speaker: message.speaker ?? '',
            role: message.role ?? '',
            text: message.text,
            language: message.language ?? null,
            translations: message.translations ?? {},
          },
        ];
      });
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room]);

  const setLanguage = useCallback((next: string) => {
    setLanguageState(next);
    SecureStore.setItemAsync(STORAGE_KEY, next).catch(() => {});
  }, []);

  return { captions, language, setLanguage };
}

/**
 * What to show for one caption: the translation when there is one, the spoken words
 * otherwise.
 *
 * Turns that arrived before a change of language carry no translation into the newly
 * chosen one — the agent only asks for languages somebody was reading at the time — so
 * they fall back to what was said rather than disappearing.
 */
export function captionText(caption: Caption, language: string): string {
  if (!language) return caption.text;
  return caption.translations[language] ?? caption.text;
}
