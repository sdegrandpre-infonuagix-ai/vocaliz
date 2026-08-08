# salon — Project Context

## Project Goals

Vocaliz est une application mobile native (iOS/Android) voice-first qui permet à un petit groupe — trois personnes au maximum — de discuter en temps réel d'un document ou d'une actualité, chacune assistée par son propre interprète IA. Elle cible les cols blancs, en particulier les professionnels techniques, qui doivent se tenir à jour dans un domaine en évolution rapide mais manquent de temps et de format adapté : les sources actuelles sont asynchrones et visuelles, donc inutilisables en conduisant. Vocaliz transforme le trajet quotidien en un moment d'apprentissage social et actif — aucune lecture préalable n'est requise, l'interprète lit et anime la discussion, traduit en direct, et une question de satisfaction en fin de Salon capture le ressenti.

Chaque participant occupe sa propre room avec un interprète dédié. Les interprètes s'échangent les tours de parole via un orchestrateur central — **chacun dans la langue où il a été prononcé** — puis restituent dans la langue de leur humain, en traduisant toujours **depuis l'original**. Personne n'entend l'audio brut d'un autre : la barrière linguistique disparaît, et l'écho avec elle.

Chacun **entend** dans sa langue et **lit** dans sa langue : l'interprète parle, les sous-titres écrivent, les deux canaux convergent vers la même personne.

Le produit est payant dès la première minute, en quatre paliers qui se distinguent par la qualité de voix et la présence d'annonces. Un crédit de bienvenue de 5 USD, valable trente jours, tient lieu d'essai.

### What Makes This Special

**Un interprète par personne, pas un animateur pour tous.** La différence n'est pas cosmétique : elle supprime l'écho par construction, permet à chacun de choisir son propre palier de qualité dans une même conversation, et fait de la condensation une régulation de charge plutôt qu'une dégradation subie. Un interprète qui prend du retard résume — comme le ferait un interprète humain — au lieu d'ensevelir son auditeur.

Le modèle « classe multilingue synchronisée » — micro-requêtes personnelles autorisées individuellement, macro-navigation toujours collective — résout une tension UX que ni les réseaux sociaux asynchrones ni les outils IA solo n'ont eu à résoudre. Aucun concurrent ne combine voix en direct, dynamique de groupe et augmentation de connaissance par IA dans un seul produit.

## Success Metrics

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

## Scope Boundaries

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
- File d'atten

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
