---
version: 2
stepsCompleted: [step-01-init, step-02-discovery, step-02b-vision, step-02c-executive-summary, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-e-01-discovery, step-e-02-review, step-e-03-edit]
inputDocuments:
  - '_bmad-output/planning-artifacts/product-brief-salon-2026-07-25.md'
  - '_bmad-output/planning-artifacts/product-rule-voice-modes.md'
  - '_bmad-output/planning-artifacts/epics.md'
workflowType: 'prd'
lastEdited: '2026-08-08'
editHistory:
  - date: '2026-08-08'
    version: 2
    changes: 'Remise en phase avec PR-VOICE-001 et l''architecture multi-rooms. Ajout de FR32-FR70 et NFR4-NFR9. Suppression de FR9, FR17, FR19, FR23, FR27 ; remplacement de FR2 et FR22 ; amendement de NFR2 (Security). Réécriture de Technical Success, Product Scope, Journey 2, Innovation et Non-Functional Requirements.'
classification:
  projectType: 'mobile_app'
  domain: 'general'
  complexity: 'medium-high'
  complexityRationale: 'Conservation de conversations pendant un an, ciblage publicitaire géolocalisé, soldes prépayés portés au passif, droits d''accès et d''effacement — la classification « faible, aucune exigence réglementaire » de la version 1 ne tient plus.'
  projectContext: 'greenfield'
  futureVision: 'extension to Android/iOS tablets and web, since an invited guest may join from a desktop computer'
scopeNotes:
  - 'Content sources include uploaded documents AND news URLs (in addition to files)'
  - 'Participant cap is a configuration value, initialised to 3. Scaling to 50 is gated on measured load-test criteria, not on a release date.'
architectureNotes:
  - 'A Salon is a set of LiveKit rooms plus a per-Salon orchestrator. Each participant occupies their own room with a dedicated AI interpreter — there is no shared audio stream and no single shared agent.'
  - 'No pivot language. Each turn is journalled in the language it was spoken — the emitter is the original — and every translation derives directly from it, never from another translation. Three speakers in three languages produce three originals, and every rendering is one hop from the one it translates.'
  - 'Translations are cached per (turn, target language): several participants hearing or reading the same language share one translation.'
  - 'No translation happens when none is needed. A turn already in the listener''s language is rendered as spoken. In a monolingual Salon — the most common case, and the one in the flagship journey — the translation subsystem stays entirely idle: translation cost and latency scale with linguistic diversity, never with conversation volume.'
  - 'The interpreter is a port with three adapters (realtime speech-to-speech, STT+TTS base, scripted fake for load testing). The orchestrator references no provider directly.'
  - 'Speaking order is first-come-first-served on journal arrival time. There is no floor mechanism, no hand-raise, and no silence-based turn detection.'
  - 'Journals and cursors are persisted for one year from Salon creation, enabling crash recovery and proof of ad delivery. This supersedes the original ephemeral-in-memory commitment.'
  - 'Echo suppression is unnecessary by construction: no audio is shared between participants.'
---

# Product Requirements Document — Vocaliz

**Author:** BMad
**Date:** 2026-07-25 · **Révision 2 :** 2026-08-08

> **Version 2.** Cette révision remet le PRD en phase avec la règle produit PR-VOICE-001 et l'architecture multi-rooms définie dans [epics.md](epics.md). Les requirements supprimés ont été retirés du document ; leur trace demeure dans l'historique git.
>
> **Nommage :** le produit s'appelle **Vocaliz** (`vocaliz.net`). Le mot **Salon** désigne l'objet — une conversation entre participants.

## Executive Summary

Vocaliz est une application mobile native (iOS/Android) voice-first qui permet à un petit groupe — trois personnes au maximum — de discuter en temps réel d'un document ou d'une actualité, chacune assistée par son propre interprète IA. Elle cible les cols blancs, en particulier les professionnels techniques, qui doivent se tenir à jour dans un domaine en évolution rapide mais manquent de temps et de format adapté : les sources actuelles sont asynchrones et visuelles, donc inutilisables en conduisant. Vocaliz transforme le trajet quotidien en un moment d'apprentissage social et actif — aucune lecture préalable n'est requise, l'interprète lit et anime la discussion, traduit en direct, et une question de satisfaction en fin de Salon capture le ressenti.

Chaque participant occupe sa propre room avec un interprète dédié. Les interprètes s'échangent les tours de parole via un orchestrateur central — **chacun dans la langue où il a été prononcé** — puis restituent dans la langue de leur humain, en traduisant toujours **depuis l'original**. Personne n'entend l'audio brut d'un autre : la barrière linguistique disparaît, et l'écho avec elle.

Chacun **entend** dans sa langue et **lit** dans sa langue : l'interprète parle, les sous-titres écrivent, les deux canaux convergent vers la même personne.

Le produit est payant dès la première minute, en quatre paliers qui se distinguent par la qualité de voix et la présence d'annonces. Un crédit de bienvenue de 5 USD, valable trente jours, tient lieu d'essai.

### What Makes This Special

**Un interprète par personne, pas un animateur pour tous.** La différence n'est pas cosmétique : elle supprime l'écho par construction, permet à chacun de choisir son propre palier de qualité dans une même conversation, et fait de la condensation une régulation de charge plutôt qu'une dégradation subie. Un interprète qui prend du retard résume — comme le ferait un interprète humain — au lieu d'ensevelir son auditeur.

Le modèle « classe multilingue synchronisée » — micro-requêtes personnelles autorisées individuellement, macro-navigation toujours collective — résout une tension UX que ni les réseaux sociaux asynchrones ni les outils IA solo n'ont eu à résoudre. Aucun concurrent ne combine voix en direct, dynamique de groupe et augmentation de connaissance par IA dans un seul produit.

## Project Classification

**Type de projet :** Application mobile native (iOS/Android) pour le MVP ; extension prévue vers tablette et web pour supporter des invités sur ordinateur.
**Domaine :** Général (grand public, apprentissage informel entre pairs — pas de conformité edtech formelle requise).
**Complexité :** **Moyenne à élevée.** La classification « faible, aucune exigence réglementaire » de la version 1 ne tient plus. Quatre surfaces l'imposent : conservation de conversations traduites pendant un an, ciblage publicitaire par géolocalisation, soldes prépayés détenus au passif envers les utilisateurs, et droits d'accès et d'effacement de la personne concernée. Aucune n'est propre à un secteur réglementé, mais leur cumul dépasse le « standard ».
**Contexte projet :** Brownfield — 26 stories livrées sur une architecture à deux participants, dont l'Epic 6 remplace la topologie audio.

## Success Criteria

### User Success

Seb et Jean-Samuel savent que Salon fonctionne quand ils ressortent d'un trajet en ayant appris quelque chose de concret tout en s'étant diverti — signal renforcé quand cet apprentissage devient une routine plutôt qu'une nouveauté ponctuelle.

### Business Success

Aucune cible chiffrée fixée avant le lancement pour la croissance/engagement à long terme — ces métriques (segmentées par démographie, géographie, éducation, salaire, langue, occupation) établiront leurs propres lignes de base dès le lancement. Seuil minimal de signal de vie pour le premier mois : **20 vrais Salons organiques** (excluant tests et famille). Signal de validation à plus long terme : un **taux d'invitation d'amis comparable aux standards des réseaux sociaux dominants chez les cols blancs** (Facebook, LinkedIn).

### Technical Success

L'architecture repose sur **un interprète et une room par participant**, coordonnés par un orchestrateur par Salon. Ce choix coûte plus cher qu'un agent partagé unique, et c'est assumé : il supprime l'écho par construction, permet des paliers de qualité différents dans une même conversation, et rend chaque flux facturable individuellement — la structure de prix épouse la structure de coût.

Le coût unitaire est vérifié, non estimé : `grok-voice-think-fast-1.0` à 3,00 USD/h, `grok-voice-think-fast-2.0` à 4,80 USD/h, minutes d'agent LiveKit à 0,60 USD/h. **Tous les paliers sont rentables**, du moins cher au plus cher.

L'interprète est un **port** avec trois adaptateurs — temps réel, transcription-synthèse, et simulé. L'orchestrateur ne référence aucun fournisseur : le coût de migration reste borné, et les tests de charge s'exécutent sans consommer de crédits.

### Measurable Outcomes

- Taux de réponses positives à la question de satisfaction de fin de Salon
- Minimum 20 vrais Salons organiques au premier mois
- Taux d'invitation d'amis approchant la parité avec les réseaux sociaux dominants chez les cols blancs
- Fréquence d'usage, minutes/Salon et engagement, ventilés par segment
- **Taux de conversion avant péremption** : proportion des nouveaux inscrits ayant effectué au moins une recharge avant l'expiration de leur crédit de bienvenue, mesuré par cohorte
- **Délai avant première recharge** : minutes entre l'inscription et la première recharge réussie, publié en distribution (médiane, p25, p75, p90)
- **Ratio de méta-parole** par palier : proportion du temps où l'interprète parle *de* la conversation plutôt qu'il ne la restitue
- **Taux de condensation** par palier : indicateur de dégradation du palier le moins cher, à surveiller pour qu'il reste utilisable
- **Coût d'exploitation réel par palier**, rapproché du tarif de vente

## Product Scope

### MVP Strategy & Philosophy

MVP de validation de problème : la question centrale est si les gens veulent discuter vocalement d'un document ou d'une actualité, à deux ou trois, avec l'aide d'une IA — et sont prêts à payer pour ça au-delà d'un crédit de bienvenue. Ressources : solopreneur, sans équipe. Cette contrainte a orienté deux décisions structurantes — le plafond à trois participants, et le modèle prépayé qui supprime tout risque d'impayé et de recouvrement.

### MVP - Minimum Viable Product

**Conversation**
- Application mobile native (iOS/Android), **plafond de participants configurable, initialisé à 3**
- **Une room LiveKit et un interprète IA par participant**, coordonnés par un orchestrateur par Salon
- Journal partagé **polyglotte** — chaque tour dans la langue où il a été prononcé — un curseur de lecture par interprète ; restitution dans la langue détectée de chacun, traduite depuis l'original
- **Sous-titres traduits en direct**, web et mobile, dans un ensemble de langues plus large que celui de la voix
- Interventions bornées à 500 caractères, découpées sur frontière de phrase
- **Ordre premier arrivé premier servi** sur l'horodatage d'arrivée au journal — aucun tour de parole, aucune demande de parole, aucune détection par silence
- Détection automatique de la langue, sans sélection manuelle ; présentation de chaque participant et de sa langue à sa première prise de parole
- Agent toujours à l'écoute, sans mot-clé de réveil
- Nettoyage des hésitations à l'ingestion ; les pauses signifiantes deviennent une métadonnée restituée par les interprètes

**Régulation de charge**
- Condensation par interprète quand le retard s'installe, annoncée au participant
- Signal vocal « Vocaliz is busy » et suspension des ajouts d'une room saturée
- Plafond de monologue ; tous les seuils persistés et modifiables sans déploiement
- Infrastructure de test de charge simulant jusqu'à 50 participants sans coût fournisseur

**Modèle d'affaires**
- **Quatre paliers payants, aucun gratuit** : Base 3 USD/h (annonces, voix synthétique), Mode A 7,50 USD/h (annonces, voix naturelle), Mode B 15 USD/h (sans annonces), Mode C 22,50 USD/h (sans annonces, modèle premium). **Les tarifs absorbent 30 % de commission de magasin** — le taux plein, sans recours aux programmes réduits
- **Prépayé** : solde tenu en millicents, décrémenté toutes les 5 secondes, jamais négatif ; recharge par `PaymentIntent` hors session sur carte enregistrée, lien par courriel et SMS en repli
- **Crédit de bienvenue de 5 USD**, une fois à vie, expirant après 30 jours, avertissement 7 jours avant l'échéance
- **Rabais de 5 % sur les recharges effectuées depuis un navigateur** plutôt que depuis l'application, pour réorienter le paiement hors des magasins ; taux ventilable par plateforme et par région
- Chaque participant paie son propre palier ; option « l'hôte paie tout » ; participants téléphoniques toujours à la charge de l'hôte, majorés de 5 USD/h
- À solde épuisé, le Salon se termine ; si le payeur est l'hôte, le Salon se ferme après un préavis de 15 secondes aux invités

**Publicité**
- Inventaire d'annonces textuelles ciblées par ensembles de géolocalisations et de langues, lues par l'interprète dans la langue du participant
- Insertion entre deux messages, jamais au milieu d'une pensée ; fréquence différenciée par palier

**Accès & identité**
- Inscription légère : courriel, téléphone, ou les deux, plus nom d'utilisateur et mot de passe
- Jonction web sans installation ; un lien à usage unique par invité
- Invitation vocale d'un numéro de téléphone, qui rejoint par appel avec son propre interprète
- Registre permanent des identifiants ayant déjà donné lieu à un crédit
- Sources de contenu : documents téléversés et URLs, ajoutables avant et pendant le Salon par l'hôte
- Sortie par commande vocale ou fermeture ; question de satisfaction en fin de Salon

**Conservation & conformité**
- Journaux et curseurs persistés **un an à compter de la création du Salon**, pour la reprise après panne et la preuve de diffusion des annonces
- Chiffrement au repos de toute donnée personnelle ; aucun contenu de conversation dans les journaux applicatifs
- Droit d'accès et d'effacement, avec pseudonymisation de ce qui doit être conservé au titre comptable
- Flux d'événements unique dont les journaux comptables et les métriques sont des vues dérivées

### Growth Features (Post-MVP)

- **Montée à 50 participants** — non plus un tier post-MVP vague, mais un **palier conditionné à des critères mesurés** : latence médiane sous 10 s, moins de 20 % de contenu condensé, zéro blocage sur une heure, coût par participant sous 50 % du prix de son palier. Le plafond est une valeur de configuration ; le franchir est une décision de données, pas de calendrier.
- Tier institutionnel : courriel institutionnel, vérification d'âge déléguée à l'institution, tarification distincte
- Messagerie privée/publique en Salon
- File d'attente pondérée par temps de parole cumulé
- Interface d'administration — au MVP, l'octroi manuel de crédits se fait par commande en ligne
- Bouton d'Urgence Humaine : détection de sujets sensibles et redirection vers une ressource d'aide humaine

> **Abandonné :** le serveur MCP pour lever la main et céder la parole. Avec l'ordre premier arrivé premier servi, il n'y a plus de parole à attribuer. L'override de l'hôte subsiste sous forme de coupure de micro.
>
> **Sans objet :** les canaux de traduction personnalisés par utilisateur, qui étaient l'évolution prévue de l'agent partagé. Chaque participant a désormais son interprète dédié dès le MVP.

### Vision (Future)

- Extension vers tablette (Android/iOS) et web, pour permettre à un invité de rejoindre depuis un ordinateur
- Positionnement élargi : le divertissement de prédilection des automobilistes fortunés

### Risk Mitigation Strategy

**Risque technique :** L'intégration LiveKit+xAI reste le risque prioritaire. S'y ajoute la **latence** du chemin humain → interprète → journal → interprète → humain. Elle reste bornée à **un seul saut de traduction** grâce au journal polyglotte : un pivot aurait ajouté un second saut à toute paire de langues ne l'incluant pas. Le port Interprète borne l'exposition au fournisseur unique.

**Risque de conservation :** Persister un an de conversations traduites transforme une promesse de non-conservation en obligation de protection — chiffrement au repos, durée bornée, droits d'accès et d'effacement. Le point de vigilance est le **contenu de conversation qui fuirait dans les journaux applicatifs**, où personne ne le considérerait comme sensible.

**Risque financier :** Le solde prépayé non consommé est une **dette envers l'utilisateur**, à provisionner. Le prépayé supprime en revanche l'impayé, la rétrofacturation sur consommation contestée et le recouvrement.

**Risque de coûts fournisseurs :** Les tarifs xAI et LiveKit ont été vérifiés le 2026-08-08 et intégrés au modèle. Restent non vérifiés : la terminaison PSTN sortante et le CPM publicitaire réel, estimé à 25 USD. À faible volume, les **coûts fixes dominent** — environ 323 USD/mois d'infrastructure indépendamment de l'usage.

**Risque de marché :** Le risque principal n'est pas seulement "les gens n'utiliseront pas Vocaliz" — c'est la possibilité que **le vrai problème ne soit pas "analyser un document à deux avec l'IA", mais que la traduction simultanée en temps réel soit, en elle-même, le produit gagnant**, indépendamment de la discussion de documents. Ce signal doit être surveillé activement pendant le MVP : si l'usage du pipeline de traduction dépasse l'intérêt pour la discussion de documents, un pivot de positionnement pourrait être justifié.

**Risque de ressources :** Solopreneur — le scope MVP doit rester réalisable par une seule personne ; toute fonctionnalité qui ajoute une complexité d'implémentation significative (MCP, canaux personnalisés, messagerie) est repoussée post-MVP par défaut.

**Risque accepté :** Sans Bouton d'Urgence Humaine, une conversation qui dérive vers un sujet sensible ou émotionnellement difficile n'a aucun garde-fou au MVP — l'agent continue la discussion normalement. Ce risque est explicitement accepté pour garder le scope minimal ; à réévaluer si l'usage réel révèle des cas problématiques.

## User Journeys

### Journey 1: Seb & Jean-Samuel — Le Trajet du Matin (Chemin Heureux)

**Scène d'ouverture :** Seb monte dans sa voiture un lundi matin, café en main, avec 25 minutes de route devant lui. Il a vu passer un article technique dense sur l'architecture des LLM la veille sur LinkedIn, sans avoir eu le temps de le lire. Plutôt que la radio, il ouvre Vocaliz.

**Action montante :** Seb téléverse le lien de l'article, choisit le Mode B — voix naturelle, sans annonces — puis dit simplement « invite Jean-Samuel ». Jean-Samuel reçoit une notification, choisit le Mode Base à son écran de jonction, et rejoint depuis son propre trajet. Chacun entre dans sa room, avec son interprète. Celui de Seb lui annonce : *« Jean-Samuel parle français »*. La lecture de l'article commence.

**Climax :** À mi-parcours, une divergence d'opinion apparaît sur une architecture technique. L'interprète de Seb relance en citant un contraste avec un autre article. Jean-Samuel, en mode Base, entend une annonce de quinze secondes glissée entre deux répliques — son interprète le rattrape ensuite sans qu'il ait rien manqué.

**Résolution :** À l'arrivée au bureau, Seb dit « Je quitte le Salon ». Son interprète lui pose aussitôt la question de satisfaction. Seb répond oui : il a retenu bien plus que d'un podcast écouté passivement.

### Journey 2: L'Invité Sans l'Application (Cas Limite)

**Scène d'ouverture :** Un autre matin, Seb veut inviter Jean-Samuel à discuter d'une nouvelle qui vient de tomber — mais Jean-Samuel n'a pas installé Vocaliz.

**Action montante :** Seb l'invite quand même. Jean-Samuel reçoit un courriel avec un lien **à usage unique**. Il clique, arrive sur une page de jonction dans son navigateur, et s'inscrit en **quinze secondes** : une adresse courriel, un nom d'utilisateur, un mot de passe. Son crédit de bienvenue de 5 USD lui est accordé — l'écran lui indique ce qu'il achète : *« Base, offert pendant 2 h 30 »*.

**Climax :** Le Salon se déroule normalement — sa propre room, son propre interprète, la même qualité qu'un utilisateur installé. Il n'a rien téléchargé.

**Résolution :** En fin de Salon, il répond à la question de satisfaction, puis reçoit un courriel avec un lien d'installation. Sept jours avant l'expiration de son crédit, il en recevra un rappel indiquant ce qu'il lui reste.

> **Ce qui a changé depuis la version 1 :** la promesse n'est plus « sans compte », elle est **« sans installation »**. L'accès anonyme a disparu avec le modèle prépayé — on ne peut pas facturer quelqu'un qu'on ne peut pas identifier, ni faire respecter un crédit unique à vie sans clé d'identité. Ce qui reste vendable est intact : cliquer un lien et être dans la conversation en quinze secondes, depuis un navigateur, sans rien télécharger.

### Journey 3: L'Invité au Téléphone (Nouveau)

**Scène d'ouverture :** Seb veut faire entrer son père dans la conversation. Son père n'a ni l'application, ni l'envie de cliquer un lien.

**Action montante :** Seb dit « invite le 514-555-0142, en Mode B ». Son interprète lui répète le numéro et attend confirmation — composer coûte de l'argent et appelle quelqu'un. Seb confirme. Le téléphone sonne.

**Climax :** Son père décroche. Une voix se présente : elle dit qui l'invite et ce qui va se passer. Il répond en français ; sa langue est détectée à ses premiers mots, et il est présenté aux autres. Il participe sans avoir rien installé, rien créé, rien cliqué.

**Résolution :** Il raccroche pour quitter. Tout son coût — interprète, minutes SIP, supplément de 5 USD/h — a été porté par Seb, qui en avait vu le montant horaire avant de composer.

### Journey Requirements Summary

- **Invitation & provisioning :** un lien à usage unique **par invité**, déclenché vocalement par l'hôte ; livré par courriel ou notification in-app. Un numéro de téléphone peut être invité directement, après confirmation vocale du numéro reconnu.
- **Accès sans installation :** page de jonction web, inscription légère — courriel ou téléphone, nom d'utilisateur, mot de passe — en quelques secondes. **Plus d'accès anonyme.**
- **Sécurité d'accès :** token à usage unique invalidé après la première connexion
- **Choix de palier :** à la création pour l'hôte, à la jonction pour chaque participant ; l'écran affiche la durée que le crédit de bienvenue couvre dans chaque palier, non le seul tarif horaire
- **Sortie de Salon :** commande vocale, fermeture, ou raccroché ; question de satisfaction dans tous les cas, y compris quand le Salon se termine faute de solde
- **Infrastructure temps réel :** LiveKit comme transport, **une room par participant** avec son interprète ; intégration SIP pour les participants téléphoniques ; ordre premier arrivé premier servi
- **Onboarding léger :** courriel de suivi avec lien d'installation après la premier Salon

## Innovation & Novel Patterns

### Detected Innovation Areas

- **Discussion de groupe voice-first orchestrée par IA** — aucune plateforme existante ne combine voix en direct, dynamique de groupe et augmentation de connaissance par IA dans un seul produit
- **Modèle "classe multilingue synchronisée"** — micro-requêtes personnelles autorisées individuellement, macro-navigation toujours collective
- **Un interprète par personne, sans pivot entre eux** — chacun converse en audio direct avec son propre interprète ; les interprètes s'échangent les tours dans la langue où ils ont été prononcés, et chaque traduction part de l'original. L'écho devient impossible par construction plutôt que d'être combattu, chaque participant peut choisir un palier de qualité différent dans une même conversation, et **aucune paire de langues ne subit deux sauts de traduction**.
- **La vidéo muette comme preuve d'identité** — dans un produit où toute parole est restituée par une IA, la voix ne prouve plus qui parle. Une image sans son, optionnelle et jamais enregistrée, restaure ce que la médiation a retiré : la certitude que l'interlocuteur est bien la personne annoncée.
- **La condensation comme régulation, non comme panne** — quand un interprète prend du retard, il résume au lieu d'ensevelir : *« pendant que tu écoutais, trois personnes ont dit ceci, en substance… »*. C'est le comportement d'un interprète humain, pas une dégradation subie — et il est annoncé, jamais silencieux.
- **La fidélité comme palier tarifaire** — moins d'annonces signifie mécaniquement moins de retard, donc moins de condensation, donc davantage de paroles réelles. Le prix n'achète pas seulement le silence publicitaire : il achète de l'exactitude.
- **Jonction téléphonique avec interprète dédié** — quelqu'un qui n'a ni application, ni navigateur, ni compte peut participer à une conversation multilingue en décrochant son téléphone
- **Bouton d'Urgence Humaine** (post-MVP) — l'IA reconnaît explicitement ses limites et redirige vers une aide humaine plutôt que de simuler une compétence qu'elle n'a pas

### Market Context & Competitive Landscape

- **Discord/Clubhouse (audio de groupe) :** aucune augmentation de connaissance par IA, aucune orchestration structurée de la parole par un agent
- **ChatGPT/agents IA solo :** puissants individuellement, mais sans dynamique de groupe ni contraste social des idées
- **LinkedIn/Facebook :** interaction asynchrone et visuelle, aucune approche voice-first
- Aucun concurrent direct identifié combinant voix en direct + facilitation IA + groupe

### Validation Approach

- Seuil de signal de vie : 20 vrais Salons organiques au premier mois
- Taux de réponses positives à la question de satisfaction de fin de Salon comme signal de validation continu, Salon après Salon
- Taux d'invitation d'amis comme validation de l'effet de réseau et de la valeur perçue

### Risk Mitigation

- **Risque :** dépendance à la disponibilité et à la tarification de xAI et LiveKit → **Mitigation :** le port Interprète fait du fournisseur un adaptateur remplaçable ; le changement de modèle est déjà une ligne de configuration par palier
- **Risque :** récolte industrielle du crédit de bienvenue → **Mitigation :** registre permanent des identifiants ayant déjà donné lieu à un crédit, montant ramené à 5 USD, péremption à 30 jours
- **Risque :** dégradation du palier le moins cher au point de le rendre inutilisable, la charge publicitaire y étant la plus forte → **Mitigation :** taux de condensation et ratio de méta-parole instrumentés **par palier**

## Mobile App Specific Requirements

### Project-Type Overview

Salon MVP est une application mobile iOS/Android construite avec React Native via Expo (déployée avec Expo Application Services). L'intégration Android Auto / Apple CarPlay est planifiée mais explicitement hors scope MVP.

### Technical Architecture Considerations

Le client mobile reste volontairement mince : il gère l'audio, l'upload de documents et d'URLs, l'affichage minimal — choix de palier, solde restant, invitations, question de satisfaction — et se connecte à **sa** room LiveKit, provisionnée par le backend, où son interprète est déjà présent. Il ne voit ni le journal, ni les autres rooms, ni l'orchestrateur.

### Platform Requirements

React Native via Expo pour iOS et Android — un seul codebase, déploiement géré par Expo Application Services (EAS Build, EAS Submit). Android Auto et Apple CarPlay sont prévus post-MVP, non requis au lancement.

### Device Permissions

Accès au **microphone** requis — c'est le cœur de l'expérience voice-first.

Accès à la **caméra** requis uniquement pour la vidéo muette optionnelle de FR72, et demandé **au moment de l'activation** plutôt qu'à l'installation. Une permission caméra réclamée à l'ouverture d'un produit vocal serait à la fois inutile et suspecte.

### Offline Mode

Aucun mode hors ligne requis — Vocaliz est fondamentalement un service temps réel en direct (conversation vocale via LiveKit + xAI). Sans connexion, il n'y a simplement pas de Salon possible.

### Push Notification Strategy

Les invitations passent par **courriel**, ou par notification in-app pour un contact déjà inscrit. Le **SMS** est réservé aux messages qui ne doivent pas être manqués : liens d'autorisation de paiement et avertissements de péremption de crédit, envoyés sur tous les canaux dont dispose la personne. Un utilisateur n'ayant fourni qu'un seul identifiant reçoit tout sur ce seul canal — c'est un choix valide, jamais une configuration incomplète. Les notifications push natives ne sont pas requises au lancement.

### Store Compliance

Vocaliz vend du temps de conversation consommé **dans** l'application, sur un solde prépayé rechargé via Stripe. C'est un service numérique consommé en Salon : les règles d'achat intégré s'appliquent en principe. **État vérifié au 2026-08-08 :**

**Apple — États-Unis.** À la suite de l'injonction *Epic v. Apple*, Apple ne peut prélever **aucune commission** sur un achat effectué par lien externe qualifié, ni empêcher un développeur d'en informer ses utilisateurs. ⚠️ **Situation provisoire** : la Cour suprême a accepté d'entendre l'appel en juin 2026, plaidoiries entre octobre et décembre 2026. Une commission peut être rétablie.

**Apple — hors États-Unis.** Commission de 15 à 30 % sur achat intégré. Dans l'UE, l'achat externe reste soumis à 2 % de frais d'acquisition plus 5 à 13 % de services de magasin.

**Google — États-Unis, Royaume-Uni, EEE (depuis le 30 juin 2026).** La commission est scindée : **frais de service de 10 %** sur le premier million annuel, **dus quel que soit le mode d'encaissement**, plus **frais de facturation de 5 %** dus uniquement en passant par Google Play Billing. Passer par le web n'économise donc que 5 %. Déclaration des transactions et paiement des frais de service obligatoires à compter du 1ᵉʳ octobre 2026.

**Stratégie tarifaire : absorber 30 % dès le départ.**

```
                       sous 1 M$      au-dessus de 1 M$
Apple, achat intégré   15 %           30 %
Google, service        10 %           20 % (nouvelles installations) à 25 % (existantes)
Google, facturation     5 %           5 %
Google, lien web       10 %           15 %
Apple, lien externe     0 % (É.-U.)   0 % (É.-U.) — sous réserve de la Cour suprême
```

Les tarifs sont calés sur le **taux plein de 30 %**, alors que la commission réellement prélevée sous un million de ventes n'est que de **15 %** — Apple Small Business Program, service fee réduit de Google. Ce choix produit deux effets voulus :

- **Une marge de croissance de 15 points** pendant toute la phase d'amorçage, soit ≈ **150 000 USD sur le premier million de ventes**, disponible pour financer l'acquisition sans lever de fonds.
- **Aucune hausse de tarif au franchissement du seuil.** La marge se resserre vers le régime de long terme, qui reste positif sur les quatre paliers. Les clients acquis tôt ne subissent jamais d'augmentation — c'est le rendez-vous tarifaire que cette stratégie supprime.

Avec des tarifs calés sur 30 %, le canal navigateur devient le plus profitable de très loin : jusqu'à 30 points d'écart avec le magasin. Le rabais de 5 % de FR71 est prudent au regard de cet écart et pourra être relevé, plateforme par plateforme.

**Position structurelle de Vocaliz.** La mécanique de recharge ne comporte **aucune interface d'achat dans l'application** : consentement vocal, lien par courriel pour la première carte, puis `PaymentIntent` hors session déclenchés côté serveur. Position plus favorable qu'un bouton d'achat intégré, mais qui ne garantit rien — les magasins visent le déblocage de fonctionnalité dans l'application, pas seulement l'endroit où s'affiche le formulaire de paiement. **À faire valider juridiquement avant soumission.**

**Sources :** [Ninth Circuit, déc. 2025](https://www.macrumors.com/2025/12/11/apple-app-store-fees-external-payment-links/) · [Cour suprême, mai 2026](https://macdailynews.com/2026/05/06/apple-seeks-u-s-supreme-court-stay-in-ongoing-epic-games-app-store-commission-battle/) · [Google Play Console — facturation alternative](https://support.google.com/googleplay/android-developer/answer/16497028?hl=en) · [Google Play, nouvelle structure de frais](https://www.neonpay.com/blog/google-plays-new-u.s.-billing-linking-policies-what-game-developers-need-to-know) · [Guide app-to-web, RevenueCat](https://www.revenuecat.com/blog/engineering/app-to-web-purchase-guidelines)

### Implementation Considerations

Le backend comprend deux composants déployables sur AWS ECS Fargate : le **worker d'interprète**, qui héberge les adaptateurs du port, et l'**orchestrateur par Salon**, qui tient le journal, les curseurs et le métrage.

Le journal étant persisté, une instance qui reprend un Salon relit son état plutôt que de le perdre. L'affinité entre un Salon et son instance reste souhaitable pour la performance, mais n'est plus une condition de survie : un déploiement draine par confort, non par nécessité.

Le client mobile reste concentré sur l'audio et une UI minimale, ce qui facilite l'extension future vers tablette et web — même backend, nouveau client.

## Functional Requirements

### Création de Salon & Invitation

- FR1: Un hôte peut créer un Salon en téléversant un document, en fournissant une URL de nouvelle comme source, ou sans aucune source — dans ce dernier cas, l'interprète ouvre le Salon en demandant aux participants de quoi ils souhaitent discuter
- FR3: Un hôte peut ajouter un document ou une URL supplémentaire à un Salon actif, avant ou pendant celle-ci
- FR4: Un invité sans l'application mobile installée peut rejoindre un Salon directement depuis un navigateur web
- FR5: Un lien d'invitation ne peut être utilisé qu'une seule fois pour rejoindre un Salon
- FR43: Le plafond de participants d'un Salon est une valeur de configuration, initialisée à 3 ; la jonction est refusée au-delà
- FR47: Un lien de jonction à usage unique distinct est émis pour chaque invité
- FR57: Un hôte peut inviter vocalement un numéro de téléphone, après confirmation du numéro reconnu. L'appelé rejoint par appel entrant, avec sa propre room et son propre interprète, sans inscription ni application. L'hôte choisit son palier parmi A, B ou C et le paie, majoré de 7,50 USD/h

### Expérience de Discussion Vocale

- FR6: L'interprète lit à voix haute le contenu source du Salon
- FR7: Les participants peuvent discuter du contenu source sans l'avoir lu ou consulté au préalable
- FR8: L'interprète introduit des informations contrastantes provenant d'autres sources pendant la discussion
- FR10: L'interprète comprend le langage naturel en tout temps, sans mot-clé de réveil requis
- FR11: Les participants peuvent ajuster vocalement la fréquence d'intervention proactive de leur interprète
- FR44: L'ordre de restitution est premier arrivé premier servi sur l'horodatage d'arrivée au journal — aucun tour de parole, aucune demande de parole, aucune attribution
- FR45: L'hôte peut couper le micro d'un participant ; cette action ne donne ni ne retire la parole
- FR52: Les messages sont bornés à 500 caractères et découpés sur frontière de phrase ; aucune insertion tierce à l'intérieur d'une intervention découpée, sauf au-delà du plafond de monologue
- FR58: Dès qu'un participant prend la parole pour la première fois, il est présenté aux autres avec sa langue, juste avant la restitution de son premier message
- FR76: Le mode conduite s'active et se désactive **manuellement par un interrupteur**, et **automatiquement au-delà de 10 km/h** mesurés par la position GPS. La vitesse est calculée **sur l'appareil et n'en sort jamais**. Une **sortie manuelle prime** et suspend l'automatisme pour le Salon — un passager ne doit pas être enfermé dans un écran noir. Deux seuils distincts évitent que le mode ne clignote à chaque feu rouge
- FR75: Le **mode conduite** est **vocal uniquement** : l'écran devient noir et suspend la vidéo (FR72), les sous-titres (FR73) et les voyants de parole (FR74). Il ne masque pas l'interface — il **supprime la raison de baisser les yeux**. La langue de sous-titres est vidée pendant toute sa durée, de sorte que rien n'est traduit ni facturé pour un participant qui ne lit pas
- FR74: Un **voyant de parole** indique, pour chaque paire humain-interprète du Salon, qui est en train de parler — **vert** quand la voix est active, **rouge** sinon. Chaque participant voit l'état de **toutes** les paires : dans une topologie où personne n'entend directement personne, le silence dans son oreille ne signifie plus que personne ne parle
- FR73: Des **sous-titres en direct traduits** sont disponibles pour l'hôte comme pour chaque participant, **sur le web et sur mobile**. Ils sont offerts dans **toutes les langues que la traduction textuelle supporte** — un ensemble plus large que celui des langues parlées par le speech-to-speech : on peut suivre en lisant une langue que la voix ne saurait pas prononcer. Chaque participant choisit sa langue de sous-titres et leur taille, indépendamment des autres
- FR72: Un participant peut activer une **vidéo muette en direct** de lui-même, visible des autres. Elle ne porte aucun son, n'est jamais enregistrée, est désactivée par défaut, et n'est jamais suggérée pendant un Salon en déplacement. Sa fonction est l'assurance d'identité — savoir que son interlocuteur est bien la personne annoncée, dans un produit où l'on n'entend plus jamais sa vraie voix
- FR59: Un participant rejoignant un Salon en cours peut recevoir la conversation tenue depuis sa création ; l'hôte décide de cet accès au moment de l'invitation tardive
- FR60: L'interprète retire les pauses mortes et les hésitations non signifiantes avant l'ajout au journal
- FR61: Une pause dépassant 2 000 ms est convertie en métadonnée `[pause=N]` dans le journal, en millisecondes, plafonnée à 5 000 ms ; elle est appliquée par les interprètes et jamais prononcée

### Traduction Multilingue

- FR12: Le système détecte automatiquement la langue parlée par chaque participant, sans sélection manuelle
- FR13: L'affichage visuel est présenté dans la langue vocale détectée de l'utilisateur, sans sélection manuelle
- FR14: Les participants peuvent s'exprimer dans leur propre langue pendant un Salon
- FR15: Le contenu parlé est traduit et lu à voix haute à chaque participant dans sa propre langue
- FR16: Le contenu traduit est lu pendant que l'interlocuteur d'origine continue de parler, sans interrompre la conversation
- FR38: Le mode Base et le mode speech-to-speech sont deux adaptateurs du même port Interprète
- FR46: Chaque participant occupe sa propre room LiveKit avec son interprète dédié et reçoit la restitution dans sa langue, sans audio partagé

**Langues supportées :** Anglais, arabe (Égypte, Arabie saoudite, Émirats), bengali, chinois simplifié, français, allemand, hindi, indonésien, italien, japonais, coréen, portugais (Brésil, Portugal), russe, espagnol (Mexique, Espagne), turc, vietnamien — selon les capacités documentées de l'API Speech-to-Speech de xAI ([docs.x.ai](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech#supported-languages)). L'espagnol et le portugais nécessitent une variante régionale plutôt que le code de langue de base.

**Cette liste est celle des langues PARLÉES** : l'intersection des langues supportées par tous les adaptateurs d'interprète, et non leur union. Le speech-to-speech est le plus restrictif ; c'est donc lui qui la définit. La conséquence est délibérée — **changer de palier ne change jamais les langues parlées disponibles.** Ajouter une langue parlée exige qu'elle soit supportée par les trois adaptateurs.

**Les langues de sous-titres forment un ensemble distinct et plus large** (FR73). La traduction textuelle n'a pas les contraintes de la synthèse vocale : elle couvre davantage de langues. Un participant peut donc **suivre en lisant une langue que la voix ne saurait pas prononcer**, sa restitution vocale se rabattant alors sur une langue parlée disponible.

```
langues PARLÉES    intersection des adaptateurs — la plus restrictive fait la règle
langues ÉCRITES    tout ce que la traduction textuelle supporte — plus large
```

### Paliers d'Expérience

- FR32: Un Salon offre toujours le speech-to-speech comme option d'expérience, en plus du mode Base
- FR33: Quatre paliers payants coexistent — Base 3 USD/h (annonces, voix synthétique), Mode A 7,50 USD/h (annonces, voix naturelle), Mode B 15 USD/h (sans annonces, voix naturelle), Mode C 22,50 USD/h (sans annonces, modèle premium). **Aucun palier n'est gratuit.** Chacun n'ajoute qu'une seule chose au précédent. Les tarifs absorbent 30 % de commission de magasin (majoration ÷ 0,70)
- FR34: À la création, l'hôte configure **ses trois options personnelles** ; aucune ne s'applique aux autres participants
- FR35: À la jonction, chaque participant payeur configure **les mêmes trois options**, indépendamment de l'hôte et des autres

> **Les trois options d'un participant payeur**, présentées au même écran — à la création pour l'hôte, à la jonction pour un invité :
>
> | | Option | Valeurs | Défaut |
> |---|---|---|---|
> | 1 | **Palier d'expérience** | Base · Mode A · Mode B · Mode C | choix explicite requis |
> | 2 | **Vidéo muette** | activée · désactivée | désactivée |
> | 3 | **Montant de recharge** | entre le plancher de sa granularité et 500 USD | plancher |
>
> Elles sont personnelles et indépendantes : trois participants peuvent tenir trois jeux de choix différents. Seule « l'hôte paie tout » (FR42) échappe à cette règle — elle n'appartient qu'à l'hôte et écrase le palier des invités qu'il couvre, toujours vers le haut.
- FR36: Le palier choisi persiste toute la durée du Salon, sauf changement explicite du participant
- FR37: Un Salon réunit simultanément des participants de paliers différents, sans qu'aucun ne soit dégradé par le choix d'un autre

### Publicité

- FR39: Les annonces résident dans une table d'inventaire où l'interprète puise au moment opportun de sa room ; l'insertion a lieu entre deux messages, jamais à l'intérieur d'une intervention découpée, et chaque interprète suit son propre rythme
- FR50: Une annonce porte un ensemble de géolocalisations cibles et un ensemble de langues cibles — celles parlées par les humains à qui elle sera lue ; des participants d'un même Salon peuvent recevoir des annonces différentes

### Solde, Facturation & Recharge

- FR20: Le système comptabilise le temps de conversation de chaque participant, échantillonné toutes les 5 secondes ; seuls les blocs complétés sont facturés, l'arrondi se faisant en faveur du client
- FR21: Un participant doit disposer d'un moyen de paiement pour recharger son solde
- FR40: Chaque participant est facturé au tarif de son propre palier, au prorata du bloc d'échantillonnage
- FR41: Un participant doit disposer d'un solde strictement positif pour consommer un palier ; aucun mode ne démarre à découvert
- FR42: À la création, l'hôte peut activer « l'hôte paie tout » : il est alors facturé au tarif Mode B multiplié par le nombre de participants, et tous passent en Mode B sans annonces
- FR55: À solde épuisé, le Salon du participant se termine. La fin est précédée d'une alerte dès que le solde couvre moins de 3 minutes — 5 minutes pour un hôte, dont l'épuisement ferme le Salon pour tous, après un préavis de 15 secondes aux invités
- FR56: Le paiement précède l'usage. Le solde prépayé est tenu en millicents, décrémenté toutes les 5 secondes, reporté sans expiration, et ne devient jamais négatif. La recharge est proposée vocalement, puis exécutée par `PaymentIntent` hors session si une carte est enregistrée — le lien par courriel et SMS n'étant qu'un repli
- FR63: Une vérification périodique s'exécute toutes les 5 secondes et contrôle que le solde de chaque payeur couvre un bloc complet supplémentaire, le coût de ce bloc étant arrondi à la hausse
- FR66: L'exploitant peut accorder manuellement un second crédit, par commande en ligne, après un délai minimal de 90 jours ; montant par défaut 3 USD
- FR67: Tout crédit offert donne lieu à une écriture comptable suivant quatre états — émis, consommé, périmé, abandonné par suppression de compte. Seul le montant consommé constitue une charge réelle
- FR68: Le solde payé donne lieu à un journal comptable suivant l'encaissé, le consommé, le remboursé, et le restant dû — ce dernier constituant le passif envers les utilisateurs
- FR69: Après un an d'inactivité d'un utilisateur dont le solde payé est positif, un courriel lui signale son compte inactif et son solde restant, avec copie à l'exploitant
- FR71: Une recharge effectuée depuis un **navigateur** — Chrome, Safari ou autre — bénéficie d'un **rabais de 5 %** par rapport à la même recharge initiée depuis l'application mobile, l'utilisateur en étant informé au moment du choix. Le taux est un paramètre de configuration **ventilable par plateforme et par région**, les commissions de magasin évitées variant de 5 % à 30 % selon la combinaison

### Régulation de Charge

- FR49: Quand le retard de l'interprète d'une room dépasse 5 minutes, ce participant seul reçoit le signal vocal « Vocaliz is busy » et l'ajout de ses messages est suspendu jusqu'au retour sous le seuil de déblocage. La saturation est par room, jamais globale
- FR53: Quand le retard d'un interprète dépasse 2 minutes, il restitue les messages en attente sous forme condensée plutôt qu'intégrale, et l'annonce explicitement
- FR54: Les paramètres opérationnels du Salon sont persistés individuellement et modifiables sans déploiement
- FR62: Quand plusieurs prises de parole de l'interprète sont prêtes simultanément, elles sont émises dans un ordre déterministe : saturation et recharge, puis alerte de solde, puis publicité

### Compte, Identité & Droits

- FR18: Un nouvel utilisateur crée un compte avant de pouvoir utiliser Vocaliz
- FR51: Toute personne s'inscrit avec une adresse courriel, un numéro de téléphone, ou les deux, et reçoit une seule fois à vie un crédit de bienvenue de 5 USD, expirant après 30 jours, avec avertissement 7 jours avant l'échéance. Le crédit n'est accordé que si aucun des identifiants fournis n'a déjà servi
- FR64: Un participant peut modifier l'un de ses deux identifiants en conservant l'autre comme ancre de continuité, jamais les deux à la fois ; son crédit conserve son montant courant
- FR65: À l'inscription, l'utilisateur choisit un nom d'utilisateur unique et un mot de passe. Pour une demande de remboursement, la vérification par le moyen de paiement Stripe enregistré est également recevable
- FR70: Toute personne peut obtenir une copie des données la concernant et demander leur effacement, après vérification de son identité. L'effacement porte sur ses propres paroles et ses données de compte ; il pseudonymise ce qui doit être conservé au titre comptable et ne rétablit jamais l'éligibilité au crédit de bienvenue

### Retour d'Expérience & Fin de Salon

- FR24: Un participant peut quitter un Salon à tout moment par une commande vocale dans sa propre langue
- FR25: Un participant peut quitter un Salon à tout moment en fermant l'application ou le navigateur
- FR26: L'interprète pose une question simple de satisfaction immédiatement après la sortie de Salon, y compris lorsque celle-ci résulte d'un solde épuisé

### Compte & Historique

- FR28: Un utilisateur inscrit peut consulter son historique de Salons passés et de partenaires de discussion
- FR29: Un utilisateur inscrit peut démarrer un nouveau Salon avec n'importe quel partenaire précédent
- FR30: Un invité reçoit automatiquement un courriel avec un lien d'installation une fois sa premier Salon terminé
- FR31: Un invité peut installer l'application native via ce lien et continuer à utiliser Vocaliz

**Note :** Le Bouton d'Urgence Humaine est reporté post-MVP — voir Product Scope → Growth Features.

## Non-Functional Requirements

### Performance

Aucun seuil de latence n'est fixé pour le MVP à 3 participants : la latence du chemin voix→pivot→voix sera validée empiriquement. En revanche, **le franchissement du plafond vers 50 participants est conditionné à quatre critères mesurés** : latence médiane de restitution sous 10 s, moins de 20 % de contenu restitué sous forme condensée, zéro blocage sur un Salon d'une heure, et coût par participant sous 50 % du prix de son palier. Le plafond est une valeur de configuration ; le franchir est une décision de données.

### Security

Les liens d'invitation à usage unique expirent après la première connexion. Les méthodes de paiement sont gérées entièrement via Stripe (tokenisation) — Vocaliz ne stocke aucune donnée de carte. Les mots de passe sont conservés sous forme de condensat salé.

> ⚠️ **Révisé en version 2.** La version 1 affirmait que « Vocaliz ne conserve aucun transcript de Salon ». **Cette promesse ne tient plus** : les journaux sont persistés un an (voir Durability). Ce qui subsiste de l'engagement d'origine est le lien à usage unique et la tokenisation Stripe.

### Durability

Le journal de chaque Salon et les curseurs de chaque interprète sont **persistés**, pour permettre la reprise après panne et prouver la diffusion des annonces. **La durée de conservation est d'un an à compter de la création du Salon**, après quoi journal et curseurs sont effacés automatiquement. L'effacement d'un journal n'affecte ni les écritures comptables ni le flux d'événements, qui ne contiennent aucun contenu de conversation et relèvent d'obligations distinctes.

### Confidentiality

Toute donnée personnelle persistée est **chiffrée au repos** : journaux et curseurs, soldes et écritures comptables, identifiants, consentements de géolocalisation, registre des identifiants brûlés. Les clés sont gérées par AWS KMS et font l'objet d'une rotation. Les sauvegardes sont chiffrées au même titre. **Aucun contenu de conversation n'est jamais écrit dans les journaux applicatifs** — un message de diagnostic ne référence que des identifiants et des longueurs.

### Auditability

Les faits financiers et opérationnels sont écrits **une seule fois**, dans un flux d'événements append-only qui fait seul autorité. Les journaux comptables et les métriques en sont des **vues dérivées**, jamais des écritures parallèles : trois écritures concurrentes du même fait finissent toujours par diverger, et rien ne permet alors de dire laquelle a raison.

### Observability

Le système instrumente le taux d'adoption par palier, le taux de complétion, la satisfaction et le taux de conversion par palier, le ratio de coût d'exploitation, le retard par participant, le taux de condensation, le nombre de saturations, le **ratio de méta-parole**, le **taux de conversion avant péremption** du crédit par cohorte, et le **délai avant première recharge** publié en distribution.

### Testability

Le projet fournit une infrastructure de test de charge simulant jusqu'à 50 participants, assertant les retards, la latence p50/p95, le déclenchement de la condensation, les événements de saturation et la durée des blocages — **sans consommer de crédits fournisseur**, grâce à un adaptateur d'interprète simulé.

### Modularity

L'interprète est un **port** ; l'orchestrateur ne référence aucun fournisseur en dur. Trois adaptateurs sont livrés : temps réel, transcription-synthèse, et simulé. Cette contrainte réduit l'exposition au fournisseur unique et rend le changement de modèle par palier une simple ligne de configuration.

### Integration

En cas d'indisponibilité de xAI, de LiveKit, ou de Stripe au moment de rejoindre ou démarrer un Salon, le système présente un message d'erreur clair plutôt qu'un échec silencieux ou un comportement indéfini.
