---
stepsCompleted: [step-01-init, step-02-discovery, step-02b-vision, step-02c-executive-summary, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish]
inputDocuments: ['_bmad-output/planning-artifacts/product-brief-salon-2026-07-25.md']
workflowType: 'prd'
classification:
  projectType: 'mobile_app'
  domain: 'general'
  complexity: 'low'
  projectContext: 'greenfield'
  futureVision: 'extension to Android/iOS tablets and web, since an invited guest may join from a desktop computer'
scopeNotes:
  - 'Content sources include uploaded documents AND news URLs (in addition to files), for both MVP (1-on-1) and post-MVP (up to 50 participants) tiers'
architectureNotes:
  - 'Separate backend from day one (thin orchestrator over the native xAI stack) rather than logic embedded in the mobile client'
  - 'MVP turn-taking is implicit/silence-based (2 participants); MCP server for explicit in-session controls (hand-raise, host override to mute the agent and grant the floor) is deferred post-MVP, along with private/public messaging'
  - 'Translation pipeline uses English as the pivot language: speech in any language is transcribed and translated to English in the backend, then translated and read aloud in each participant''s own language; skipped when the detected language is already English'
  - 'Live/overlapping interpretation: translation is read aloud while the other participant keeps speaking (simultaneous-interpretation style), with that participant''s mic muted during translation playback to avoid audio feedback on the shared stream'
---

# Product Requirements Document - salon

**Author:** BMad
**Date:** 2026-07-25

## Executive Summary

Salon est une application mobile native (iOS/Android) voice-first qui permet à deux personnes de discuter en temps réel d'un document ou d'une actualité (via URL), animée par l'agent vocal de xAI. Elle cible les cols blancs — en particulier les professionnels techniques comme les ingénieurs — qui doivent se tenir à jour dans un domaine en évolution rapide mais manquent de temps et de format adapté (les sources actuelles sont asynchrones et visuelles, donc inutilisables en conduisant). Salon transforme le trajet quotidien en un moment d'apprentissage social et actif : aucune lecture préalable n'est requise, l'agent lit et anime la discussion, traduit en temps réel (anglais comme langue pivot), et une simple question de satisfaction en fin de session capture le ressenti des participants.

### What Makes This Special

L'intégration exclusive et profonde avec la stack native xAI (Voice Realtime API, Files API, Collections API) crée un avantage de premier arrivant sur un problème que personne d'autre n'attaque avec cette combinaison précise : discussion de groupe vocale, en direct, assistée par IA, mesurable. Le modèle "classe multilingue synchronisée" — micro-requêtes personnelles (relecture, clarification) autorisées individuellement, macro-navigation toujours collective — résout une tension UX que ni les réseaux sociaux asynchrones (LinkedIn, Facebook) ni les outils IA solo (ChatGPT) n'ont eu à résoudre.

## Project Classification

**Type de projet :** Application mobile native (iOS/Android) pour le MVP ; extension prévue vers tablette et web pour supporter des invités sur ordinateur.
**Domaine :** Général (grand public, apprentissage informel entre pairs — pas de conformité edtech formelle requise).
**Complexité :** Faible/standard — aucune exigence réglementaire spécifique identifiée pour le scope MVP.
**Contexte projet :** Greenfield — nouveau produit, aucune base de code existante.

## Success Criteria

### User Success

Seb et Jean-Samuel savent que Salon fonctionne quand ils ressortent d'un trajet en ayant appris quelque chose de concret tout en s'étant diverti — signal renforcé quand cet apprentissage devient une routine plutôt qu'une nouveauté ponctuelle.

### Business Success

Aucune cible chiffrée fixée avant le lancement pour la croissance/engagement à long terme — ces métriques (segmentées par démographie, géographie, éducation, salaire, langue, occupation) établiront leurs propres lignes de base dès le lancement. Seuil minimal de signal de vie pour le premier mois : **20 vraies sessions organiques** (excluant tests et famille). Signal de validation à plus long terme : un **taux d'invitation d'amis comparable aux standards des réseaux sociaux dominants chez les cols blancs** (Facebook, LinkedIn).

### Technical Success

Pour le MVP, l'architecture doit minimiser le coût d'utilisation des services xAI : **un seul Voice Agent partagé sert tous les utilisateurs d'une session, à tour de rôle**, sur un flux audio unique et synchrone (pas de canaux personnalisés par utilisateur). Si les deux participants parlent des langues différentes, chaque message est traduit vers l'anglais (langue pivot) puis lu dans les deux langues sur ce même flux partagé. Le backend reste un orchestrateur mince au-dessus de la stack xAI native (Voice Realtime, Files, Collections), sans logique de traduction ou de synthèse vocale maison.

### Measurable Outcomes

- Taux de réponses positives à la question de satisfaction de fin de session ("Est-ce que votre conversation dans Salon a été une belle expérience ?")
- Minimum 20 vraies sessions organiques au premier mois
- Taux d'invitation d'amis approchant la parité avec les réseaux sociaux dominants chez les cols blancs
- Fréquence d'usage, minutes/session et engagement mesurés dès le lancement comme baseline, ventilés par segment

## Product Scope

### MVP Strategy & Philosophy

MVP de validation de problème (problem-solving MVP) : la question centrale à valider est si les gens veulent vraiment discuter vocalement d'un document ou d'une actualité, à deux, avec l'aide d'une IA — et sont prêts à payer pour ça au-delà d'un essai gratuit. Ressources : solopreneur, sans équipe — ce qui renforce la discipline de garder le MVP minimal (backend mince, pas de serveur MCP, pas de canaux personnalisés).

### MVP - Minimum Viable Product

- Application mobile native (iOS/Android), 1-à-1, un seul Voice Agent partagé par session (flux audio unique, synchrone)
- Modèle d'affaires : 1 heure d'essai gratuit à vie par hôte (cumulative sur toutes ses sessions), puis 5 USD/heure facturés à l'hôte uniquement — l'invité ne paie jamais
- Création de compte avec numéro de téléphone vérifié dès le premier lancement ; méthode de paiement (Stripe) demandée seulement une fois l'heure d'essai gratuite épuisée
- Sources de contenu : documents téléversés ET URLs de nouvelles
- Upload réservé à l'hôte, possible avant et pendant la session
- Backend séparé, orchestrateur mince sur la stack xAI native (Voice Realtime, Files, Collections API)
- Pipeline de traduction avec l'anglais comme langue pivot (sauté si déjà anglais) ; si langues différentes, lecture dans les deux langues sur le flux partagé
- Ordre de parole automatique par silence (FIFO implicite) — à deux personnes, chacun prend la parole naturellement quand il y a un silence, sans mécanisme de contrôle explicite
- Détection automatique de la langue parlée, sans sélection manuelle
- Agent toujours à l'écoute, sans mot-clé de réveil, compréhension en langage naturel
- Question de satisfaction simple en fin de session ("Est-ce que votre conversation dans Salon a été une belle expérience ?"), déclenchée immédiatement après la commande de sortie
- Sortie de session par commande vocale ("Je quitte le Salon", dans sa propre langue) ou en fermant l'application/le navigateur
- Invitation déclenchée vocalement par l'hôte, vers un ami enregistré dans Salon ou un contact du téléphone ; livraison par SMS (contact téléphone) ou notification in-app (ami Salon)

### Growth Features (Post-MVP)

- Tier institutionnel à grande échelle (jusqu'à 50 participants, courriel institutionnel, vérification d'âge déléguée à l'institution, tarification distincte du 1-à-1)
- Serveur MCP pour les contrôles de session explicites : lever la main, override de l'hôte (couper l'agent, céder la parole)
- Messagerie privée/publique en session
- File d'attente pondérée par temps de parole cumulé
- Canaux de traduction personnalisés par utilisateur (agent dédié plutôt que partagé)
- Bouton d'Urgence Humaine : détection de sujets sensibles et redirection vers une ressource d'aide humaine

### Vision (Future)

- Extension vers tablette (Android/iOS) et web, pour permettre à un invité de rejoindre depuis un ordinateur
- Positionnement élargi : le divertissement de prédilection des automobilistes fortunés

### Risk Mitigation Strategy

**Risque technique :** L'intégration LiveKit+xAI est le risque technique prioritaire à valider dès le MVP — le pipeline de traduction bilingue en temps réel est un risque secondaire à valider post-MVP, et l'orchestration MCP est reportée bien plus tard, une fois les fondations prouvées.

**Risque de marché :** Le risque principal n'est pas seulement "les gens n'utiliseront pas Salon" — c'est la possibilité que **le vrai problème ne soit pas "analyser un document à deux avec l'IA", mais que la traduction simultanée en temps réel soit, en elle-même, le produit gagnant**, indépendamment de la discussion de documents. Ce signal doit être surveillé activement pendant le MVP : si l'usage du pipeline de traduction dépasse l'intérêt pour la discussion de documents, un pivot de positionnement pourrait être justifié.

**Risque de ressources :** Solopreneur — le scope MVP doit rester réalisable par une seule personne ; toute fonctionnalité qui ajoute une complexité d'implémentation significative (MCP, canaux personnalisés, messagerie) est repoussée post-MVP par défaut.

**Risque accepté :** Sans Bouton d'Urgence Humaine, une conversation qui dérive vers un sujet sensible ou émotionnellement difficile n'a aucun garde-fou au MVP — l'agent continue la discussion normalement. Ce risque est explicitement accepté pour garder le scope minimal ; à réévaluer si l'usage réel révèle des cas problématiques.

## User Journeys

### Journey 1: Seb & Jean-Samuel — Le Trajet du Matin (Chemin Heureux)

**Scène d'ouverture :** Seb monte dans sa voiture un lundi matin, café en main, avec 25 minutes de route devant lui. Il a vu passer un article technique dense sur l'architecture des LLM la veille sur LinkedIn, sans avoir eu le temps de le lire. Plutôt que la radio, il ouvre Salon.

**Action montante :** Seb téléverse le lien de l'article dans l'app, puis dit simplement "invite Jean-Samuel." Jean-Samuel, déjà enregistré comme ami dans Salon, reçoit une notification in-app et rejoint la session depuis son propre trajet. L'agent vocal xAI accueille les deux, résume brièvement le sujet, puis commence à lire l'article à voix haute, en s'arrêtant pour poser des questions et inviter chacun à réagir.

**Climax :** À mi-parcours, l'agent détecte une divergence d'opinion entre Seb et Jean-Samuel sur une architecture technique — il relance la discussion en citant un contraste avec un autre article de référence, poussant les deux à approfondir leur raisonnement plutôt que de rester sur leur première impression.

**Résolution :** À l'arrivée au bureau, Seb dit "Je quitte le Salon" pour terminer proprement la session. L'agent lui pose aussitôt une dernière question simple — "Est-ce que votre conversation dans Salon a été une belle expérience ?" Seb répond oui sans hésiter : il a retenu bien plus que s'il avait écouté un podcast passivement, et se sent prêt à en parler intelligemment avec ses collègues.

### Journey 2: Seb & Jean-Samuel — L'Invité Sans l'Application (Cas Limite)

**Scène d'ouverture :** Un autre matin, Seb veut inviter Jean-Samuel à discuter d'une nouvelle qui vient de tomber sur X — mais Jean-Samuel n'a pas encore installé Salon.

**Action montante :** Seb l'invite quand même via SMS. Jean-Samuel reçoit un lien **à usage unique** vers un canal LiveKit (intégration xAI native — voir https://docs.livekit.io/agents/integrations/xai/). Il clique et rejoint **anonymement**, directement depuis son navigateur, sans créer de compte ni s'authentifier.

**Climax :** La session se déroule normalement — même agent, même orchestration, même qualité audio — malgré le fait que Jean-Samuel n'ait jamais ouvert l'application native et n'ait aucun compte.

**Résolution :** En fin de session, Jean-Samuel entend la même question de satisfaction, à laquelle il répond **anonymement** (non liée à un profil persistant). Impressionné par l'expérience, il ferme simplement son navigateur pour quitter, puis installe l'application native après coup pour ses futures conversations et pour retrouver son historique.

### Journey Requirements Summary

- **Invitation & provisioning :** génération d'un lien LiveKit **à usage unique** par session, déclenchée vocalement par l'hôte vers un ami Salon ou un contact du téléphone ; livré par SMS (contact téléphone) ou notification in-app (ami Salon)
- **Accès sans installation :** point d'entrée web minimal (page de jonction LiveKit dans le navigateur), rejoint **anonymement**, sans authentification — distinct d'une véritable version web de Salon (prévue plus tard)
- **Sécurité d'accès :** token à usage unique invalidé après la première connexion, pour empêcher qu'un lien intercepté/transféré laisse entrer un inconnu
- **Satisfaction anonyme :** la question de satisfaction de fin de session fonctionne aussi pour un invité non-authentifié, sans le lier à un profil persistant
- **Sortie de session :** un participant peut quitter à tout moment par commande vocale ("Je quitte le Salon", dans sa propre langue) ou en fermant l'application/le navigateur
- **Infrastructure temps réel :** LiveKit comme couche de transport audio/données en temps réel, avec l'agent xAI comme participant de la salle (room) ; ordre de parole géré naturellement par silence pour le MVP (serveur MCP pour contrôles explicites — lever la main, override hôte — reporté post-MVP)
- **Onboarding léger :** conversion post-session de l'invité web anonyme vers l'application native

## Innovation & Novel Patterns

### Detected Innovation Areas

- **Discussion de groupe voice-first orchestrée par IA** — aucune plateforme existante ne combine voix en direct, dynamique de groupe et augmentation de connaissance par IA dans un seul produit
- **Modèle "classe multilingue synchronisée"** — micro-requêtes personnelles (relecture, clarification) autorisées individuellement, macro-navigation toujours collective
- **Interprétation simultanée avec gestion de feedback** — la traduction est lue en direct pendant que l'interlocuteur continue de parler dans sa langue (comme un interprète de conférence), avec fermeture temporaire du micro du destinataire pendant la lecture de sa traduction pour éviter tout écho sur le flux audio partagé ; réduit la latence perçue par rapport à une traduction strictement séquentielle tour-par-tour
- **Bouton d'Urgence Humaine** (post-MVP) — l'IA reconnaît explicitement ses limites et redirige vers une aide humaine plutôt que de simuler une compétence qu'elle n'a pas
- **Accès anonyme à usage unique via LiveKit** — un invité peut rejoindre une conversation vocale IA sans compte ni installation, réduisant la friction d'acquisition à son minimum

### Market Context & Competitive Landscape

- **Discord/Clubhouse (audio de groupe) :** aucune augmentation de connaissance par IA, aucune orchestration structurée de la parole par un agent
- **ChatGPT/agents IA solo :** puissants individuellement, mais sans dynamique de groupe ni contraste social des idées
- **LinkedIn/Facebook :** interaction asynchrone et visuelle, aucune approche voice-first
- Aucun concurrent direct identifié combinant voix en direct + facilitation IA + groupe

### Validation Approach

- Seuil de signal de vie : 20 vraies sessions organiques au premier mois
- Taux de réponses positives à la question de satisfaction de fin de session comme signal de validation continu, session après session
- Taux d'invitation d'amis comme validation de l'effet de réseau et de la valeur perçue

### Risk Mitigation

- **Risque :** dépendance à la disponibilité/tarification de xAI et LiveKit → **Mitigation :** backend orchestrateur mince, limitant le coût de migration si nécessaire plus tard
- **Risque :** abus de l'accès anonyme malgré le lien à usage unique → **Mitigation :** expiration de token, limitation du taux de génération de liens par utilisateur

## Mobile App Specific Requirements

### Project-Type Overview

Salon MVP est une application mobile iOS/Android construite avec React Native via Expo (déployée avec Expo Application Services). L'intégration Android Auto / Apple CarPlay est planifiée mais explicitement hors scope MVP.

### Technical Architecture Considerations

Le client mobile reste volontairement mince : il gère l'audio (micro, haut-parleur), l'upload de documents/URLs, l'affichage minimal (invitations, question de satisfaction), et se connecte à une salle LiveKit provisionnée par le backend, où l'agent xAI est déjà présent comme participant.

### Platform Requirements

React Native via Expo pour iOS et Android — un seul codebase, déploiement géré par Expo Application Services (EAS Build, EAS Submit). Android Auto et Apple CarPlay sont prévus post-MVP, non requis au lancement.

### Device Permissions

Accès au microphone requis — c'est le cœur de l'expérience voice-first. Aucune autre permission d'appareil particulière identifiée pour le MVP.

### Offline Mode

Aucun mode hors ligne requis — Salon est fondamentalement un service temps réel en direct (session vocale via LiveKit + xAI). Sans connexion, il n'y a simplement pas de session possible.

### Push Notification Strategy

Les invitations et alertes de session passent par **SMS** plutôt que par des notifications push natives pour le MVP — cohérent avec le parcours d'invité anonyme (Journey 2) qui n'a pas nécessairement l'application installée. Les notifications push natives pourraient être envisagées plus tard pour les utilisateurs avec compte, mais ne sont pas requises au lancement.

### Store Compliance

Aucune préoccupation particulière de conformité App Store/Google Play identifiée pour le scope MVP.

### Implementation Considerations

Le backend gère le provisionnement des salles LiveKit et l'intégration xAI (Voice Realtime, Files, Collections API). Le client mobile natif reste concentré sur l'audio et l'UI minimale, ce qui simplifie sa portée et facilite l'extension future vers tablette et web (même backend, nouveau client).

## Functional Requirements

### Création de Session & Invitation

- FR1: Un hôte peut créer une session en téléversant un document ou en fournissant une URL de nouvelle comme source
- FR2: Un hôte peut inviter exactement un invité à une session par commande vocale, en nommant un ami enregistré dans Salon (livraison par notification in-app) ou un contact de son téléphone (livraison par SMS)
- FR3: Un hôte peut ajouter un document ou une URL supplémentaire à une session active, avant ou pendant celle-ci
- FR4: Un invité sans l'application mobile installée peut rejoindre une session directement depuis un navigateur web, sans créer de compte
- FR5: Un lien d'invitation ne peut être utilisé qu'une seule fois pour rejoindre une session

### Expérience de Discussion Vocale

- FR6: Un agent vocal lit à voix haute le contenu source de la session aux participants
- FR7: Les participants peuvent discuter du contenu source avec l'agent vocal et entre eux sans l'avoir lu ou consulté au préalable
- FR8: L'agent vocal introduit des informations contrastantes provenant d'autres sources pendant la discussion
- FR9: Les participants prennent la parole selon les pauses naturelles de la conversation, sans mécanisme formel de demande de parole
- FR10: L'agent vocal comprend le langage naturel des participants en tout temps, sans mot-clé de réveil requis
- FR11: Les participants peuvent ajuster vocalement la fréquence d'intervention proactive de l'agent (par défaut : une intervention succincte par minute lorsque les participants partagent la même langue ; plus fréquent lorsque l'agent traduit activement entre deux langues différentes)

### Traduction Multilingue

- FR12: Le système détecte automatiquement la langue parlée par chaque participant, sans sélection manuelle
- FR13: L'affichage visuel de l'application (les quelques écrans existants) est présenté dans la langue vocale détectée de l'utilisateur, sans sélection manuelle
- FR14: Les participants peuvent s'exprimer dans leur propre langue pendant une session
- FR15: Le contenu parlé est traduit et lu à voix haute à chaque participant dans sa propre langue, lorsque les participants parlent des langues différentes
- FR16: Le contenu traduit est lu à voix haute pendant que l'interlocuteur d'origine continue de parler, sans interrompre la conversation
- FR17: L'audio traduit destiné à un participant ne crée pas d'écho dans l'audio partagé de la session

**Langues supportées :** Anglais, arabe (Égypte, Arabie saoudite, Émirats), bengali, chinois simplifié, français, allemand, hindi, indonésien, italien, japonais, coréen, portugais (Brésil, Portugal), russe, espagnol (Mexique, Espagne), turc, vietnamien — selon les capacités documentées de l'API Speech-to-Speech de xAI ([docs.x.ai](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech#supported-languages)). D'autres langues peuvent fonctionner avec une précision variable. L'espagnol et le portugais nécessitent une variante régionale spécifique plutôt que le code de langue de base.

### Compte & Facturation

- FR18: Un nouvel utilisateur doit créer un compte avec un numéro de téléphone vérifié avant de pouvoir utiliser Salon pour la première fois
- FR19: Un hôte dispose d'une heure d'essai gratuite à vie, cumulée sur l'ensemble de ses sessions
- FR20: Le système comptabilise précisément, à la minute et à la seconde près, le temps de conversation cumulé de chaque hôte, pour déterminer le moment exact où l'heure d'essai gratuite est épuisée
- FR21: Un hôte doit ajouter une méthode de paiement (Stripe) une fois son heure d'essai gratuite épuisée, pour continuer à utiliser Salon en tant qu'hôte
- FR22: Un hôte est facturé 5 USD par heure (au prorata de la seconde) au-delà de son heure d'essai gratuite
- FR23: Un invité n'est jamais facturé, peu importe la durée de la session

### Retour d'Expérience & Fin de Session

- FR24: Un participant peut quitter une session à tout moment par une commande vocale dans sa propre langue
- FR25: Un participant peut quitter une session à tout moment en fermant l'application ou le navigateur
- FR26: L'agent vocal pose une question simple de satisfaction immédiatement après qu'un participant a prononcé la commande de sortie de session
- FR27: Un invité non-authentifié peut répondre à la question de satisfaction de fin de session sans posséder de compte persistant

### Compte & Historique

- FR28: Un utilisateur inscrit peut consulter son historique de sessions passées et de partenaires de discussion
- FR29: Un utilisateur inscrit peut démarrer une nouvelle session avec n'importe quel partenaire de discussion précédent
- FR30: Un invité anonyme reçoit automatiquement un SMS avec un lien d'installation de l'application native une fois sa session terminée
- FR31: Un invité anonyme peut installer l'application native via ce lien et continuer à utiliser Salon en tant qu'utilisateur inscrit

**Note :** Le Bouton d'Urgence Humaine (détection de sujets sensibles + redirection vers une ressource d'aide) est reporté post-MVP — voir Product Scope → Growth Features.

## Non-Functional Requirements

### Performance

Aucun seuil de latence formel n'est fixé pour le MVP. La latence du pipeline voix→traduction→voix sera validée empiriquement une fois l'usage réel commencé, plutôt que contrainte par une cible arbitraire dès le départ.

### Security

Salon ne conserve aucun transcript de session pour le MVP — le contenu parlé et traduit (y compris le pivot anglais) reste éphémère, traité en mémoire pendant la session sans persistance. Les liens d'invitation à usage unique expirent après la première connexion. Les méthodes de paiement sont gérées entièrement via Stripe (tokenisation) — Salon ne stocke aucune donnée de carte de crédit directement.

### Integration

En cas d'indisponibilité de xAI, de LiveKit, ou de Stripe au moment de rejoindre ou démarrer une session, le système doit présenter un message d'erreur clair à l'utilisateur plutôt qu'un échec silencieux ou un comportement indéfini.
