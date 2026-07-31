# salon — Project Context

## Project Goals

Salon est une application mobile native (iOS/Android) voice-first qui permet à deux personnes de discuter en temps réel d'un document ou d'une actualité (via URL), animée par l'agent vocal de xAI. Elle cible les cols blancs — en particulier les professionnels techniques comme les ingénieurs — qui doivent se tenir à jour dans un domaine en évolution rapide mais manquent de temps et de format adapté (les sources actuelles sont asynchrones et visuelles, donc inutilisables en conduisant). Salon transforme le trajet quotidien en un moment d'apprentissage social et actif : aucune lecture préalable n'est requise, l'agent lit et anime la discussion, traduit en temps réel (anglais comme langue pivot), et une simple question de satisfaction en fin de session capture le ressenti des participants.

### What Makes This Special

L'intégration exclusive et profonde avec la stack native xAI (Voice Realtime API, Files API, Collections API) crée un avantage de premier arrivant sur un problème que personne d'autre n'attaque avec cette combinaison précise : discussion de groupe vocale, en direct, assistée par IA, mesurable. Le modèle "classe multilingue synchronisée" — micro-requêtes personnelles (relecture, clarification) autorisées individuellement, macro-navigation toujours collective — résout une tension UX que ni les réseaux sociaux asynchrones (LinkedIn, Facebook) ni les outils IA solo (ChatGPT) n'ont eu à résoudre.

## Success Metrics

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

## Scope Boundaries

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

## Non-Functional Requirements

### Performance

Aucun seuil de latence formel n'est fixé pour le MVP. La latence du pipeline voix→traduction→voix sera validée empiriquement une fois l'usage réel commencé, plutôt que contrainte par une cible arbitraire dès le départ.

### Security

Salon ne conserve aucun transcript de session pour le MVP — le contenu parlé et traduit (y compris le pivot anglais) reste éphémère, traité en mémoire pendant la session sans persistance. Les liens d'invitation à usage unique expirent après la première connexion. Les méthodes de paiement sont gérées entièrement via Stripe (tokenisation) — Salon ne stocke aucune donnée de carte de crédit directement.

### Integration

En cas d'indisponibilité de xAI, de LiveKit, ou de Stripe au moment de rejoindre ou démarrer une session, le système doit présenter un message d'erreur clair à l'utilisateur plutôt qu'un échec silencieux ou un comportement indéfini.

## Design Guidelines

Foundation

### 1.1 Design System Choice

Système établi : React Native Paper (implémentation Material Design 3 pour React Native) — un seul codebase Expo pour iOS/Android, sans design system custom.

### Rationale for Selection

L'UI de Salon est volontairement minimale (vérification téléphone, confirmation d'invitation, question de satisfaction, historique léger). La différenciation du produit vient de la voix, pas du visuel — investir dans un design system custom serait un mauvais usage du temps limité d'un solopreneur. Un système établi apporte accessibilité intégrée et rapidité de développement.

### Implementation Approach

React Native via Expo, avec React Native Paper pour les composants Material 3 — un seul codebase TypeScript pour iOS et Android, déployé via Expo Application Services (EAS Build/Submit).

### Customization Strategy

Personnalisation minimale : accent de couleur de marque et typographie seulement. Aucune bibliothèque de composants custom nécessaire vu le nombre restreint d'écrans.
