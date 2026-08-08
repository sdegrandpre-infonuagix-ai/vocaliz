import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { getLocales } from 'expo-localization';
import {
  DEFAULT_LANGUAGE,
  TRANSLATIONS,
  matchLanguage,
  resolveLanguage,
} from '../i18n/translations';
import type { SupportedLanguage, Translations } from '../i18n/translations';
import { LANGUAGE as LANGUAGE_KEY, migrateLegacyKeys } from '../services/secureStoreKeys';

/**
 * Three things want to choose the interface language, and they do not agree. Ranking them
 * settles it once instead of letting whichever arrives last win:
 *
 *  - `user`    — the header switch. Always wins, and is remembered across launches.
 *  - `device`  — the phone's own language list. A strong signal, read at startup.
 *  - `profile` — the language the agent heard the host *speak*. A guess about their
 *                interface preference, and the weakest of the three.
 *  - `default` — English, when nothing else matched.
 *
 * A new value applies only if its rank is at least the current one.
 */
const SOURCE_RANK = { default: 0, profile: 1, device: 2, user: 3 } as const;
type LanguageSource = keyof typeof SOURCE_RANK;

interface LanguageContextValue {
  language: SupportedLanguage;
  /** Record a language the user picked themselves. Persisted, and final. */
  setLanguage: (code: string) => void;
  /**
   * A choice this person made on another device, read back from their account.
   *
   * Enters at the same rank as a choice made here, because that is what it is — the account
   * ranks below the device only for languages that were *inferred*, and this one was picked.
   * Not written back to the server: it came from there.
   */
  adoptSavedLanguage: (code: string) => void;
  /** Offer a language inferred elsewhere — applied only if nothing stronger has spoken. */
  suggestLanguage: (code: string) => void;
  t: Translations;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => {},
  adoptSavedLanguage: () => {},
  suggestLanguage: () => {},
  t: TRANSLATIONS[DEFAULT_LANGUAGE],
});

/**
 * First supported entry in the device's ordered language list.
 *
 * The list is ordered by preference, so a device set to [es, fr, en] should get French,
 * not English — taking the first entry we happen to recognise is what makes that work.
 * getLocales() is synchronous, so this can seed the initial state with no flash of
 * English on the way to French.
 */
function detectDeviceLanguage(): { language: SupportedLanguage; source: LanguageSource } {
  try {
    for (const locale of getLocales()) {
      const matched = matchLanguage(locale.languageCode ?? locale.languageTag);
      if (matched) return { language: matched, source: 'device' };
    }
  } catch {
    // Locale unreadable — English stands.
  }
  return { language: DEFAULT_LANGUAGE, source: 'default' };
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const initial = useRef(detectDeviceLanguage()).current;
  const [language, setLanguageState] = useState<SupportedLanguage>(initial.language);

  // Where the current value came from. A ref as well as state because suggestLanguage()
  // is called from an effect whose closure would otherwise capture a stale value.
  const sourceRef = useRef<LanguageSource>(initial.source);

  const applyIfStronger = useCallback((next: SupportedLanguage, source: LanguageSource) => {
    if (SOURCE_RANK[source] < SOURCE_RANK[sourceRef.current]) return;
    sourceRef.current = source;
    setLanguageState(next);
  }, []);

  // Restore a previous explicit choice. Until this resolves the detected language stands,
  // which is a reasonable thing to be showing in the meantime.
  useEffect(() => {
    let active = true;
    // The migration has to complete before the read, not beside it: a launch that read
    // first would find nothing under the new key and quietly fall back to detection,
    // discarding a choice the user had already made.
    migrateLegacyKeys()
      .then(() => SecureStore.getItemAsync(LANGUAGE_KEY))
      .then(stored => {
        if (!active || !stored) return;
        applyIfStronger(resolveLanguage(stored), 'user');
      })
      .catch(() => {
        // No stored preference readable — detection stands.
      });
    return () => {
      active = false;
    };
  }, [applyIfStronger]);

  const setLanguage = useCallback(
    (code: string) => {
      applyIfStronger(resolveLanguage(code), 'user');
      SecureStore.setItemAsync(LANGUAGE_KEY, resolveLanguage(code)).catch(() => {
        // Persistence is best-effort; the choice still holds for this run.
      });
    },
    [applyIfStronger],
  );

  // The same effect as setLanguage minus the trip back to the server, since this value came
  // from there. Still written to SecureStore: the next launch should not have to wait for a
  // network round trip to show the right language.
  const adoptSavedLanguage = useCallback(
    (code: string) => {
      const matched = matchLanguage(code);
      if (!matched) return;
      applyIfStronger(matched, 'user');
      SecureStore.setItemAsync(LANGUAGE_KEY, matched).catch(() => {
        // Best-effort, exactly as above.
      });
    },
    [applyIfStronger],
  );

  // Deliberately not persisted: only a real choice is worth remembering across launches.
  const suggestLanguage = useCallback(
    (code: string) => {
      const matched = matchLanguage(code);
      if (matched) applyIfStronger(matched, 'profile');
    },
    [applyIfStronger],
  );

  return (
    <LanguageContext.Provider
      value={{
        language,
        setLanguage,
        adoptSavedLanguage,
        suggestLanguage,
        t: TRANSLATIONS[language],
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
