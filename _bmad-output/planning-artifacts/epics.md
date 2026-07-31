---
stepsCompleted: [1, 2, 3, 4]
status: 'complete'
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/architecture.md', '_bmad-output/planning-artifacts/ux-design-specification.md']
---

# salon - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for salon, decomposing the requirements from the PRD, UX Design, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Un hôte peut créer une session en téléversant un document, en fournissant une URL de nouvelle comme source, ou sans aucune source — dans ce dernier cas, l'agent ouvre la session en demandant aux participants de quoi ils souhaitent discuter
FR2: Un hôte peut inviter exactement un invité à une session par commande vocale, en nommant un ami enregistré dans Salon (livraison par notification in-app) ou un contact par son adresse courriel (livraison du lien de jonction par courriel)
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
FR18: Un nouvel utilisateur doit créer un compte avec une adresse courriel vérifiée par code à usage unique avant de pouvoir utiliser Salon pour la première fois ; le numéro de téléphone devient facultatif et n'est requis que pour être invité par SMS ou pour rattacher une participation antérieure en tant qu'invité anonyme
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
FR30: Un invité anonyme reçoit automatiquement un courriel avec un lien d'installation de l'application native une fois sa session terminée
FR31: Un invité anonyme peut installer l'application native via ce lien et continuer à utiliser Salon en tant qu'utilisateur inscrit

### NonFunctional Requirements

NFR1: Performance — Aucun seuil de latence formel n'est fixé pour le MVP ; la latence du pipeline voix→traduction→voix sera validée empiriquement une fois l'usage réel commencé.
NFR2: Security — Salon ne conserve aucun transcript de session pour le MVP (traitement éphémère en mémoire) ; les liens d'invitation à usage unique expirent après la première connexion ; les méthodes de paiement sont gérées entièrement via Stripe (tokenisation).
NFR3: Integration — En cas d'indisponibilité de xAI, LiveKit, ou Stripe, le système doit présenter un message d'erreur clair plutôt qu'un échec silencieux.

### Additional Requirements

- Starter template worker d'agent : `lk app create --template agent-starter-python` + `uv add "livekit-agents[xai,silero,turn-detector]"` (Story 1.1)
- Starter template mobile : `npx create-expo-app` avec Expo Development Build (pas Expo Go) requis dès le départ pour supporter `@livekit/react-native` (Story 1.2)
- Infrastructure AWS : Lambda + API Gateway (API REST), ECS Fargate (worker d'agent xAI), Aurora Serverless v2 PostgreSQL, S3+CloudFront (page de jonction web), Secrets Manager (clés API), CloudWatch Logs (monitoring), GitHub Actions (CI/CD)
- Intégrations tierces : xAI (plugin `livekit-agents[xai]`), LiveKit Cloud (managé, pas d'auto-hébergement), Stripe (paiement), AWS SES (OTP et invitations par courriel)
- Base de données : schéma relationnel (`users`, `sessions`, `friends`, `billing_events`), migrations Alembic
- Authentification : OTP par courriel (AWS SES), JWT à courte durée pour utilisateurs inscrits, token à usage unique pour jonction anonyme
- Métrage de facturation : heartbeat périodique (30s) du worker vers l'API + callback final, pour fiabilité en cas de déconnexion
- Règle métier "ami Salon" : un contact ne devient un ami Salon (livraison in-app) que s'il s'est lui-même inscrit avec une adresse courriel vérifiée ; sinon, joignable uniquement par SMS
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
FR1: Epic 2 - Création de session (document, URL, ou sans source)
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
FR18: Epic 1 - Compte + vérification courriel
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

## Epic 1: Inscription & Identité

Un nouvel utilisateur peut créer un compte Salon en vérifiant son numéro de téléphone — condition préalable à toute utilisation du produit en tant qu'hôte.

### Story 1.1: Initialisation des Projets

As a développeur,
I want les projets agent et mobile initialisés depuis les starters officiels,
So that je peux commencer à construire des fonctionnalités sur une fondation cohérente.

**Acceptance Criteria:**

**Given** aucun projet n'existe encore
**When** j'exécute `lk app create --template agent-starter-python` et `uv add "livekit-agents[xai,silero,turn-detector]"`
**Then** le worker d'agent est scaffoldé avec Dockerfile, config `livekit.toml`, et `.env.example`

**And Given** aucun projet mobile n'existe encore
**When** j'exécute `npx create-expo-app` et configure un Expo Development Build
**Then** le projet mobile React Native est prêt à être développé et testé sur un appareil réel

### Story 1.2: Vérification Téléphone par OTP

As a nouvel utilisateur,
I want créer un compte en vérifiant mon numéro de téléphone,
So that je peux utiliser Salon pour la première fois. (FR18)

**Acceptance Criteria:**

**Given** un nouvel utilisateur ouvre l'application pour la première fois
**When** il entre son numéro de téléphone
**Then** un code OTP est envoyé via AWS SNS et une entrée `users` est préparée

**And Given** l'utilisateur entre le code OTP reçu
**When** le code est valide et non expiré
**Then** le compte est créé, un JWT est émis, et l'utilisateur peut utiliser Salon

**And Given** l'utilisateur entre un code invalide ou expiré
**When** la vérification échoue
**Then** l'agent l'informe vocalement de l'erreur et propose de renvoyer un nouveau code

### Story 1.3: Écran d'Inscription

As a nouvel utilisateur,
I want un écran d'inscription clair et rapide,
So that la friction avant ma première session soit minimale. (UX-DR1, UX-DR6, UX-DR10, UX-DR7)

**Acceptance Criteria:**

**Given** l'écran d'inscription est affiché
**When** il se charge
**Then** il utilise la palette "Salon Parisien" (bourgogne, or, ivoire) et l'icône télégraphique custom plutôt qu'une icône téléphone générique

**And Given** un utilisateur avec un lecteur d'écran actif
**When** il navigue l'écran
**Then** tous les champs et boutons respectent le contraste WCAG AA et les cibles tactiles 44×44px minimum

## Epic 2: Session de Discussion Vocale

Un hôte inscrit peut créer une session à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de session.

### Story 2.1: Création de Session avec Document/URL

As a hôte inscrit,
I want créer une session à partir d'un document téléversé ou d'une URL de nouvelle,
So that je peux démarrer une discussion sur ce contenu. (FR1)

**Acceptance Criteria:**

**Given** un hôte inscrit et authentifié
**When** il téléverse un document ou fournit une URL
**Then** une session est créée avec ce contenu comme source, et une salle LiveKit est provisionnée

### Story 2.2: Invitation Vocale d'un Ami ou Contact

As a hôte,
I want inviter un ami Salon ou un contact téléphone par simple commande vocale,
So that je n'ai jamais à manipuler de lien ou de menu. (FR2)

**Acceptance Criteria:**

**Given** une session active et un hôte qui dit "invite [nom]"
**When** le nom correspond à un ami Salon déjà enregistré
**Then** une notification in-app est envoyée à cet ami

**And Given** le nom correspond à un contact du téléphone non-inscrit
**When** l'hôte prononce l'invitation
**Then** un SMS est envoyé à ce contact avec un lien de session

**And Given** l'agent ne comprend pas le nom mentionné
**When** la résolution échoue
**Then** l'agent redemande poliment à voix haute

### Story 2.3: Ajout de Source en Cours de Session

As a hôte,
I want ajouter un document ou une URL supplémentaire pendant une session active,
So that la discussion peut évoluer sans devoir en créer une nouvelle. (FR3)

**Acceptance Criteria:**

**Given** une session active dont l'hôte est participant
**When** l'hôte ajoute un nouveau document ou une URL
**Then** la nouvelle source est associée à la session et disponible pour l'agent

### Story 2.4: Lecture à Voix Haute et Facilitation Sans Lecture Préalable

As a participant,
I want que l'agent lise et anime le contenu à voix haute,
So that je peux discuter d'un document sans l'avoir lu au préalable. (FR6, FR7)

**Acceptance Criteria:**

**Given** une session démarrée avec une source de contenu
**When** les participants rejoignent
**Then** l'agent lit le contenu à voix haute et pose des questions pour engager la discussion

**And Given** un participant n'a pas consulté le document au préalable
**When** il participe à la discussion
**Then** il peut suivre et contribuer normalement grâce à la lecture de l'agent

### Story 2.5: Contraste avec d'Autres Sources

As a participant,
I want que l'agent introduise des informations contrastantes d'autres sources,
So that la discussion gagne en profondeur. (FR8)

**Acceptance Criteria:**

**Given** une discussion en cours sur un sujet donné
**When** l'agent identifie une occasion de contraste pertinent
**Then** il introduit l'information contrastante à voix haute, en citant sa source

### Story 2.6: Conversation Naturelle Sans Mot-Clé de Réveil

As a participant,
I want parler naturellement sans mot-clé de réveil ni mécanisme formel de demande de parole,
So that la conversation reste fluide comme entre humains. (FR9, FR10)

**Acceptance Criteria:**

**Given** une session active
**When** un participant commence à parler
**Then** l'agent le comprend sans qu'un mot-clé de réveil soit prononcé

**And Given** deux participants parlent en alternance
**When** une pause naturelle survient
**Then** l'agent ou l'autre participant peut prendre la parole sans mécanisme explicite de demande

### Story 2.7: Ajustement Vocal de la Fréquence d'Intervention

As a participant,
I want ajuster à voix haute la fréquence d'intervention de l'agent,
So that je garde le contrôle du rythme de la conversation. (FR11)

**Acceptance Criteria:**

**Given** une session avec des participants de même langue
**When** aucun ajustement n'est demandé
**Then** l'agent intervient au maximum une fois par minute, de façon succincte

**And Given** un participant dit "parle moins souvent" ou "interviens plus"
**When** la demande est reçue
**Then** l'agent ajuste sa fréquence d'intervention en conséquence pour le reste de la session

### Story 2.8: Détection de Langue et Expression Multilingue

As a participant,
I want m'exprimer dans ma propre langue sans configuration,
So that la barrière linguistique ne limite jamais la conversation. (FR12, FR14)

**Acceptance Criteria:**

**Given** un participant rejoint une session
**When** il commence à parler
**Then** le système détecte automatiquement sa langue sans sélection manuelle

**And Given** la langue est détectée
**When** le participant continue de parler
**Then** il peut s'exprimer entièrement dans cette langue tout au long de la session

### Story 2.9: Affichage Visuel dans la Langue Détectée

As a utilisateur,
I want que les écrans de l'application s'affichent dans ma langue vocale détectée,
So that je n'aie jamais besoin de configurer manuellement une langue d'interface. (FR13)

**Acceptance Criteria:**

**Given** la langue vocale d'un utilisateur est détectée
**When** un écran de l'application s'affiche
**Then** le texte visuel est présenté dans cette langue

### Story 2.10: Traduction Simultanée en Direct Sans Écho

As a participant,
I want entendre une traduction en direct dans ma langue pendant que l'autre continue de parler,
So that la conversation reste fluide malgré la barrière linguistique. (FR15, FR16, FR17)

**Acceptance Criteria:**

**Given** deux participants parlant des langues différentes
**When** l'un d'eux parle
**Then** son discours est traduit et lu à voix haute au destinataire dans sa propre langue

**And Given** la traduction est en cours de lecture pour un destinataire
**When** l'interlocuteur d'origine continue de parler
**Then** la traduction ne l'interrompt pas et le microphone du destinataire est temporairement coupé pour éviter tout écho sur le flux partagé

### Story 2.11: Sortie Vocale de Session

As a participant,
I want quitter une session en disant "Je quitte le Salon" dans ma propre langue,
So that je peux terminer proprement sans manipuler l'écran. (FR24)

**Acceptance Criteria:**

**Given** une session active
**When** un participant prononce la commande de sortie dans sa langue
**Then** la session se termine pour ce participant

### Story 2.12: Question de Satisfaction de Fin de Session

As a participant,
I want qu'on me demande vocalement si la conversation a été agréable,
So that mon ressenti soit capturé sans effort. (FR26)

**Acceptance Criteria:**

**Given** un participant vient de prononcer la commande de sortie
**When** la session se termine pour lui
**Then** l'agent lui pose immédiatement, à voix haute, la question "Est-ce que votre conversation dans Salon a été une belle expérience ?"

## Epic 3: Accès Invité Sans Installation

Un contact téléphone sans l'application peut rejoindre une session Salon anonymement depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.

### Story 3.1: Jonction Web Anonyme via Lien à Usage Unique

As a contact téléphone invité sans l'application,
I want rejoindre une session directement depuis mon navigateur,
So that je peux participer sans créer de compte ni installer quoi que ce soit. (FR4, FR5, UX-DR5, UX-DR8)

**Acceptance Criteria:**

**Given** un hôte invite un contact téléphone sans l'application Salon
**When** le contact reçoit le SMS et clique le lien
**Then** il rejoint la session anonymement depuis son navigateur, sans créer de compte

**And Given** un lien de session a déjà été utilisé une fois
**When** quelqu'un tente de le réutiliser
**Then** l'accès est refusé

**And Given** la page de jonction s'affiche
**When** elle se charge sur mobile ou desktop
**Then** elle affiche le badge "Sans Installation" et s'adapte correctement aux deux formats

### Story 3.2: Sortie de Session par Fermeture

As a invité anonyme,
I want pouvoir simplement fermer mon navigateur pour quitter,
So that je n'aie pas besoin de connaître une commande vocale spécifique. (FR25)

**Acceptance Criteria:**

**Given** un invité anonyme dans une session active
**When** il ferme l'application ou l'onglet du navigateur
**Then** il quitte la session proprement

### Story 3.3: Question de Satisfaction pour Invité Anonyme

As a invité anonyme,
I want répondre à la question de satisfaction sans avoir de compte,
So that mon ressenti compte même sans inscription. (FR27)

**Acceptance Criteria:**

**Given** un invité anonyme quitte une session
**When** l'agent pose la question de satisfaction
**Then** l'invité peut y répondre vocalement sans que la réponse soit liée à un profil persistant

### Story 3.4: SMS de Suivi avec Lien d'Installation

As a invité anonyme,
I want recevoir un SMS avec un lien d'installation après ma session,
So that je puisse facilement installer l'application si l'expérience m'a plu. (FR30)

**Acceptance Criteria:**

**Given** un invité anonyme termine sa première session
**When** la session se termine
**Then** il reçoit automatiquement un SMS avec un lien d'installation de l'application

### Story 3.5: Conversion en Utilisateur Inscrit

As a invité anonyme ayant reçu le lien d'installation,
I want installer l'application et continuer à utiliser Salon en tant qu'utilisateur inscrit,
So that je conserve mon historique pour mes futures sessions. (FR31)

**Acceptance Criteria:**

**Given** un invité anonyme a reçu le SMS d'installation
**When** il installe l'application et complète la vérification téléphone
**Then** il devient un utilisateur inscrit à part entière

## Epic 4: Essai Gratuit & Facturation

Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.

### Story 4.1: Heure d'Essai Gratuite à Vie par Hôte

As a hôte,
I want bénéficier d'une heure d'essai gratuite cumulée sur toutes mes sessions,
So that je peux essayer Salon avant de payer. (FR19)

**Acceptance Criteria:**

**Given** un hôte utilise Salon pour la première fois
**When** il démarre des sessions
**Then** son temps cumulé en tant qu'hôte est suivi contre un plafond d'une heure à vie

**And Given** un invité participe à une session
**When** le temps est comptabilisé
**Then** son temps à lui n'est jamais compté contre l'essai gratuit de qui que ce soit (FR23)

### Story 4.2: Métrage Précis du Temps de Conversation

As a système,
I want comptabiliser le temps de conversation à la minute et à la seconde près,
So that l'essai gratuit et la facturation soient exacts. (FR20)

**Acceptance Criteria:**

**Given** une session active avec un hôte
**When** la conversation se déroule
**Then** le worker d'agent envoie un heartbeat de métrage toutes les 30 secondes à l'API

**And Given** une déconnexion brutale survient
**When** la session se termine de façon inattendue
**Then** le métrage déjà transmis via heartbeat n'est pas perdu

### Story 4.3: Ajout de Méthode de Paiement Stripe

As a hôte dont l'heure gratuite est épuisée,
I want ajouter une méthode de paiement,
So that je peux continuer à utiliser Salon en tant qu'hôte. (FR21)

**Acceptance Criteria:**

**Given** un hôte a épuisé son heure d'essai gratuite
**When** il tente de démarrer une nouvelle session en tant qu'hôte
**Then** il doit ajouter une méthode de paiement via Stripe avant de continuer

### Story 4.4: Facturation à l'Heure Après l'Essai Gratuit

As a hôte avec une méthode de paiement enregistrée,
I want être facturé au prorata de mon temps d'utilisation au-delà de l'essai gratuit,
So that je paie seulement ce que j'utilise. (FR22, FR23)

**Acceptance Criteria:**

**Given** un hôte a dépassé son heure gratuite et a une méthode de paiement
**When** il utilise Salon en tant qu'hôte
**Then** il est facturé 5 USD par heure, au prorata de la seconde

**And Given** un invité participe à une session facturée
**When** la facturation est calculée
**Then** l'invité n'est jamais facturé, peu importe la durée

## Epic 5: Historique & Reconnexion

Un utilisateur inscrit peut consulter ses sessions passées et démarrer rapidement une nouvelle session avec un partenaire déjà connu.

### Story 5.1: Consultation de l'Historique de Sessions

As a utilisateur inscrit,
I want consulter mes sessions passées et mes partenaires de discussion,
So that je peux me souvenir de mes conversations précédentes. (FR28, UX-DR13)

**Acceptance Criteria:**

**Given** un utilisateur inscrit avec au moins une session passée
**When** il consulte son historique
**Then** il voit une liste simple de ses sessions passées et partenaires, sans fil de messages détaillé

### Story 5.2: Nouvelle Session avec un Partenaire Précédent

As a utilisateur inscrit,
I want démarrer rapidement une nouvelle session avec un partenaire déjà connu,
So that je n'aie pas à répéter le processus d'invitation complet. (FR29)

**Acceptance Criteria:**

**Given** un utilisateur consulte son historique
**When** il sélectionne un partenaire précédent pour une nouvelle session
**Then** une nouvelle session démarre avec ce partenaire déjà identifié
