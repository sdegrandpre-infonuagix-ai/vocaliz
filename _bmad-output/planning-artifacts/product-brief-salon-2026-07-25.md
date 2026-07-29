---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments: ['_bmad-output/brainstorming/brainstorming-session-2026-07-25-10-40-26.md']
date: '2026-07-25'
author: 'BMad'
---

# Product Brief: salon

<!-- Content will be appended sequentially through collaborative workflow steps -->

## Executive Summary

Salon est une plateforme de discussion de groupe voice-first, propulsée par l'agent vocal de xAI, qui permet à des utilisateurs d'approfondir leur compréhension de documents (livres, articles scientifiques, documents techniques, sites web) en groupe, en temps réel — plutôt que seuls ou de façon asynchrone. Au moment où la maturité des agents vocaux IA converge avec une anxiété grandissante des cols blancs face à l'IA, Salon propose un contre-récit concret : utiliser l'IA pour élever l'intelligence collective humaine, pas pour la remplacer — et le prouver, mesurablement, à chaque session.

---

## Core Vision

### Problem Statement

Les moyens actuels d'acquérir des connaissances à partir de documents n'exploitent pas les outils modernes d'IA générative de façon interactive et collective. Les gens naviguent entre la lecture solo, les clubs de lecture traditionnels (contraints par l'horaire et le lieu), les forums de discussion textuels (asynchrones), les outils IA génériques comme ChatGPT (solo, sans dynamique de groupe), et les réseaux sociaux comme Facebook ou LinkedIn (asynchrones, sans expérience vocale). Aucune de ces options ne recrée le momentum d'une vraie discussion de groupe en temps réel, à moins d'être encore à l'école.

### Problem Impact

Sans solution, le risque est que l'intelligence artificielle diminue l'intelligence humaine collective au lieu de l'élever — les gens deviennent des consommateurs passifs de résumés IA plutôt que des penseurs actifs en dialogue. Cet enjeu est particulièrement aigu pour les cols blancs, qui ressentent déjà la pression compétitive de l'IA sur leur profession et ont besoin d'outils qui renforcent, plutôt qu'affaiblissent, leurs capacités cognitives et collaboratives.

### Why Existing Solutions Fall Short

- **Clubs de lecture traditionnels :** contraints par l'horaire et le lieu physique, pas de momentum continu
- **Forums textuels :** asynchrones, sans la richesse et la spontanéité d'une discussion vocale en direct
- **IA générative solo (ChatGPT) :** puissante individuellement, mais sans dynamique de groupe ni contraste social des idées
- **Réseaux sociaux (Facebook, LinkedIn) :** bons pour l'interaction asynchrone, mais aucune approche voice-first n'existe pour la discussion de documents

### Proposed Solution

Salon est une application voice-first où un hôte invite un participant à discuter d'un document ensemble, avec un agent vocal xAI qui lit à voix haute, facilite le survol interactif du contenu (**aucune connaissance préalable du document n'est requise**), traduit en temps réel pour que chacun parle sa propre langue, et sait reconnaître ses limites — en orientant vers une aide humaine réelle si la conversation touche un terrain émotionnellement sensible.

Pour rendre la valeur tangible et mesurable, chaque session est encadrée par un court échange vocal en 6 questions (5 fermées, 1 ouverte) avant et après la discussion — capturant à la fois le score de compréhension et la qualité de la réflexion, sans jamais prendre la forme d'un examen scolaire anxiogène.

### Key Differentiators

- **Effet de réseau de premier arrivant** sur le problème spécifique de l'apprentissage collectif voice-first assisté par IA, renforcé par une intégration xAI profonde difficile à répliquer rapidement
- **Intégration native profonde** avec la stack xAI (Voice Realtime API, Files API, Collections API)
- **Positionnement philosophique clair** : élever l'intelligence collective humaine plutôt que la remplacer — et le prouver avec une métrique de delta de compréhension pré/post-session
- **Voice-first par conception** — transforme des moments auparavant perdus (le trajet du matin) en moments d'apprentissage actif, sans préparation préalable requise
- **Bouton d'Urgence Humaine** — un principe de confiance et de sécurité intégré dès la conception

## Target Users

### Primary Users

**Seb — Ingénieur Logiciel en Quête Perpétuelle de Pertinence**

Seb est ingénieur logiciel, avec un trajet quotidien en voiture matin et soir. Le rythme effréné des technologies logicielles l'oblige à se tenir constamment à jour, mais il n'a jamais le temps de tout lire. Son réseau LinkedIn, composé en grande partie d'ingénieurs et d'architectes logiciels, lui offre du contenu de qualité — mais cette information est asynchrone et visuelle, donc totalement inutilisable pendant qu'il conduit.

**Vécu du problème :** Ne pas se tenir à jour en génie logiciel peut être catastrophique pour sa carrière — se faire dépasser, devenir moins employable. C'est une source de stress diffus mais réel. Trouver la discipline et le temps d'apprendre, surtout accompagné d'un ami, est difficile dans son quotidien chargé.

**Vision du succès :** Ressortir de chaque trajet avec Salon en ayant réellement appris quelque chose de concret — grâce à l'interaction entre l'agent vocal et son ami Jean-Samuel, ingénieur électrique qui suit de près les tendances en LLM. Le trajet devient une source de divertissement ET d'apprentissage, plutôt qu'un temps mort.

**Jean-Samuel — L'Ami Brillant et Complémentaire**

Jean-Samuel est ingénieur électrique, féru des tendances en IA/LLM. Il joue tantôt le rôle d'hôte, tantôt d'invité dans les sessions avec Seb — apportant une perspective complémentaire (électrique/IA vs logiciel) qui enrichit la discussion au-delà de ce qu'un seul expert ou l'agent seul pourrait offrir.

### Secondary Users

N/A pour le MVP — le produit reste volontairement centré sur la dyade hôte/invité (Seb et Jean-Samuel), cohérent avec le scope freemium 1-à-1. Aucun acteur tiers (employeur, institution) n'est considéré à ce stade ; cette dimension appartient au tier institutionnel post-MVP déjà identifié pendant le brainstorming.

### User Journey

**Découverte :** Par bouche-à-oreille entre ingénieurs, ou via un post sur LinkedIn/Facebook mentionnant Salon.

**Onboarding :** Typiquement, un ami invite l'autre à discuter 1 à 1 d'un document via un simple lien vers Salon, envoyé sur Messenger, LinkedIn ou WhatsApp — l'invitation circule dans les deux sens entre amis, ce n'est pas toujours le même qui est hôte. Celui qui initie la session téléverse le document (article technique, post approfondi, documentation).

**Usage principal :** Pendant ses trajets, Seb lance ou rejoint une session avec Jean-Samuel. L'agent vocal xAI lit et anime la discussion autour du document, sans qu'aucun des deux n'ait eu besoin de le lire à l'avance.

**Moment de succès :** Le quiz vocal de fin de session (5 questions fermées + 1 ouverte) révèle un gain de compréhension mesurable — la preuve concrète que le trajet vient de valoir plus qu'un podcast passif.

**Long terme :** Salon devient un rituel de trajet régulier pour Seb, qui entretient plusieurs relations 1-à-1 en parallèle — il peut réinviter Jean-Samuel sur un nouveau document, mais aussi inviter d'autres amis pour rediscuter d'un document déjà exploré (sous un angle d'expertise différent) ou pour explorer de tout nouveaux sujets. Le réseau d'amis de Seb devient une bibliothèque vivante de partenaires de discussion, chacun apportant sa spécialité.

## Success Metrics

**Perspective utilisateur :** Seb et Jean-Samuel savent que Salon fonctionne quand ils ressortent d'un trajet en ayant appris quelque chose de concret tout en s'étant diverti — et surtout quand cet apprentissage devient une routine plutôt qu'une nouveauté ponctuelle. Le signal le plus fort : ils reviennent, ils invitent d'autres amis, et leur delta de compréhension pré/post-session (via le quiz vocal) reste positif dans la durée.

**Comportements indicateurs de valeur :**

- Fréquence d'usage (sessions par semaine par utilisateur actif)
- Nombre d'amis invités au fil du temps (expansion du réseau de partenaires de discussion de chaque utilisateur)
- Sentiment recueilli par analyse des conversations (l'IA capte le ton et la satisfaction perçue, au-delà du score de quiz)

### Business Objectives

- **Croissance (3-12 mois) :** nombre de nouveaux utilisateurs actifs, avec suivi par segments démographiques, géographiques, niveau d'éducation, salaire, langues et occupation, pour identifier les segments à plus forte traction
- **Engagement :** nombre de sessions par semaine par utilisateur actif ; minutes moyennes par session (globalement et par segment)
- **Effet de réseau :** taux d'utilisateurs qui invitent au moins un nouvel ami par mois — signal clé de la traction virale sur laquelle repose l'avantage concurrentiel de premier arrivant

### Key Performance Indicators

- **Croissance :** X nouveaux utilisateurs actifs par mois, ventilés par segment démographique/géographique/éducation/salaire/langue/occupation
- **Engagement :** Y sessions moyennes par utilisateur actif par semaine
- **Profondeur d'usage :** Z minutes moyennes par session (par segment)
- **Viralité :** % d'utilisateurs invitant ≥1 nouvel ami par mois
- **Valeur d'apprentissage :** delta moyen de compréhension pré/post-session (score du quiz vocal en 5 questions fermées + 1 ouverte)
- **Satisfaction :** score de sentiment moyen dérivé de l'analyse des conversations

## MVP Scope

### Core Features

- Expérience voice-first intégrale (lecture à voix haute, survol interactif, aucune lecture préalable requise)
- Traduction simultanée multilingue (agent partagé)
- Modèle "classe multilingue synchronisée" (micro-requêtes personnelles vs macro-navigation)
- Freemium 1-à-1 (host + invité, agent partagé)
- Invitation par lien, tout canal (Messenger, LinkedIn, WhatsApp, courriel, SMS)
- Upload de documents réservé à l'hôte, avant et pendant la session
- Ordre de parole FIFO
- Bouton d'Urgence Humaine (version simplifiée : affichage de ressources, pas d'appel automatisé)
- Stack xAI natif exclusif (Voice Realtime API, Files API, Collections API), multilinguisme natif
- Quiz vocal pré/post-session (5 fermées + 1 ouverte) pour mesurer le delta de compréhension

### Out of Scope for MVP

- Tier payant/institutionnel (jusqu'à 50 participants, courriel institutionnel, vérification d'âge)
- File d'attente pondérée par temps de parole cumulé
- Canaux de traduction personnalisés par utilisateur
- Mémoire de personnalité trans-session
- Détecteur de stagnation
- Signalement discret de désengagement (détection de bluff)
- Attribution des sources en cas de contradiction
- Enregistrement des sessions
- Vérification d'âge en freemium

### MVP Success Criteria

Le signal de validation clé : un **taux d'invitation d'amis (viralité) comparable aux standards des réseaux sociaux dominants chez les cols blancs** (Facebook, LinkedIn). Si Salon atteint un coefficient viral de cet ordre, c'est la preuve que la valeur perçue par session est assez forte pour que les utilisateurs deviennent eux-mêmes le moteur de croissance — le signal qui justifie de continuer à investir au-delà du MVP.

### Future Vision

Si Salon connaît un succès retentissant, il devient **le divertissement de prédilection des automobilistes fortunés** — une catégorie de contenu audio premium à part entière pour les trajets, dépassant le seul cadre de l'outil d'apprentissage entre pairs cols blancs. Cette vision élargie ouvrirait naturellement la porte au tier institutionnel (jusqu'à 50 participants) déjà identifié, à de nouveaux types de documents et de marchés, et à un positionnement de marque premium autour du temps de trajet réinventé.
