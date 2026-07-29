import React, { createContext, useCallback, useContext, useState } from 'react';
import { DEFAULT_LANGUAGE, TRANSLATIONS, resolveLanguage } from '../i18n/translations';
import type { SupportedLanguage, Translations } from '../i18n/translations';

interface LanguageContextValue {
  language: SupportedLanguage;
  setLanguage: (code: string) => void;
  t: Translations;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => {},
  t: TRANSLATIONS[DEFAULT_LANGUAGE],
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<SupportedLanguage>(DEFAULT_LANGUAGE);

  const setLanguage = useCallback((code: string) => {
    const resolved = resolveLanguage(code);
    setLanguageState(resolved);
  }, []);

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t: TRANSLATIONS[language] }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
