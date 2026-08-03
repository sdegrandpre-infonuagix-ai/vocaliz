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
  room: {
    title: string;
    connecting: string;
    micLive: string;
    micOff: string;
    sourceSection: string;
    sourceInputLabel: string;
    sourceInputHint: string;
    sourceButton: string;
    sourceAdded: string;
    inviteSection: string;
    inviteInputLabel: string;
    inviteInputHint: string;
    inviteButton: string;
    inviteEmailed: string;
    inviteInApp: string;
    inviteEmailFailed: string;
    leaveButton: string;
    errorConnect: string;
    errorGeneric: string;
  };
  /** Fallbacks used when a request fails without the API supplying a reason. */
  auth: {
    errorSendCode: string;
    errorResendCode: string;
    errorInvalidCode: string;
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
  room: {
    title: 'Vous animez le Salon',
    connecting: 'Connexion au salon…',
    micLive: 'Micro actif',
    micOff: 'Micro inactif',
    sourceSection: 'Ajouter une source',
    sourceInputLabel: "URL de l'article à ajouter",
    sourceInputHint: "L'agent en tiendra compte sans interrompre la conversation",
    sourceButton: 'Ajouter à la session',
    sourceAdded: "Source ajoutée. L'agent en a été prévenu.",
    inviteSection: 'Inviter',
    inviteInputLabel: "Adresse courriel de l'invité",
    inviteInputHint: 'Le lien de jonction lui est envoyé par courriel',
    inviteButton: 'Inviter',
    inviteEmailed: 'Courriel envoyé avec le lien de jonction.',
    inviteInApp:
      'Courriel envoyé. Ce contact est inscrit dans Vocaliz : il reçoit aussi une notification.',
    inviteEmailFailed: "Le courriel n'a pas pu partir — partagez le lien ci-dessous vous-même.",
    leaveButton: 'Quitter la session',
    errorConnect: 'Impossible de rejoindre le salon.',
    errorGeneric: 'Une erreur est survenue.',
  },
  auth: {
    errorSendCode: "Impossible d'envoyer le code.",
    errorResendCode: 'Impossible de renvoyer le code.',
    errorInvalidCode: 'Code invalide ou expiré.',
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
  room: {
    title: 'You are hosting the Salon',
    connecting: 'Connecting to the room…',
    micLive: 'Microphone on',
    micOff: 'Microphone off',
    sourceSection: 'Add a source',
    sourceInputLabel: 'URL of the article to add',
    sourceInputHint: 'The agent picks it up without interrupting the conversation',
    sourceButton: 'Add to session',
    sourceAdded: 'Source added. The agent has been notified.',
    inviteSection: 'Invite',
    inviteInputLabel: "Guest's email address",
    inviteInputHint: 'The join link is emailed to them',
    inviteButton: 'Invite',
    inviteEmailed: 'Email sent with the join link.',
    inviteInApp: 'Email sent. This contact has a Vocaliz account: they also get a notification.',
    inviteEmailFailed: 'The email could not be sent — share the link below yourself.',
    leaveButton: 'Leave session',
    errorConnect: 'Unable to join the room.',
    errorGeneric: 'Something went wrong.',
  },
  auth: {
    errorSendCode: 'Could not send the code.',
    errorResendCode: 'Could not resend the code.',
    errorInvalidCode: 'Invalid or expired code.',
  },
};

export const TRANSLATIONS: Record<SupportedLanguage, Translations> = { fr, en };

// The fallback when the device asks for a language we do not speak. The device's own
// locale is preferred over it, and an explicit choice over both — see LanguageContext.
export const DEFAULT_LANGUAGE: SupportedLanguage = 'en';

/**
 * Match a language code (BCP-47 or full tag) to a supported locale, or null when we do
 * not support it.
 *
 * The null case is the point: locale detection has to tell "the device asked for French"
 * apart from "the device asked for Spanish, so fall back to English". resolveLanguage
 * collapses both into English and cannot express that difference.
 */
export function matchLanguage(code: string | null | undefined): SupportedLanguage | null {
  if (!code) return null;
  const base = code.split('-')[0].toLowerCase();
  return base === 'en' || base === 'fr' ? base : null;
}

/** Resolve any language code (BCP-47 or full tag) to a supported locale, defaulting to English. */
export function resolveLanguage(code: string | null | undefined): SupportedLanguage {
  return matchLanguage(code) ?? DEFAULT_LANGUAGE;
}
