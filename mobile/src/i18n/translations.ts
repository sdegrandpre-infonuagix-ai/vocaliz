export type SupportedLanguage = 'fr' | 'en';

export interface Translations {
  email: {
    subtitle: string;
    inputLabel: string;
    inputHint: string;
    button: string;
    legal: string;
  };
  otp: {
    back: string;
    title: string;
    subtitle: string;
    inputLabel: string;
    inputHint: string;
    inputValue: string;
    verifyButton: string;
    verifyButtonLabel: string;
    resendWaiting: string;
    resendWaitingLabel: string;
    resend: string;
  };
  session: {
    title: string;
    subtitle: string;
    urlLabel: string;
    urlInputLabel: string;
    urlInputHint: string;
    startButton: string;
    or: string;
    uploadButton: string;
    uploadButtonLabel: string;
    uploadButtonHint: string;
    uploadComingSoonTitle: string;
    uploadComingSoonMsg: string;
    noSourceButton: string;
    noSourceButtonLabel: string;
    noSourceButtonHint: string;
    errorGeneric: string;
  };
}

const fr: Translations = {
  email: {
    subtitle: 'Entrez votre adresse courriel pour commencer.',
    inputLabel: 'Adresse courriel',
    inputHint: 'Entrez votre adresse courriel, par exemple vous@exemple.com',
    button: 'Recevoir mon code',
    legal: "En continuant, vous acceptez nos conditions d'utilisation.",
  },
  otp: {
    back: '← Retour',
    title: 'Code de vérification',
    subtitle: 'Entrez le code à {n} chiffres envoyé à',
    inputLabel: 'Code OTP à {n} chiffres',
    inputHint: 'Entrez les 6 chiffres reçus par courriel',
    inputValue: '{n} chiffres saisis',
    verifyButton: 'Valider',
    verifyButtonLabel: 'Valider le code',
    resendWaiting: 'Renvoyer dans {n}s',
    resendWaitingLabel: 'Renvoyer le code dans {n} secondes',
    resend: 'Renvoyer le code',
  },
  session: {
    title: 'Nouvelle session',
    subtitle: "Partagez une URL d'article pour démarrer une discussion guidée par l'agent.",
    urlLabel: "URL de l'article",
    urlInputLabel: "URL de l'article source",
    urlInputHint: "Entrez l'adresse web de l'article à discuter",
    startButton: 'Démarrer la session',
    or: 'ou',
    uploadButton: '📄  Téléverser un document',
    uploadButtonLabel: 'Téléverser un document',
    uploadButtonHint: 'Sélectionnez un fichier PDF ou texte',
    uploadComingSoonTitle: 'Prochainement',
    uploadComingSoonMsg:
      'Le téléversement de documents sera disponible dans la prochaine mise à jour.',
    noSourceButton: 'Démarrer sans source',
    noSourceButtonLabel: 'Démarrer une session sans document ni URL',
    noSourceButtonHint:
      "L'agent vous demandera de quoi vous souhaitez discuter",
    errorGeneric: 'Impossible de créer la session.',
  },
};

const en: Translations = {
  email: {
    subtitle: 'Enter your email address to get started.',
    inputLabel: 'Email address',
    inputHint: 'Enter your email address, e.g. you@example.com',
    button: 'Receive my code',
    legal: 'By continuing, you accept our terms of use.',
  },
  otp: {
    back: '← Back',
    title: 'Verification Code',
    subtitle: 'Enter the {n}-digit code sent to',
    inputLabel: '{n}-digit OTP code',
    inputHint: 'Enter the 6 digits received by email',
    inputValue: '{n} digits entered',
    verifyButton: 'Confirm',
    verifyButtonLabel: 'Confirm code',
    resendWaiting: 'Resend in {n}s',
    resendWaitingLabel: 'Resend code in {n} seconds',
    resend: 'Resend code',
  },
  session: {
    title: 'New Session',
    subtitle: 'Share an article URL to start an agent-guided discussion.',
    urlLabel: 'Article URL',
    urlInputLabel: 'Source article URL',
    urlInputHint: 'Enter the web address of the article to discuss',
    startButton: 'Start Session',
    or: 'or',
    uploadButton: '📄  Upload a document',
    uploadButtonLabel: 'Upload a document',
    uploadButtonHint: 'Select a PDF or text file',
    uploadComingSoonTitle: 'Coming soon',
    uploadComingSoonMsg: 'Document upload will be available in the next update.',
    noSourceButton: 'Start without a source',
    noSourceButtonLabel: 'Start a session with no document or URL',
    noSourceButtonHint: 'The agent will ask what you would like to discuss',
    errorGeneric: 'Unable to create the session.',
  },
};

export const TRANSLATIONS: Record<SupportedLanguage, Translations> = { fr, en };

export const DEFAULT_LANGUAGE: SupportedLanguage = 'fr';

/** Resolve any language code (BCP-47 or full tag) to a supported locale, defaulting to 'fr'. */
export function resolveLanguage(code: string | null | undefined): SupportedLanguage {
  if (!code) return DEFAULT_LANGUAGE;
  const base = code.split('-')[0].toLowerCase();
  if (base === 'en') return 'en';
  if (base === 'fr') return 'fr';
  return DEFAULT_LANGUAGE;
}
