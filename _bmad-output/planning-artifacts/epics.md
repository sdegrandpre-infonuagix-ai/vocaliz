---
stepsCompleted: [1, 2, 3]
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/architecture.md', '_bmad-output/planning-artifacts/ux-design-specification.md']
---

# salon - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for salon, decomposing the requirements from the PRD, UX Design, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Un hôte peut créer une session en téléversant un document ou en fournissant une URL de nouvelle comme source
FR2: Un hôte peut inviter exactement un invité à une session par commande vocale, en nommant un ami enregistré dans Salon (livraison par notification in-app) ou un contact de son téléphone (livraison par SMS)
FR3: Un hôte peut ajouter un document ou une URL supplémentaire à une session active, avant ou pendant celle-ci
FR4: Un invité sans l'application mobile installée peut rejoindre une session directement depuis un navigateur web, sans créer de compte
FR5: Un lien d'invitation ne peut être utilisé qu'une seule fois pour rejoindre une session
FR6: Un agent vocal lit à voix haute le contenu source de la session aux participants
FR7: Les participants peuvent discuter du contenu source avec l'agent vocal et entre eux sans l'avoir lu ou consulté au préalable
FR8: L'agent vocal introduit des informations contrastantes provenant d'autres sources pendant la discussion
FR9: Les participants prennent la parole selon les pauses naturelles de la conversation, sans mécanisme formel de demande de parole
FR10: L'agent vocal comprend le langage naturel des participants en tout temps, sans mot-clé de réveil requis
FR11: Les participants peuvent ajuster vocalement la fréquence d'intervention proactive de l'agent (par défaut : une intervention succincte par minute lorsque les participants partagent la même langue ; plus fréquent lorsque l'agent traduit activement entre deux langues différentes)
FR12: Le système détecte automatiquement la langue parlée par chaque participant, sans sélection manuelle
FR13: L'affichage visuel de l'application (les quelques écrans existants) est présenté dans la langue vocale détectée de l'utilisateur, sans sélection manuelle
FR14: Les participants peuvent s'exprimer dans leur propre langue pendant une session
FR15: Le contenu parlé est traduit et lu à voix haute à chaque participant dans sa propre langue, lorsque les participants parlent des langues différentes
FR16: Le contenu traduit est lu à voix haute pendant que l'interlocuteur d'origine continue de parler, sans interrompre la conversation
FR17: L'audio traduit destiné à un participant ne crée pas d'écho dans l'audio partagé de la session
FR18: Un nouvel utilisateur doit créer un compte avec un numéro de téléphone vérifié avant de pouvoir utiliser Salon pour la première fois
FR19: Un hôte dispose d'une heure d'essai gratuite à vie, cumulée sur l'ensemble de ses sessions
FR20: Le système comptabilise précisément, à la minute et à la seconde près, le temps de conversation cumulé de chaque hôte, pour déterminer le moment exact où l'heure d'essai gratuite est épuisée
FR21: Un hôte doit ajouter une méthode de paiement (Stripe) une fois son heure d'essai gratuite épuisée, pour continuer à utiliser Salon en tant qu'hôte
FR22: Un hôte est facturé 5 USD par heure (au prorata de la seconde) au-delà de son heure d'essai gratuite
FR23: Un invité n'est jamais facturé, peu importe la durée de la session
FR24: Un participant peut quitter une session à tout moment par une commande vocale dans sa propre langue
FR25: Un participant peut quitter une session à tout moment en fermant l'application ou le navigateur
FR26: L'agent vocal pose une question simple de satisfaction immédiatement après qu'un participant a prononcé la commande de sortie de session
FR27: Un invité non-authentifié peut répondre à la question de satisfaction de fin de session sans posséder de compte persistant
FR28: Un utilisateur inscrit peut consulter son historique de sessions passées et de partenaires de discussion
FR29: Un utilisateur inscrit peut démarrer une nouvelle session avec n'importe quel partenaire de discussion précédent
FR30: Un invité anonyme reçoit automatiquement un SMS avec un lien d'installation de l'application native une fois sa session terminée
FR31: Un invité anonyme peut installer l'application native via ce lien et continuer à utiliser Salon en tant qu'utilisateur inscrit

### NonFunctional Requirements

NFR1: Performance — Aucun seuil de latence formel n'est fixé pour le MVP ; la latence du pipeline voix→traduction→voix sera validée empiriquement une fois l'usage réel commencé.
NFR2: Security — Salon ne conserve aucun transcript de session pour le MVP (traitement éphémère en mémoire) ; les liens d'invitation à usage unique expirent après la première connexion ; les méthodes de paiement sont gérées entièrement via Stripe (tokenisation).
NFR3: Integration — En cas d'indisponibilité de xAI, LiveKit, ou Stripe, le système doit présenter un message d'erreur clair plutôt qu'un échec silencieux.

### Additional Requirements

- Starter template worker d'agent : `lk app create --template agent-starter-python` + `uv add "livekit-agents[xai,silero,turn-detector]"` (Story 1.1)
- Starter template mobile : `npx create-expo-app` avec Expo Development Build (pas Expo Go) requis dès le départ pour supporter `@livekit/react-native` (Story 1.2)
- Infrastructure AWS : Lambda + API Gateway (API REST), ECS Fargate (worker d'agent xAI), Aurora Serverless v2 PostgreSQL, S3+CloudFront (page de jonction web), Secrets Manager (clés API), CloudWatch Logs (monitoring), GitHub Actions (CI/CD)
- Intégrations tierces : xAI (plugin `livekit-agents[xai]`), LiveKit Cloud (managé, pas d'auto-hébergement), Stripe (paiement), AWS SNS (OTP SMS)
- Base de données : schéma relationnel (`users`, `sessions`, `friends`, `billing_events`), migrations Alembic
- Authentification : OTP par SMS uniquement, JWT à courte durée pour utilisateurs inscrits, token à usage unique pour jonction anonyme
- Métrage de facturation : heartbeat périodique (30s) du worker vers l'API + callback final, pour fiabilité en cas de déconnexion
- Règle métier "ami Salon" : un contact ne devient un ami Salon (livraison in-app) que s'il s'est lui-même inscrit avec un numéro vérifié ; sinon, joignable uniquement par SMS
- Conventions : JSON camelCase (alias Pydantic) / Python snake_case interne, erreurs API au format `{detail: string}`, dates ISO 8601 UTC

### UX Design Requirements

UX-DR1: Design tokens — palette "Salon Parisien" (bourgogne profond, or/laiton en accent, beige ivoire chaud, charbon pour le texte), typographie serif classique pour les titres (ex. Playfair Display) + sans-serif accessible pour le corps
UX-DR2: Composant réutilisable — Indicateur d'Onde Vocale (6 barres animées, états écoute/traduction/silencieux, label ARIA requis)
UX-DR3: Composant réutilisable — Badge Logo Causeuse (grand logo rond, silhouette de causeuse classique à 3 places en ligne dorée, centré en haut de chaque écran)
UX-DR4: Composant réutilisable — Bandeau de Confirmation (affichage d'état d'invitation, non-tapable)
UX-DR5: Composant réutilisable — Badge "Sans Installation" (pilule or, écran de jonction anonyme uniquement)
UX-DR6: Icône vectorielle custom — manipulateur télégraphique du 19ᵉ siècle (clé Morse) pour l'écran de vérification téléphone, remplaçant une icône téléphone générique
UX-DR7: Accessibilité WCAG AA — contraste 4.5:1 minimum, cibles tactiles 44×44px minimum, labels ARIA sur tout élément purement visuel, compatibilité VoiceOver/TalkBack
UX-DR8: Responsive — page de jonction web anonyme fonctionnelle sur mobile et desktop (breakpoint simple <768px/≥768px), layout à une colonne
UX-DR9: Pattern d'interaction voice-first — toute confirmation/erreur annoncée vocalement en premier, affichage visuel secondaire seulement ; récupération gracieuse par nouvelle demande polie en cas d'incompréhension
UX-DR10: Écran d'onboarding — vérification téléphone (OTP), friction minimale, aucune question superflue
UX-DR11: Écran "Home"/invitation — capture de la commande vocale "invite [nom]", confirmation vocale + bandeau visuel
UX-DR12: Écran de session — Indicateur d'Onde Vocale actif, sortie par commande vocale ("Je quitte le Salon")
UX-DR13: Écran d'historique — liste simple des sessions passées et partenaires (pas de fil de messages)

### FR Coverage Map

```
FR1: Epic 2 - Création de session (document/URL)
FR2: Epic 2 - Invitation vocale (ami Salon ou contact)
FR3: Epic 2 - Ajout de source en cours de session
FR4: Epic 3 - Jonction web sans compte
FR5: Epic 3 - Lien à usage unique
FR6: Epic 2 - Lecture à voix haute
FR7: Epic 2 - Discussion sans lecture préalable
FR8: Epic 2 - Contraste d'autres sources
FR9: Epic 2 - Parole par pauses naturelles
FR10: Epic 2 - Compréhension langage naturel, toujours à l'écoute
FR11: Epic 2 - Ajustement vocal de la fréquence d'intervention
FR12: Epic 2 - Détection automatique de langue
FR13: Epic 2 - Affichage dans la langue détectée
FR14: Epic 2 - Expression dans sa propre langue
FR15: Epic 2 - Traduction et lecture dans la langue du destinataire
FR16: Epic 2 - Interprétation simultanée sans interrompre
FR17: Epic 2 - Pas d'écho audio
FR18: Epic 1 - Compte + vérification téléphone
FR19: Epic 4 - Heure d'essai gratuite à vie
FR20: Epic 4 - Métrage précis minute/seconde
FR21: Epic 4 - Ajout de méthode de paiement Stripe
FR22: Epic 4 - Facturation 5$/heure au prorata
FR23: Epic 4 - Invité jamais facturé
FR24: Epic 2 - Sortie vocale de session
FR25: Epic 3 - Sortie par fermeture app/navigateur
FR26: Epic 2 - Question de satisfaction
FR27: Epic 3 - Satisfaction pour invité anonyme
FR28: Epic 5 - Consultation de l'historique
FR29: Epic 5 - Nouvelle session avec partenaire précédent
FR30: Epic 3 - SMS automatique avec lien d'installation
FR31: Epic 3 - Installation et conversion en utilisateur inscrit
```

## Epic List

### Epic 1: Inscription & Identité
Un nouvel utilisateur peut créer un compte Salon en vérifiant son numéro de téléphone — condition préalable à toute utilisation du produit en tant qu'hôte.
**FRs covered:** FR18
**Note d'implémentation :** Story 1.1 = initialisation des deux projets (`lk app create --template agent-starter-python`, `npx create-expo-app`) — première story technique avant toute fonctionnalité utilisateur.

### Epic 2: Session de Discussion Vocale
Un hôte inscrit peut créer une session à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de session.
**FRs covered:** FR1, FR2, FR3, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR24, FR26

### Epic 3: Accès Invité Sans Installation
Un contact téléphone sans l'application peut rejoindre une session Salon anonymement depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.
**FRs covered:** FR4, FR5, FR25, FR27, FR30, FR31

### Epic 4: Essai Gratuit & Facturation
Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.
**FRs covered:** FR19, FR20, FR21, FR22, FR23

### Epic 5: Historique & Reconnexion
Un utilisateur inscrit peut consulter ses sessions passées et démarrer rapidement une nouvelle session avec un partenaire déjà connu.
**FRs covered:** FR28, FR29
