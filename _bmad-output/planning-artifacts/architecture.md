---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/epics.md'
  - '_bmad-output/planning-artifacts/story-audit-2026-08-08.md'
  - '_bmad-output/planning-artifacts/ux-design-specification.md'
  - '_bmad-output/planning-artifacts/product-brief-salon-2026-07-25.md'
  - '_bmad-output/planning-artifacts/product-rule-voice-modes.md'
  - 'CODE — api/ agent/ mobile/ infra/ (héritage du projet Salon)'
  - 'AWS — pile SalonApi déployée en ca-central-1, compte 006619322178'
workflowType: 'architecture'
project_name: 'vocaliz'
user_name: 'BMad'
date: '2026-08-08'
projectContext: 'brownfield — transformation d''un produit déployé'
---

# Architecture Decision Document — Vocaliz

_Ce document décrit la **transformation** d'un produit existant, non la conception d'un produit neuf. Il se lit en trois couches : ce qui est hérité et conservé, ce qui change, et ce qui s'ajoute._

---

## Vocabulaire — Deux Mots, Deux Choses

Ce document, le code et les stories emploient désormais ces deux termes au sens strict. Ils ne sont pas interchangeables, et l'un des deux remplace un mot ambigu.

> **SALON** — un regroupement de **jusqu'à trois paires** interprète-IA + humain qui conversent ensemble. C'est l'unité de conversation, de facturation et de rétention.
>
> **ROOM** — une **room LiveKit Cloud** contenant exactement **un interprète IA et un humain**. C'est l'unité de transport audio.

```
SALON  =  { room₁, room₂, room₃ }  +  orchestrateur  [+ 1 room vidéo muette]

room_i =  1 humain  ⟷ audio ⟷  1 interprète IA
```

Un Salon contient N rooms. Une room n'appartient qu'à un Salon et à un participant.

### Le mot `session` a été retiré — fait le 2026-08-08

Le schéma appelait `session` ce que le produit appelle un Salon. Le mot est abandonné pour trois raisons :

1. **Il confond.** Le produit dit « Salon » partout — brief, PRD, UX, interface — et le schéma disait « session ».
2. **Il était déjà pris.** SQLAlchemy nomme `Session` son objet de connexion à la base. Un modèle `SessionModel` cohabitant avec un `Session` SQLAlchemy dans les mêmes fichiers était une ambiguïté inscrite dans le code, pas une préférence de style.
3. **Il devenait faux avec la nouvelle topologie.** « Session » suggérait une conversation *et* sa room. Ce sont maintenant deux choses distinctes.

### Ce qui a été renommé

| Avant | Après | Portée |
|---|---|---|
| table `sessions` | **`salons`** | schéma — migration `044` |
| `sessions.id` | `salons.id` | ← **identifiant canonique d'un Salon** |
| colonne `session_id` | `salon_id` | `utterances` · `invitations` · `billing_events` · `ad_broadcasts` · `shared_source_consents` · `salon_sources` |
| table `session_sources` | `salon_sources` | schéma |
| classe `SessionModel` | `Salon` | `models/session.py` → `models/salon.py` |
| `routers/sessions.py` | `routers/salons.py` | endpoints `/sessions` → `/salons` |
| `services/session_lifecycle.py` | `salon_lifecycle.py` | |
| règle `SweepExpiredSessions` | `SweepExpiredSalons` | EventBridge — remplacement du construct |
| action `session_ended` | `salon_ended` | canal de données LiveKit |
| `sessionsApi.ts` · `SessionCreationScreen` | `salonsApi.ts` · `SalonCreationScreen` | mobile |

**Non renommé, et volontairement :** `DbSession`, `SessionLocal`, `sessionmaker`, `TestingSession`, `synchronize_session` (SQLAlchemy) ; `AgentSession`, `agent_session` (LiveKit) ; `AudioSession` (React Native) ; `off_session` (Stripe) ; `sessionStorage` (navigateur). Le mot désigne quatre autres choses que le Salon, et c'est toute la difficulté de ce renommage.

`sessions.livekit_room_name` est **supprimée** : sous la topologie multi-rooms, un nom de room est une propriété de la participation, pas du Salon.

**`salon_events` ne change pas** — il porte déjà le bon mot. Sa clé primaire, en revanche, doit passer de `(participant_identity, salon_name)` à `(participant_identity, salon_id)`, pour la raison développée en *Data Architecture*. **Ce rekeyage reste à faire** ; il ne faisait pas partie du renommage.

### Ce que le renommage a cassé, et qu'il faut savoir avant de déployer

Le protocole a changé sans compatibilité ascendante — décision explicite : plus personne n'est sur l'ancien projet.

- Les clients web sont servis **par** l'API : même déploiement, bascule atomique.
- **L'application mobile ne l'est pas.** Un build installé avant ce déploiement reçoit des 404 sur chaque appel et ne voit plus la fin de Salon. Il faut publier la mise à jour mobile avec le déploiement de l'API, pas après.
- Les clés de stockage sur appareil et navigateur sont passées au namespace `vocaliz.` avec reprise à la lecture ; les métadonnées Stripe déjà écrites se reprennent par l'action `backfill_stripe_namespace`.

---

## Project Context Analysis

### Ce projet est un brownfield, et c'est le fait le plus important

Le code de ce dépôt vient du projet **Salon** — un produit **déployé, en fonctionnement, avec des données réelles**. Vocaliz n'en diffère que sur quatre points. Toute décision d'architecture qui l'ignorerait produirait du travail de reconstruction plutôt que de transformation.

```
DÉPLOYÉ ET CONSERVÉ            pile CloudFormation SalonApi · ca-central-1 · compte 006619322178
                               Aurora PostgreSQL · 43 migrations · données réelles
                               vocaliz.net et app.vocaliz.net · certificats ACM · DKIM SES
                               API Gateway HTTP + Lambda · VPC · instance NAT
                               EventBridge : InvoiceAdvertisers · ParticipantReport
                                             CheckXaiHealth · SweepExpiredSalons
```

**Décision du 2026-08-08 : rien n'est détruit.** Les domaines que Vocaliz doit servir sont déjà servis par cette pile, avec leurs certificats validés et leur DKIM en place. La base porte le schéma dont Vocaliz hérite. La pile est **renommée et transformée**, jamais recréée.

### Requirements Overview

**Functional Requirements :** 62 FR (PRD v2), dont 40 ajoutées lors de la révision du 2026-08-08. Le cœur architectural tient en quatre transformations et une continuité.

**Non-Functional Requirements :** neuf catégories — Performance, Security, **Durability**, **Confidentiality**, **Auditability**, **Observability**, **Testability**, **Modularity**, Integration. Les cinq en gras sont nouvelles ; NFR2 (non-conservation) a été abrogée.

**Périmètre réel :** l'audit des 44 stories contre le code livré donne **8 déjà livrées, 12 partiellement héritées, 24 à construire**. Voir [story-audit-2026-08-08.md](story-audit-2026-08-08.md).

### Les quatre écarts entre Salon et Vocaliz

| | Salon (déployé) | Vocaliz | Ampleur |
|---|---|---|---|
| **1. Topologie audio** | 1 room LiveKit, 1 agent partagé | **1 room par paire humain-interprète** + orchestrateur | refonte |
| **2. Vidéo** | aucune | **vidéo muette partagée**, 240p | ajout |
| **3. Facturation** | post-payée, essai en temps, tarif unique | **prépayée en millicents**, échantillonnage 5 s | remplacement |
| **4. Paliers** | expérience unique | **quatre paliers payants** | ajout |

Le premier écart est celui qui a motivé le projet : dans Salon, deux appareils proches l'un de l'autre produisaient du **larsen**, parce que les deux humains partageaient un flux audio.

### Technical Constraints & Dependencies

- **LiveKit Cloud managé** — transport WebRTC, SIP téléphonique, dispatch d'agents. Déjà intégré (`services/livekit_service.py`).
- **xAI** — `grok-voice-think-fast-1.0` pour les paliers Base à B, `2.0` pour le Mode C. Épinglé, jamais aliasé.
- **AWS ca-central-1** — Aurora Serverless, Lambda + API Gateway HTTP, Secrets Manager, SES, SNS, EventBridge, CloudWatch. **AWS CDK en TypeScript** (`infra/`), contrairement à la décision d'origine de ne pas recourir à l'infrastructure-as-code.
- **Stripe** — client, moyen de paiement enregistré, facturation des annonceurs. Conservé ; la logique de calcul change.
- **Expo / React Native** — client mobile ; page de jonction web servie par l'API.

### Cross-Cutting Concerns Identified

- **Aucun pivot linguistique.** L'émetteur fait l'original ; chaque traduction en dérive directement et est mise en cache par couple (tour, langue). Un Salon monolingue ne déclenche **aucune** traduction.
- **Deux ensembles de langues.** Les langues **parlées** sont l'intersection des adaptateurs d'interprète ; les langues **écrites** (sous-titres) forment un ensemble plus large.
- **Conservation d'un an** des journaux, chiffrement au repos, droits d'accès et d'effacement — obligations nouvelles, issues de l'abrogation de NFR2.
- **Le port Interprète** est la clé de voûte : il rend les paliers configurables, les tests de charge gratuits, et le fournisseur remplaçable.

---

## Décision d'Infrastructure : Transformer, Ne Pas Recréer

### Ce qui est conservé tel quel

| Ressource | Raison |
|---|---|
| **Zone Route53 `vocaliz.net`** | Les domaines cibles y sont déjà servis |
| **Certificats ACM** apex et app | Validés — une recréation impose une revalidation DNS |
| **Enregistrements DKIM SES** | Trois CNAME ; les recréer casse la délivrabilité du courriel le temps de la repropagation |
| **Aurora PostgreSQL** | Porte le schéma hérité et les données réelles. `DeletionProtection` est à **FALSE** et la rétention à **1 jour** — à corriger, voir ci-dessous |
| **VPC, sous-réseaux, instance NAT** | Aucune raison de les refaire |
| **`CDKToolkit`** | Bootstrap CDK **partagé** de la région — le supprimer casserait tout autre déploiement du compte |

### Où tourne quoi — correction d'une erreur de l'architecture précédente

`agent/livekit.toml` établit un fait que l'architecture du 28 juillet affirmait à l'envers :

```toml
[project]
  subdomain = "salon-sojjerdy"
[agent]
  id = "CA_y85UAcFFZPEj"
```

**Le worker d'interprète est hébergé par LiveKit Cloud Agents, pas par AWS.** C'est la raison pour laquelle il n'existe **aucun cluster ECS** dans le compte, alors que le document précédent décrivait un « worker sur ECS Fargate ».

| Composant | Où il tourne |
|---|---|
| **Interprètes** (N par Salon) | **LiveKit Cloud Agents** — le dispatch existe déjà, seule la cardinalité change |
| **API REST + migrations** | AWS Lambda derrière API Gateway HTTP |
| **Orchestrateur** ← neuf | **AWS ECS Fargate**, dans le VPC existant |
| Base | Aurora PostgreSQL |

L'orchestrateur est le **seul déployable AWS neuf**. Lambda ne convient pas : il tient un état par Salon et vit le temps d'une conversation.

### Ce qui change dans l'infrastructure

- **Ajout d'un service Fargate** pour l'orchestrateur, dans le VPC existant.
- **Cardinalité du dispatch d'agents** : un par participant au lieu d'un par salle. Le mécanisme (`dispatch_agent`) est inchangé.
- **Rien n'est retiré.** Les quatre écarts de Vocaliz sont additifs au niveau infrastructure.

### Correctifs relevés à l'inspection du 2026-08-08

**🔴 Protection de la base.** `DeletionProtection` est à **FALSE** et la rétention de sauvegarde à **un jour**. Conserver un an de journaux derrière une fenêtre de restauration d'une journée est incohérent — et une base sans protection de suppression porte ici des conversations transcrites, des adresses et des preuves de facturation d'annonceurs.

**🔴 Le compte AWS n'est pas dédié à ce projet.** L'utilisateur déployeur s'appelle `caraoke-deployer`, une zone `test12.net` cohabite, et cinq secrets appartiennent à un autre produit :

```
caraoke/xai-api-key · caraoke-dev/database-url · caraoke-dev/livekit
caraoke/stripe-secret-key · caraoke-dev/google-oauth
```

`CDKToolkit`, le bucket `cdk-hnb659fds-assets-*` et le dépôt ECR `cdk-hnb659fds-container-assets-*` sont le **bootstrap CDK partagé de la région**. Toute opération destructive à l'échelle du compte ou de la région est **proscrite** : elle emporterait des clés d'API et une base de production qui n'appartiennent pas à Vocaliz.

---

## Core Architectural Decisions

### Decision Priority Analysis

**Déjà décidé par l'héritage — à ne pas rouvrir.** Python et TypeScript, FastAPI sur Lambda via Mangum, PostgreSQL avec SQLAlchemy et Alembic, `snake_case` en base et `camelCase` sur le fil, LiveKit Cloud managé, AWS CDK, pytest avec base de test construite depuis les modèles, Plus Code à six chiffres. Ces choix ont du code derrière eux ; les remettre en cause coûterait plus que ce qu'ils rapportent.

**Décisions critiques — bloquent l'implémentation :**
1. Où vit le journal d'un Salon actif, et qui en est la source de vérité
2. Comment l'orchestrateur et les interprètes se parlent
3. Où se range le palier choisi par un participant
4. Comment se représente un solde prépayé sans jamais perdre un centième

**Décisions importantes — façonnent l'architecture :** hachage de mot de passe, chemin média de la vidéo, transport de l'état de parole, gestion d'état côté client.

**Décisions différées :** interface d'administration (commande en ligne au MVP), montée à 50 participants (conditionnée à des critères mesurés), tier institutionnel.

---

### Data Architecture

**Le journal reste en PostgreSQL, l'orchestrateur en tient une vue de travail.**

`utterances` et `utterance_translations` restent la **source de vérité**, comme aujourd'hui. L'orchestrateur charge le journal du Salon qu'il héberge et écrit en traversant — il ne devient jamais un second stockage.

*Pourquoi.* NFR8 exige la persistance et la reprise après panne ; un journal purement en mémoire les interdirait. Et l'endpoint `GET /{salon_id}/utterances` sert déjà les sous-titres et le transcript : deux stockages divergeraient au premier incident.

*Conséquence à accepter.* Aurora **descend à zéro ACU** et met une quinzaine de secondes à se réveiller. Le premier tour d'un Salon ouvert après une nuit calme paiera ce réveil. Le commentaire du CDK l'assume déjà pour l'API ; il vaut désormais pour le journal.

**L'identifiant d'un Salon : `salons.id`, et lui seul.**

La colonne existe déjà — `salons.id`, anciennement `sessions.id`. Aucune colonne n'est à créer.

⚠️ **La topologie multi-rooms casse le second identifiant.** Deux valeurs désignaient un Salon, et l'une devient fausse :

```
salons.id                   UUID    ✅ reste l'identifiant canonique
salons.livekit_room_name    String  ❌ UNIQUE et singulier — ne peut pas porter N rooms
salon_events.salon_name     String  ❌ CLÉ PRIMAIRE avec participant_identity
ad_broadcasts.salon_name    String  ⚠️  conservé pour nommer un Salon sur une facture
                                       après suppression du Salon
```

Avec une room par participant, **le nom de room désigne une room, plus un Salon**. Trois participants produisent trois noms différents pour une seule conversation. Deux ruptures en découlent :

- **`salon_events` ne peut plus se regrouper par Salon.** Sa clé primaire `(participant_identity, salon_name)` donnerait trois valeurs distinctes de `salon_name` pour un même Salon — et `participant_report.py` regroupe précisément là-dessus.
- **`salons.livekit_room_name` ne peut plus être unique ni singulier.** Un nom de room devient une propriété **de la participation**, pas du Salon.

**Décision :** `salons.id` devient le **seul** identifiant de Salon. `livekit_room_name` descend au niveau de la participation — il y en a désormais un par participant. `salon_events` est rekeyé sur `(participant_identity, salon_id)`. `ad_broadcasts.salon_name` reste tel quel : il n'identifie rien, il **nomme** un Salon sur une ligne de facture qui doit survivre à la suppression de celui-ci, et la topologie ne touche pas cet usage.

C'est une **migration de clé primaire sur une table portant des données réelles** : elle mérite sa propre story, et elle doit précéder tout travail qui lit `salon_events`.

**Nouvelle table : les curseurs.**

```
interpreter_cursors   (salon_id, participant_identity) → sequence, updated_at
```

Clé composite sur la paire, comme `salon_events` : un participant, un curseur, une position. `sequence` référence `utterances.sequence`, déjà monotone et unique par Salon — **rien de nouveau à ordonner**.

**Le palier se range sur la participation, pas sur le compte.**

Il va dans `salon_events`, aux côtés de `first_spoken_language` et `device_type`, et pour la raison que le modèle donne déjà pour ceux-là : *« the same person joins from a laptop at work and a phone on the train, and an account-level column would keep only the last of those and call it a fact about them »*. Quelqu'un peut prendre le Mode C pour une conversation qui compte et le Base pour la suivante.

**Le solde : des entiers, jamais un flottant — et des `BIGINT`, jamais des `INTEGER`.**

```
users.solde_offert_millicents    BIGINT · crédit de bienvenue et réactivations
users.solde_paye_millicents      BIGINT · argent versé, remboursable
users.total_cumulatif_millicents BIGINT · total payé à vie, jamais remis à zéro
consommation_cent_blocs          BIGINT · accumulateur, unité « cent × bloc de 5 s »
```

`500 ÷ 720` a un développement décimal illimité : aucune unité décimale ne le représente. L'accumulateur entier est donc la seule forme exacte, et la conversion en cents n'a lieu **qu'à la facturation**, par une division entière arrondie vers le bas.

**Pourquoi `BIGINT` et non `INTEGER`.** Le choix de compter en millicents et en cent·blocs — qui garantit l'exactitude — multiplie les valeurs par mille et par sept cent vingt. Un usager intensif y arrive vite :

```
2 h/jour × 365 jours = 730 h/an, au Mode B à 1500 ¢/h
  consommation_cent_blocs   730 × 720 × 1500  =  788 000 000 par an   → déborde en 3 ans
  total_cumulatif           730 × 1500 × 1000 = 1 095 000 000 par an  → déborde en 2 ans
                                                 (INTEGER : 2 147 483 647)
```

Un débordement sur un compteur de facturation est le pire cas possible : il ne lève **aucune alerte**, il produit un nombre **négatif**, et il se découvre en rapprochant les comptes plusieurs mois plus tard. `BIGINT` porte 9,2 × 10¹⁸ — plus de dix milliards d'années au même rythme.

> **Note de lecture.** `utterances.sequence` reste un `INTEGER`, et c'est correct : il est monotone **par Salon**, l'unicité portant sur le couple `(salon_id, sequence)`. Il faudrait 2,1 milliards de tours **dans un seul Salon** pour le déborder. Le volume de la table, lui, ne fait déborder aucun compteur — la clé primaire est un UUID.

`trial_seconds_used` et `billed_seconds` **sortent du modèle** — ils portent l'essai en temps et la facturation post-payée que le prépayé remplace. `billing_events` reste, comme journal d'encaissement.

**Migrations : Alembic, une par changement, modèles mis à jour dans le même commit.**

Ce n'est pas une convention de style. La base de test est construite **depuis les modèles**, et le code porte la cicatrice de cette leçon en deux endroits — `users.__table_args__` et `Invitation.__table_args__` — où une contrainte vivant uniquement dans une migration a été rencontrée pour la première fois **en production**.

**Aucun cache applicatif.** Les traductions sont déjà mises en cache là où il faut — dans `utterance_translations`, par couple (tour, langue). Ajouter un Redis dupliquerait un cache qui fonctionne, pour un produit où la donnée chaude tient dans un Salon.

**Volume des tables de conversation.** `utterances` et `utterance_translations` sont les seules tables dont la croissance suit l'usage plutôt que le nombre de comptes. Ordre de grandeur, à un tour toutes les cinq secondes :

```
100 usagers × 5 min/jour    ≈  1 M lignes sur l'année de rétention
5 500 usagers (seuil 1 M$)  ≈  60 M tours + ~120 M traductions
```

Deux conséquences, à traiter le jour où le second ordre de grandeur approche — pas avant :

- **La purge de rétention** (NFR8, un an depuis la création du Salon) devient l'opération la plus lourde de la base. Un partitionnement par mois la transforme en `DROP PARTITION` plutôt qu'en `DELETE` de dizaines de millions de lignes.
- **`utterance_translations` croît plus vite que `utterances`**, d'un facteur égal au nombre moyen de langues par Salon. Un Salon monolingue n'en produit aucune — c'est la diversité linguistique qui dimensionne cette table, pas le volume de conversation.

---

### Authentication & Security

**Deux voies d'authentification qui coexistent, aucune ne remplace l'autre.**

| Voie | Usage | État |
|---|---|---|
| **OTP par courriel** (SES) | inscription, connexion sans mot de passe | hérité, conservé |
| **Nom d'utilisateur + mot de passe** | connexion quand aucun identifiant n'est joignable | à construire (FR65) |
| **Vérification par carte Stripe** | **remboursement uniquement**, jamais accès au compte | à construire (FR65) |

**Hachage : Argon2id**, paramètres OWASP — `m = 19456 KiB`, `t = 2`, `p = 1`. C'est la première recommandation de la *Password Storage Cheat Sheet* de l'OWASP, devant scrypt puis bcrypt. Le produit n'a **aucun mot de passe existant** à migrer : l'argument habituel en faveur de bcrypt — la migration progressive au login — ne s'applique pas ici, ce qui rend le choix moderne gratuit.

**JWT à courte durée** via `python-jose`, comme aujourd'hui. Le secret est généré par le CDK et n'existe jamais dans le dépôt.

**Chiffrement au repos : celui d'Aurora, par KMS.** Il couvre le stockage, les instantanés et les sauvegardes. **Pas de chiffrement au niveau colonne** — le modèle explique pourquoi : *« column encryption would have forced a deterministic scheme on the key columns and ruled out every query but equality »*.

**La règle qui protège réellement le journal** n'est pas cryptographique : **aucun contenu de conversation dans les journaux applicatifs**. Un diagnostic ne référence que des identifiants et des longueurs. C'est par là que du texte chiffré en base reparaît en clair.

**Limitation de débit** : `slowapi`, déjà en place.

---

### API & Communication Patterns

**Trois chemins, trois natures — et ils ne se mélangent jamais.**

```
1.  CLIENT → API REST            FastAPI sur Lambda · HTTP · camelCase sur le fil
                                 Salons, invitations, soldes, paliers, comptes

2.  HUMAIN ⟷ INTERPRÈTE          LiveKit · AUDIO · une room par paire
                                 plus le canal de données de cette room :
                                 sous-titres, voyants, annonces système

3.  INTERPRÈTE ⟷ ORCHESTRATEUR   WebSocket · TEXTE seulement · une connexion par interprète
                                 tours de parole, curseurs, état de parole, métrage
```

**Pourquoi WebSocket entre interprètes et orchestrateur.** Le besoin est bidirectionnel et continu : l'interprète pousse les tours qu'il entend, l'orchestrateur pousse ceux des autres. Du HTTP imposerait de l'interrogation périodique sur un chemin où la latence est le risque n°1. Faire rejoindre l'orchestrateur dans chaque room LiveKit fonctionnerait, mais lui donnerait une identité média dans N rooms pour n'y transporter que du texte — une plateforme de média employée comme bus de messages.

**L'état de parole (FR74) emprunte le chemin 3, puis le chemin 2.** LiveKit publie nativement l'état de parole *dans une room* ; comme les humains n'en partagent aucune, l'orchestrateur relaie. C'est une gratuité perdue en changeant de topologie, et il fallait la remplacer explicitement.

**La vidéo (FR72) est un quatrième chemin, délibérément séparé.** Une room LiveKit dédiée, **vidéo seulement**, plafonnée à 200 kbps, sans aucune piste audio publiée. La séparer du chemin 2 est ce qui garantit que l'anti-écho par construction survive à l'ajout de la vidéo.

**Erreurs** : format `{detail: string}`, comme aujourd'hui. **Indisponibilité d'un fournisseur** : message explicite plutôt qu'échec silencieux (NFR3) — `service_health` et `xai_health` existent déjà.

---

### Frontend Architecture

**Pas de bibliothèque de gestion d'état.** `AuthContext` et `LanguageContext` suffisent, et le produit ajoute peu d'état global : un solde, un palier, un état de conduite. Introduire Redux ou Zustand pour trois valeurs coûterait plus en cérémonie qu'en clarté.

**Navigation** : React Navigation, déjà en place — `RootNavigator` arbitrant entre `AuthNavigator` et `AppNavigator`.

**Trois surfaces, un seul backend** : mobile natif (Expo), page de jonction web (`routers/guest_web.py`), et l'interface d'administration qui **n'existe pas** — l'octroi manuel de crédit passe par une commande en ligne.

**Les écrans à ajouter** : sélection des trois options (palier, vidéo, montant de recharge) à la création et à la jonction, solde et recharge, vignettes vidéo, voyants de parole.

> ⚠️ `mobile/AGENTS.md` : **Expo a changé — lire la documentation versionnée de v57.0.0 avant d'écrire du code.**

---

### Infrastructure & Deployment

Voir la section *Décision d'Infrastructure* ci-dessus pour le détail. En résumé :

| Composant | Hébergement | État |
|---|---|---|
| Interprètes (N par Salon) | **LiveKit Cloud Agents** | hérité, cardinalité à changer |
| API REST + migrations | AWS Lambda + API Gateway HTTP | hérité |
| **Orchestrateur** | **AWS ECS Fargate**, VPC existant | **neuf** |
| Base | Aurora Serverless v2, 0 à 2 ACU | hérité, protection corrigée le 2026-08-08 |
| CI/CD | GitHub Actions → CDK | hérité |

**Configuration** : les paramètres opérationnels de FR54 quittent les variables d'environnement pour une **table persistée**, modifiable sans déploiement. Les secrets restent dans Secrets Manager, avec échec au démarrage si l'un manque — jamais à la première requête.

---

### Decision Impact Analysis

**Séquence d'implémentation contrainte.** Chaque flèche est une dépendance réelle, pas une préférence :

```
orchestrateur (6.1)
   └→ port Interprète (6.2)
        └→ journal + curseurs (6.3)          ← étend utterances, ajoute interpreter_cursors
             └→ une room par participant (6.4)  ← LE PIVOT
                  ├→ adaptateur Base (6.7)      ← les paliers en dépendent
                  ├→ vidéo (6.13)               ← 4ᵉ chemin média
                  └→ voyants (6.15)             ← relais par l'orchestrateur

flux d'événements (8.1)
   └→ crédit offert (8.2) → paliers (8.3-8.5) → facturation (8.6) → prépayé (8.7)
                                                                        └→ vérification (8.8) → alerte (8.9)
```

**Une migration bloquante, à placer tôt.** Le rekeyage de `salon_events` de `(participant_identity, salon_name)` vers `(participant_identity, salon_id)` conditionne tout ce qui lit cette table — rapport de participants, ciblage publicitaire par `plus_code`, question de satisfaction. Elle porte sur des données réelles et doit **précéder la bascule multi-rooms**, faute de quoi les participations d'un même Salon se disperseront sous trois noms de room.

**Dépendances croisées à connaître :**

- **Les paliers exigent le port.** Sans lui, changer de modèle par palier est une constante du produit plutôt qu'un paramètre d'adaptateur.
- **Le prépayé exige la vérification périodique**, qui exige le métrage, qui existe déjà sous forme de heartbeat.
- **La vidéo et les voyants exigent la topologie multi-rooms.** Les construire avant n'aurait pas de sens : dans une room partagée, on voit et on entend déjà l'autre.
- **Le nettoyage de `mixed_audio_input.py` vient après 6.4**, jamais avant : c'est du code vivant tant que la room partagée existe.
- **Le mode conduite (6.16) est livré** mais doit être étendu **après** la vidéo et les voyants, puisqu'il les suspend.

---

## Travail de Nettoyage

Inventaire du 2026-08-08 : **aucune ressource AWS n'est inutilisée par Vocaliz.** Le nettoyage à faire est de schéma et de code.

### Schéma — trois colonnes mortes

| Colonne | Table | Constat |
|---|---|---|
| `target_countries` | `advertisers` | JSONB, **jamais eu de données** |
| `target_regions` | `advertisers` | JSONB, **jamais eu de données** |
| `circle` | `advertisers` | JSONB, **jamais eu de données** |

Le code le dit lui-même, dans `models/ad.py` : il existe **trois façons de désigner où une annonce peut être entendue, et c'est une de trop.**

```
ads_regions                   cellules listées sur l'annonce               → CONSERVÉ
advertisers_regions           régions nommées achetées par l'annonceur     → CONSERVÉ
  + region_google_plus_codes
advertisers.target_countries  ← les trois JSONB : à SUPPRIMER
  target_regions, circle
```

Les deux premiers répondent à la même question à des grains différents — une annonce couvrant une rue, un annonceur couvrant une ville — et se comparent tous deux à `salon_events.plus_code` sans géométrie. Le troisième exigerait un géocodage inverse qui n'existe pas ici, et c'est pourquoi il n'a jamais servi.

**Par migration Alembic**, avec les modèles mis à jour dans le même commit — la base de test étant construite depuis les modèles, un écart entre les deux se découvre en production.

### Code — un module sans objet

**`agent/src/mixed_audio_input.py`** mélangeait les entrées audio de plusieurs humains dans la room partagée. Avec **un humain par room**, il n'y a plus rien à mélanger : le module perd son objet en même temps que la room partagée.

À supprimer **avec ses tests** (`agent/tests/test_mixed_audio.py`), et pas avant que la topologie multi-rooms ne soit en place — c'est du code encore vivant tant que Salon tourne.

### Ce qui n'est PAS à nettoyer

- **Aucune ressource AWS.** Tout ce que la pile contient sert Vocaliz.
- **Les secrets `caraoke/*` et la zone `test12.net`** — ils appartiennent à un autre projet.
- **Le bootstrap CDK** — partagé par toute la région.
- **`friends`** — l'invitation d'un ami inscrit passe toujours par cette table.

---

## Starter Template Evaluation

### Il n'y a pas de starter à choisir

Cette question ne se pose pas ici, et il vaut mieux le dire que de la simuler. Vocaliz n'est pas un projet neuf : **la fondation est un produit déployé**, et la choisir consisterait à choisir de le jeter.

L'étape garde néanmoins son objet — recenser **les décisions techniques déjà prises pour nous**. Elles ne viennent pas d'un gabarit mais du code livré, ce qui les rend plus contraignantes, pas moins : un gabarit se remplace, un système en production se migre.

### La fondation réelle, avec ses versions

**`agent/` — worker d'interprète** · Python ≥ 3.11
```
livekit-agents[xai,silero,turn-detector]  ≥ 1.5.0    dispatch, VAD, détection de tour
numpy ≥ 2.4.6 · python-dotenv ≥ 1.0.0
pytest + pytest-asyncio                              13 fichiers de tests
```

**`api/` — API REST** · Python ≥ 3.12
```
fastapi ≥ 0.140 + mangum ≥ 0.19      FastAPI servi par Lambda derrière API Gateway HTTP
sqlalchemy ≥ 2.0 + alembic ≥ 1.16    ORM et migrations — 43 à ce jour
pydantic ≥ 2.0 + pydantic-settings   validation et configuration
python-jose[cryptography]            JWT
livekit-api ≥ 1.2                    provisionnement de rooms, dispatch, jetons
stripe ≥ 12.0                        paiement et facturation des annonceurs
openlocationcode ≥ 1.0.1             cellules Plus Code — géolocalisation à la maille
boto3 · slowapi · httpx · pypdf · beautifulsoup4
moto[sns]                            AWS simulé en test
```

**`mobile/` — client** · Expo ~57.0.8 · React Native 0.86 · React 19.2 · TypeScript 7.0
```
@livekit/react-native ^2.12 + @livekit/react-native-webrtc ^144.1
livekit-client ^2.21
expo-secure-store · expo-localization · expo-contacts · expo-keep-awake
@react-navigation/native ^7.3
@expo-google-fonts/playfair-display    la typographie serif de l'UX
```

> ⚠️ `mobile/AGENTS.md` porte une consigne à respecter : **Expo a changé — lire la documentation versionnée de v57.0.0 avant d'écrire du code.**

**`infra/` — infrastructure** · AWS CDK ^2.1031 · aws-cdk-lib ^2.170 · TypeScript ~5.6

### Les décisions que cette fondation a déjà prises

| Domaine | Décision héritée |
|---|---|
| **Langages** | Python côté serveur et agent · TypeScript côté client et infrastructure |
| **API** | FastAPI **sur Lambda** via Mangum — pas de serveur permanent pour le REST |
| **Données** | PostgreSQL, SQLAlchemy, migrations Alembic, `snake_case` en base |
| **Sérialisation** | JSON `camelCase` sur le fil via alias Pydantic, `snake_case` en Python |
| **Temps réel** | LiveKit Cloud managé — transport, SIP, dispatch d'agents |
| **Infrastructure** | **AWS CDK en TypeScript**, contrairement à la décision d'origine de s'en passer |
| **Tests** | pytest, base de test construite **depuis les modèles** — d'où la règle de déclarer les contraintes dans les modèles autant que dans les migrations |
| **Géolocalisation** | Plus Code à six chiffres, encodé à l'ingestion |

### Ce que la fondation ne fournit pas

Aucune de ces quatre choses n'existe, et c'est exactement le périmètre de Vocaliz :

```
1.  orchestrateur par Salon           aucun composant à état long ne tourne aujourd'hui
2.  port Interprète                   agent.py appelle xai.realtime.RealtimeModel en dur
3.  solde prépayé                     la facturation est post-payée
4.  vidéo                             aucune piste vidéo nulle part
```

**La première story d'implémentation reste donc une initialisation** — non d'un gabarit, mais du composant orchestrateur, qui est le seul déployable neuf (Story 6.1).

---

## Topologie Cible

### Le principe

> **Il n'existe aucun canal audio entre appareils.** Chaque humain converse vocalement avec son propre interprète IA, dans sa propre room LiveKit — l'audio est bien là, c'est le transport de cette conversation. Ce qui circule **entre les participants**, ce sont des **tours de parole en texte** via l'orchestrateur, et optionnellement une **vidéo muette**.

C'est ce qui supprime le larsen à la racine plutôt que de le combattre : il n'existe plus de chemin par lequel le haut-parleur d'un appareil puisse atteindre le microphone d'un autre. Deux téléphones posés côte à côte sur un bureau ne s'entendent plus, parce qu'ils ne diffusent plus rien qui vienne de l'autre.

```
                    ┌─────────────────────────────────────────┐
                    │           ORCHESTRATEUR (Fargate)        │
                    │  journal polyglotte · curseurs par       │
                    │  interprète · FCFS · condensation ·      │
                    │  saturation · métrage · pas de média     │
                    └───┬──────────────┬──────────────┬────────┘
                        │ texte        │ texte        │ texte
              ┌─────────┴────┐  ┌──────┴───────┐  ┌───┴──────────┐
              │  ROOM 1      │  │  ROOM 2      │  │  ROOM 3      │
              │ humain ⟷ IA  │  │ humain ⟷ IA  │  │ humain ⟷ IA  │
              │ AUDIO PRIVÉ  │  │ AUDIO PRIVÉ  │  │ AUDIO PRIVÉ  │
              └──────────────┘  └──────────────┘  └──────────────┘
                        ╲              │              ╱
                         ╲     VIDÉO MUETTE 240p     ╱
                          ╲   chemin média partagé  ╱
                           ╲    aucune piste audio ╱
                            ╲___________________ ╱
```

### Ce qui disparaît, et ce qui reste

**L'audio reste pleinement dans LiveKit Cloud** : c'est lui qui porte la conversation vocale entre un humain et son interprète IA, dans les deux sens. Ce qui disparaît, c'est la **room partagée** — aucun humain n'est jamais dans la même room LiveKit qu'un autre humain.

```
Salon    1 room · 2 humains + 1 agent · un seul flux audio pour tous   →  LARSEN
Vocaliz  N rooms · 1 humain + 1 agent chacune · audio privé par paire  →  larsen impossible
         + 1 chemin vidéo partagé, sans aucune piste audio
```

La distinction est celle-ci : **il y a de l'audio dans LiveKit, il n'y a pas de canal audio entre appareils.**

### Conséquences directes

| | |
|---|---|
| **FR17 (anti-écho)** | Sans objet — l'écho devient impossible par construction |
| **`mixed_audio_input.py`** | Hérité de la room partagée ; à réévaluer, probablement sans objet |
| **`livekit_room_max_participants`** | Devient **2 par room** (un humain, un agent) ; le plafond de participants du Salon se déplace sur l'orchestrateur |
| **Coût LiveKit** | N Salons d'agent au lieu d'une — la structure de prix par participant l'épouse (voir PRD, Technical Success) |
| **Vidéo** | Chemin média **distinct**, plafonné à 200 kbps, jamais persisté, sacrifié avant l'audio |

---

## Implementation Patterns & Consistency Rules

_Ces patterns ne sont pas proposés, ils sont **relevés**. Le dépôt porte 45 migrations, 760 tests et quatre surfaces livrées ; les conventions existent déjà et sont cohérentes. Les écrire ici a un seul but : empêcher qu'un agent en invente une seconde, parce que deux conventions concurrentes dans une base de code coûtent plus cher que n'importe laquelle des deux._

**Règle qui prime sur tout ce qui suit :** en cas de doute, lire le code voisin et l'imiter. Ce document décrit ce que le code fait ; là où les deux divergent, c'est le code qui a raison et ce document qui doit être corrigé.

### Nommage — base de données

Tout en `snake_case`. Tables au **pluriel**, colonnes au singulier.

```
salons · salon_events · utterance_translations · ad_broadcasts
salon_id · host_user_id · livekit_room_name · first_spoken_language
```

Clés étrangères : `<entité_au_singulier>_id`, jamais `fk_user` ni `userId`.

Objets nommés — le préfixe dit ce que l'objet **fait**, pas où il est :

| Préfixe | Sens | Occurrences |
|---|---|---|
| `ix_` | index de performance, ne peut rien refuser | 66 |
| `uq_` | unicité, **peut** refuser une écriture | 8 |
| `ck_` | contrainte de validation | 45 |
| `fk_` | clé étrangère nommée explicitement | 4 |

Puis `<table>_<colonnes>` : `ix_utterances_salon_spoken`, `uq_utterances_salon_sequence`, `ck_salon_events_user_type`.

> ⚠️ **Un objet nommé `uq_` ou `ck_` doit être déclaré sur le modèle, pas seulement dans la migration.** La base de test est construite depuis les modèles : une contrainte absente du modèle n'existe dans aucun test, et le code qui la viole passe toute la suite avant d'échouer devant un utilisateur. C'est arrivé — `uq_invitations_phone_pin_pending` ne vivait que dans la migration 022, et toutes les invitations de la plateforme ont répondu 500 pendant que 615 tests passaient. `api/tests/test_schema_visibility.py` l'interdit désormais.

### Nommage — API

Chemins au **pluriel**, paramètre positionnel en UUID nu :

```
GET  /salons/{salon_id}/utterances
POST /salons/{salon_id}/heartbeat
POST /invitations/{invitation_id}/accept
```

**Les champs JSON sont en `camelCase`, écrits littéralement dans les modèles Pydantic.** Aucun `alias_generator`, aucune conversion automatique :

```python
class SalonResponse(BaseModel):
    salonId: str
    livekitRoomName: str
    createdAt: str
```

La frontière est nette : `snake_case` en Python et en base, `camelCase` dès qu'un octet part vers un client. La conversion est manuelle et visible dans le schéma — un générateur d'alias la rendrait invisible, et un agent finirait par écrire les deux formes.

**Pas d'enveloppe de réponse.** L'objet est rendu directement, jamais `{data: …}`.

**Les dates sont des chaînes ISO 8601** produites par `.isoformat()`, jamais des horodatages numériques.

### Nommage — code

| | Python | TypeScript |
|---|---|---|
| fichier | `salon_lifecycle.py` | `salonsApi.ts` · `SalonCreationScreen.tsx` |
| fonction | `record_entry` | `createSalonFromUrl` |
| classe / composant | `SalonEvent` | `SalonCreationScreen` |
| variable | `salon_id` | `salonId` |

Composants React en `PascalCase`, fichier compris. Tout le reste en TS est `camelCase`.

### Structure

```
api/src/models/           une entité par fichier, nommé comme la table au singulier
api/src/schemas/          Pydantic, groupés par domaine
api/src/routers/          un routeur par ressource, préfixe déclaré dans le fichier
api/src/services/         logique métier, aucun import de FastAPI
api/tests/                test_<sujet>.py — jamais co-localisé
api/migrations/versions/  NNN_description_courte.py, numérotation continue
```

Un service ne connaît ni `Request` ni `HTTPException` sauf raison écrite : il doit rester appelable depuis une fonction Lambda de maintenance, ce que `migrate_handler.py` fait pour dix d'entre eux.

### Erreurs

`HTTPException(status_code=…, detail="Phrase complète.")` — une phrase en anglais, majuscule initiale, point final. Pas de code d'erreur, pas d'objet imbriqué.

```python
raise HTTPException(status_code=404, detail="Salon not found or access denied.")
```

**404 plutôt que 403 quand la ressource existe mais n'appartient pas à l'appelant.** Un 403 confirmerait l'existence de l'objet à quelqu'un qui n'a pas le droit de le savoir.

Codes employés : `401` non authentifié · `404` absent ou non autorisé · `409` état incompatible (Salon terminé, invitation déjà acceptée) · `410` définitivement parti.

### Journalisation

`logger = logging.getLogger(__name__)`, sans exception — 23 modules sur 23 depuis la correction du seul écart, qui portait en plus l'ancien nom de projet.

**Aucun contenu de conversation dans les journaux.** Les identifiants et les compteurs, jamais ce qui a été dit.

### Écritures qui ne doivent jamais bloquer

Un motif propre à ce produit, et le plus facile à casser par inadvertance. Les écritures d'observation — participations, langue entendue, métriques — sont **au mieux** : elles avalent leur exception, journalisent un avertissement, et rendent la main.

```python
try:
    ...
    db.commit()
except Exception:  # noqa: BLE001
    db.rollback()
    logger.warning("Could not record …", exc_info=True)
```

Ne jamais transformer cela en erreur remontée : échouer à noter une arrivée ne doit pas empêcher quelqu'un d'entrer dans une room.

> ⚠️ **Le prix de ce motif :** il cache aussi les vrais défauts. `record_first_language` a passé toute sa vie à lever une exception avalée par ce `except`, sans jamais rien écrire, et rien ne l'a signalé. **Toute fonction protégée ainsi doit avoir un test qui vérifie le chemin qui réussit.** C'est la contrepartie non négociable du motif.

### Événements du canal de données LiveKit

`{"action": "<verbe_au_passé>"}` en `snake_case` : `salon_ended`. Le producteur est `livekit_service.notify_room` ; les consommateurs sont l'agent, l'app mobile et les deux clients web. **Quatre consommateurs — un renommage se fait des cinq côtés dans le même commit.**

### Argent

Les montants sont des **entiers**, jamais des flottants. Les millicents pour le solde, les cents pour Stripe. Un `float` sur une somme est un défaut, pas un choix de style.

Les métadonnées écrites sur un objet Stripe passent par `stripe_metadata.namespaced()` et portent le préfixe `vocaliz_`. Un préfixe recopié à la main est appliqué inégalement, et l'écriture réussit avec la mauvaise clé.

### Ce que tout agent doit faire

- **Lire le code voisin avant d'écrire.** Ce document résume ; le code décide.
- **Déclarer sur le modèle toute contrainte qui peut refuser une écriture**, sans quoi aucun test ne la connaît.
- **Tester le chemin qui réussit** de toute fonction dont les erreurs sont avalées.
- **Écrire en `snake_case` côté serveur, en `camelCase` côté fil**, et rendre la conversion visible.
- **Ne jamais laisser de contenu de conversation atteindre un journal.**
- **Traiter les montants en entiers.**

### Anti-patterns, tous rencontrés dans ce dépôt

| À ne pas faire | Pourquoi |
|---|---|
| Contrainte créée en migration seulement | Invisible aux tests ; a déjà mis les invitations à 500 en production |
| `except Exception` sans test du chemin nominal | A rendu `record_first_language` muet depuis toujours |
| Renommer un jeton sans vérifier ce qu'il désigne | `sessionStorage` → `salonStorage` : `ReferenceError` à la connexion de l'hôte |
| Préfixe de namespace recopié à la main | Appliqué inégalement, et l'écriture réussit avec la mauvaise clé |
| Boucle f-string dans une migration | Les noms d'objets deviennent illisibles pour le relecteur et pour l'outillage |

---

## Project Structure

_L'arborescence existe déjà et n'est pas à créer. Ce qui suit dit **où chaque Epic atterrit** et **où passent les frontières** — c'est-à-dire ce qu'un agent doit savoir avant d'ajouter un fichier, et ce qu'il ne doit pas franchir._

### Où atterrit chaque Epic

| Epic | Atterrit principalement dans | Nature |
|---|---|---|
| **1 · Inscription & Identité** | `api/src/routers/auth.py` · `services/otp.py` · `services/jwt_service.py` · `mobile/src/contexts/AuthContext.tsx` | ✅ livré |
| **2 · Salon de Discussion Vocale** | `api/src/routers/salons.py` · `services/livekit_service.py` · `agent/agent.py` | ✅ livré, **amendé par 6** |
| **3 · Accès Invité** | `api/src/routers/guest_web.py` · `api/web/join.html` | ✅ livré, **amendé par 10** |
| **4 · Essai & Facturation** | `api/src/services/stripe_service.py` · `models/billing_event.py` | ✅ livré, **remplacé par 8** |
| **5 · Historique & Reconnexion** | `api/src/services/partner_service.py` · `routers/users.py` | ✅ livré |
| **6 · Socle Multi-Rooms** | **`orchestrator/`** — nouveau composant déployable, à la racine · `api/src/services/livekit_service.py` · `models/utterance.py` · `agent/agent.py` | 🔨 le cœur |
| **7 · Régulation & Observabilité** | `orchestrator/` · **`api/src/models/operational_setting.py`** (nouveau) | 🔨 |
| **8 · Modes & Paliers** | **`api/src/services/billing/`** (nouveau) · `models/user.py` · `services/stripe_service.py` | 🔨 remplace 4 |
| **9 · Régie d'Annonces** | `api/src/services/ad_auction_service.py` · `ad_billing_service.py` · `models/ad.py` | ⚠️ **hérité, à conserver** |
| **10 · Inscription Légère** | `api/src/routers/auth.py` · `services/invitation_service.py` · `api/web/` | 🔨 amende 1 et 3 |

> ⚠️ **Epic 9 est le piège de cette carte.** La régie existe déjà et fonctionne : enchère au second prix, ciblage par Plus Code, contrainte `ck_ad_broadcasts_billed_only_if_delivered` qui interdit de facturer une annonce non diffusée. Les stories de l'Epic 9 ont été écrites comme si de rien n'était et **dégraderaient** l'existant si elles étaient suivies littéralement. Voir `story-audit-2026-08-08.md`.

### Ce qui s'ajoute, et seulement cela

```
orchestrator/                         ← Epic 6 et 7. Un CINQUIÈME composant déployable,
    src/main.py                          à la racine, pas un sous-dossier de l'API.
    src/config.py                     santé, configuration par l'environnement, journalisation
    src/lifecycle.py                  reprise après éviction, drainage au déploiement
    src/journal.py                    écriture et lecture du journal polyglotte
    src/cursors.py                    un curseur par interprète ; retard = tête − curseur
    src/interpreter.py                le port : InterpreteS2S · InterpreteBase · InterpreteFake
    src/saturation.py                 seuils par room, condensation, blocage d'entrée
    Dockerfile                        image conteneur
    ecs/task-definition.json          définition de tâche écrite à la main, pas de CDK
    tests/

api/src/services/billing/             ← Epic 8. Le prépayé remplace le post-payé.
    ledger.py                         millicents, accumulateur entier, report de reste
    sampler.py                        prélèvement toutes les 5 s
    coverage.py                       vérification de couverture, arrondie à la hausse

api/src/models/operational_setting.py ← Epic 7. Seuils modifiables sans déploiement.
```

> ⚠️ **Correction du 2026-08-08.** Ce document plaçait d'abord l'orchestrateur dans `api/src/services/orchestrator/`. C'était faux : les critères d'acceptation de la Story 6.1 exigent **un composant déployable distinct**, avec son `Dockerfile`, sa définition de tâche ECS Fargate et son propre cycle de vie — un sous-dossier de l'API ne peut satisfaire aucun des trois. L'orchestrateur a besoin d'un processus long qui survit à une requête HTTP ; l'API est une Lambda. C'était une contradiction de fond, pas une préférence de rangement.
>
> **Un attendu de la Story 6.1 reste néanmoins faux :** elle place l'orchestrateur sur ECS *« au même titre que le worker d'interprète »*. Le worker d'interprète n'est **pas** sur ECS — `agent/livekit.toml` le déploie sur LiveKit Cloud Agents, et c'est pourquoi aucun cluster ECS n'existe dans ce compte. La conclusion de la story tient — l'orchestrateur va bien sur ECS Fargate — mais **l'analogie qui la justifie est fausse, et le cluster est à créer**, pas à rejoindre.

Rien d'autre ne se crée. Toute autre fonctionnalité s'ajoute à un fichier existant : `models/` gagne des colonnes, `routers/salons.py` gagne des routes, `services/` gagne des fonctions.

### Frontières, et ce qu'elles interdisent

```
                    mobile/          api/web/         agent/
                       │                │                │
                       └──── HTTP ──────┴──── HTTP ──────┘
                                    │
                            api/src/routers/     ← HTTP uniquement
                                    │              valide, autorise, traduit en erreurs
                            api/src/services/    ← toute la logique métier
                                    │              ne connaît ni Request ni HTTPException
                            api/src/models/      ← schéma
                                    │
                              Aurora PostgreSQL
```

**Un service n'importe jamais de FastAPI.** La règle a une raison mesurable : `migrate_handler.py` appelle dix services depuis une Lambda de maintenance, sans requête HTTP. Un service qui lève une `HTTPException` casse ce chemin.

**Un routeur ne contient pas de logique métier.** Il valide, autorise, délègue, traduit. La preuve qu'on a franchi la limite : le besoin d'un test qui monte un client HTTP pour vérifier une règle de calcul.

**L'agent ne touche jamais la base.** Il passe par l'API avec le jeton de l'hôte. C'est ce qui permet de l'héberger chez LiveKit Cloud plutôt que dans le VPC.

**L'orchestrateur ne parle pas à xAI.** Il parle au port `Interprete` — NFR6. Un appel direct au fournisseur depuis l'orchestrateur rendrait `InterpreteFake` inutile et les tests de charge impossibles.

### Où vit quoi, dans les grandes lignes

```
api/
  src/
    main.py                 assemblage FastAPI, montage des routeurs
    migrate_handler.py      migrations + dix actions de maintenance (Lambda)
    config.py               pydantic-settings, une seule source des paramètres
    database.py             engine, SessionLocal, get_db
    routers/                auth · salons · invitations · sources · users · admin · guest_web
    services/               logique métier + les deux nouveaux sous-dossiers
    schemas/                Pydantic, camelCase vers le fil
    models/                 SQLAlchemy, snake_case
  migrations/versions/      NNN_description.py — 45 révisions, numérotation continue
  tests/                    49 fichiers, test_<sujet>.py
  web/                      host.html · join.html · index.html · report.html + i18n/

agent/
  agent.py                  l'interprète LiveKit ; instructions, outils, cycle de vie
  src/                      captions · mixed_audio_input · opening
  livekit.toml              déploiement LiveKit Cloud Agents — pas AWS

mobile/
  src/screens · components · contexts · hooks · navigation · services · i18n · theme
  app.json                  identité, slug, projectId, updates

infra/
  lib/salon-api-stack.ts    la pile entière — un seul fichier, volontairement
  bin/salon.ts              point d'entrée CDK
```

### Deux frontières de déploiement à ne pas confondre

**`api/web/` est servi par l'API.** Les clients web et l'API basculent ensemble, atomiquement. Un changement de protocole n'y pose aucun problème.

**`mobile/` ne l'est pas.** Il se publie par EAS, indépendamment. Tout changement de contrat — chemin d'URL, forme de réponse, action du canal de données — casse les installations qui n'ont pas suivi. C'est la seule frontière du projet où la compatibilité ascendante se pose vraiment, et elle s'est déjà posée lors du renommage.

**`agent/` non plus.** Il tourne sur LiveKit Cloud Agents et se déploie par `lk agent deploy`. Un `cdk deploy` ne le met pas à jour.

---

## Architecture Validation

_Validation faite par vérification, pas par relecture. Les chiffres ci-dessous sortent d'un recoupement programmatique du PRD et des epics, et les défauts trouvés ont été corrigés avant d'écrire cette section._

### Couverture des exigences

| | Résultat |
|---|---|
| FR déclarées au PRD v2 | **68** |
| FR rattachées à un Epic | **68 — aucune orpheline** |
| FR rattachées mais retirées du PRD | 7 (`FR2`, `FR9`, `FR17`, `FR19`, `FR22`, `FR23`, `FR27`) |
| NFR déclarées | **9** |
| NFR rattachées à un Epic | **9 — aucune orpheline** |

Les sept FR retirées restent dans la carte de couverture, marquées `⛔ SANS OBJET` ou `⛔ SUPPRIMÉE PAR`. C'est volontaire : elles ont été implémentées et livrées, elles existent dans le code, et un agent qui rencontre `FR22` dans un commentaire doit pouvoir apprendre qu'elle a été remplacée par FR40 plutôt que de conclure à une erreur.

### Deux défauts trouvés pendant la validation

**La carte de couverture annonçait les anciens tarifs.** `FR33` disait encore `Base 2$ / A 5$ / B 10$ / C 15$` alors que le bloc de paramètres et le PRD portent les prix majorés de la commission des magasins — `3 / 7,50 / 15 / 22,50`. Un agent lisant la carte plutôt que le PRD aurait codé la mauvaise grille tarifaire. Corrigé.

**Deux occurrences de « Salon Salon »** subsistaient du renommage. Corrigées.

### Cohérence des décisions

**Le port Interprète et les deux jeux de langues tiennent ensemble.** Les langues parlées sont l'intersection des adaptateurs, la plus restrictive étant `InterpreteS2S`. C'est ce qui garantit que passer de Base au Mode C ne retire jamais une langue à personne — la propriété que le produit promet. Les sous-titres écrits, eux, tirent d'un ensemble plus large, ce qui est cohérent : traduire du texte n'a pas les contraintes de la voix.

**Le journal sans langue pivot et la topologie multi-rooms se renforcent.** Chaque traduction part de l'original émis ; en Salon monolingue, aucune traduction n'a lieu. Le coût et la latence suivent la diversité linguistique, jamais le volume de conversation — ce qui est exactement le comportement voulu pour le parcours principal, qui est monolingue.

**Le journal et les curseurs suffisent à l'ordre FCFS.** `utterances.sequence`, monotone par Salon, **est** l'ordre d'arrivée. Un curseur par interprète donne le retard par simple soustraction. Aucune file d'attente n'est nécessaire, et en introduire une créerait une seconde source de vérité sur le même ordre.

**Le prépayé en millicents est cohérent avec l'échantillonnage à 5 s.** L'accumulateur entier reporte le reste d'un prélèvement au suivant ; la facturation arrondit vers le bas aux blocs complets, la vérification de couverture arrondit vers le haut. Les deux arrondis vont dans le sens qui protège le client, ce qui est le point.

### Contradiction résiduelle, assumée

**NFR8 abroge la promesse d'origine de NFR2.** Le produit promettait de ne conserver aucun transcript ; il conserve désormais les journaux un an à compter de la création du Salon, pour la reprise après panne et la preuve de diffusion des annonces. Ce n'est pas une incohérence à résoudre mais une décision à assumer publiquement : **la politique de confidentialité doit dire ce que NFR8 fait**, et le dire avant le premier utilisateur réel.

### Ce que l'architecture ne couvre pas encore

| Manque | Conséquence |
|---|---|
| **Rétention de `salon_events`** | Le modèle le dit lui-même : la ligne porte un courriel, un téléphone, parfois une position approximative, et *« elle mérite une règle de rétention ; il n'y en a aucune »*. NFR8 couvre les journaux, pas les participations. |
| **Réamorçage du pool de codes téléphoniques** | Aucune action ne l'alimente. FR57 (invitation téléphonique) ne peut pas fonctionner tant que `code_available` est vide. |
| **Charge au-delà de 3 participants** | Le plafond est une valeur de configuration, et le franchir est conditionné à des critères mesurés. L'infrastructure de test de charge est prévue mais pas construite. |

### Prêt pour l'implémentation

L'architecture est **suffisante pour démarrer**, et les trois manques ci-dessus ne bloquent aucune des 48 stories restantes : le premier est une dette de conformité, le deuxième bloque une seule FR, le troisième conditionne un palier futur.

Ce qui doit être fait **avant** toute story de l'Epic 6 : rien. Le rekeyage de `salon_events`, qui était la migration bloquante, est livré (migration `045`).

---

_Document d architecture complet — 8 etapes. Vocaliz, 2026-08-08._

---

## L'orchestrateur ne voit jamais d'audio — décision du 2026-08-09

_La deuxième décision structurante après la topologie elle-même, et celle qui range tout le reste._

> **`agent/`** — audio ↔ texte. Il tient la room LiveKit, la session temps réel xAI, et **l'interprète**. C'est le seul composant qui entend et qui parle.
>
> **`orchestrator/`** — **texte seulement**. Journal, curseurs, ordre, traduction, condensation, saturation, annonces, présentations. Pas un octet d'audio ne le traverse.

### Le trou que cette décision comble

`InterpreteS2S` vivait dans l'orchestrateur et réclamait un `RealtimeSession` — écouter un humain, lui parler. **Rien ne construisait le vrai.** La Story 6.2 l'a signalé et renvoyé à la 6.4, qui l'a renvoyé plus loin. Il ne pouvait pas y être construit : l'audio arrive par la room LiveKit, qui est chez l'agent.

Deux issues existaient, et elles n'étaient pas équivalentes.

**Faire relayer l'audio par l'agent jusqu'à l'orchestrateur** aurait préservé le rangement du code écrit — 861 tests portent sur des interprètes dans l'orchestrateur — au prix d'un aller-retour réseau supplémentaire dans le chemin audio : humain → LiveKit → agent → orchestrateur → xAI, et retour, à chaque tour de parole. **La latence est ce que ce produit vend.** Payer un saut réseau par tour pour préserver un rangement est le mauvais côté du marché.

**L'interprète descend donc dans l'agent**, qui a déjà le SDK et une session xAI qui fonctionne. Le chemin audio redevient le plus court possible.

### Ce que cela change vraiment : l'orchestrateur sert au lieu de pousser

C'est la conséquence à ne pas manquer. `Salon.deliver()` appelait `interprete.render()` directement. Cet appel devient inter-processus, donc il disparaît : l'orchestrateur ne pilote plus personne.

```
AVANT   orchestrateur → interprète.render(...)        un appel en mémoire

APRÈS   agent → « que dois-je à mon humain ? »        HTTP, texte
        orchestrateur → une liste ordonnée, dans la langue de l'écoutant
        agent → la dit avec son propre interprète
        agent → « j'ai dit jusqu'à N »                le curseur avance
```

**Rien de la logique textuelle ne bouge.** Les créneaux publicitaires, les présentations de la Story 6.9, la condensation, la saturation, le découpage à 500 caractères, l'ordre d'arrivée — tout reste dans l'orchestrateur, parce que tout cela décide **quoi dire**, jamais **comment le prononcer**. Ce qui descend dans l'agent, c'est uniquement l'acte de parler.

### Pourquoi cette ligne est la bonne, et pas seulement commode

Elle se vérifie d'un coup d'œil : **un octet d'audio dans `orchestrator/` est un défaut.** Un garde-fou peut l'affirmer, comme celui qui interdit déjà un SDK fournisseur sous `src/`.

Elle explique aussi pourquoi le port `Interprete` était une bonne idée dès le départ, et pourquoi il survit au déménagement : l'orchestrateur n'a jamais eu besoin de savoir *comment* on parle, seulement qu'on parle. Le port passe de « frontière entre deux modules » à « frontière entre deux processus », ce qui est exactement ce qu'un port est censé pouvoir devenir.

### Ce que le déménagement coûte

`src/interprete/` — le port, `InterpreteS2S`, `InterpreteBase`, `InterpreteFake` et la liste des langues — descend dans `agent/`. Les tests de contrat suivent. L'orchestrateur garde `journal/`, `salon/` moins le rendu, `settings/`, `load/` et `cohorts`.

`adapters/livekit_rooms.py` reste discutable et reste où il est : provisionner une room est un appel de plan de contrôle, pas de l'audio. Si cette ligne devait bouger un jour, ce serait vers l'API, qui crée déjà les rooms à la création d'un Salon.

### Comment l'inversion a été faite : un script est une voix qui enregistre

L'inversion pousser→servir aurait pu coûter une réécriture du conducteur. Elle n'en a coûté aucune, et la raison mérite d'être écrite parce qu'elle est réutilisable.

`Salon.deliver()` ne parlait pas à un interprète : il parlait à **trois verbes** — `render`, `insert_annonce`, `condense`. Ces trois verbes sont un port en eux-mêmes, plus étroit que `Interprete`, dont ils excluent précisément le seul verbe qui touche à l'audio : `ingest`. C'est `Voice`, dans `src/salon/script.py`.

`Script` est une `Voice` qui écrit au lieu de dire. Le siège tient l'une ou l'autre :

```python
@property
def voice(self) -> Voice:
    return self.script if self.script is not None else self.interpreter
```

Toute règle du conducteur passe par `seat.voice` et **aucune ne sait laquelle elle a obtenue**. Les créneaux publicitaires, les présentations, le seuil de condensation, le plafond de monologue, les annonces retenues : le même code produit la livraison en mémoire et le script servi. Ils ne peuvent pas diverger, parce qu'il n'y en a qu'un.

Ce que cela permet d'affirmer par un test, et qui est l'assertion sur laquelle tout le reste repose : **un script joué dit exactement ce que la livraison aurait dit** — mêmes lignes, même ordre, mêmes langues, présentations comprises. Deux Salons pilotés à l'identique, l'un qui livre, l'autre qui sert ; les deux interprètes finissent indiscernables.

Un second garde-fou interdit à `conductor.py` d'appeler `seat.interpreter.render` — une règle qui contournerait `seat.voice` fonctionnerait parfaitement en mémoire et ne dirait **rien du tout** sur le fil. Silence pour ce participant, suite de tests toujours verte : exactement la panne qu'un garde-fou existe pour attraper.

**Le curseur avance à la remise du script, pas à la confirmation de l'agent.** Cela ressemble à un message perdu en puissance et n'en est pas un : dans cette topologie une room tient un humain et son agent, donc un agent qui meurt emporte la room, et il ne reste personne pour avoir manqué quoi que ce soit. Livrer deux fois, ce que l'autre choix risque, est en revanche une panne qu'un auditeur remarque — il ne distingue pas une répétition de quelqu'un qui redit la même chose.

Il reste donc **deux appels HTTP et non trois** : demander son script, rapporter ce que l'humain a dit.

### Qui tient quel Salon, et pourquoi c'est écrit

Un Salon est fait de trois choses, pas de deux. L'hôte crée sa room LiveKit et son Salon d'un même geste ; l'API désigne dans la foulée l'orchestrateur qui prend la conversation, et écrit son adresse dans `salons.orchestrator_url`.

**Écrite plutôt que déduite.** Un Salon est étatique là où une room ne l'est pas : le journal, la position de chaque lecteur, qui a été présenté à qui. Une seule instance tient cela à la fois, et toute autre instance répondant pour le même Salon servirait une seconde version, plus vide, de la même conversation. Un répartiteur en tourniquet produirait exactement cela. Tous les agents d'un Salon doivent joindre la même adresse, et cette adresse est un fait à propos de ce Salon.

**Jamais sur le chemin critique.** L'appel est un `PUT` idempotent, et son échec — injoignable, en drain, lent, absent — n'empêche pas le Salon de s'ouvrir. Il s'ouvre sans traduction et la colonne nulle le dit franchement. Un hôte ne doit pas être arrêté parce qu'un second service redémarre.

**Nul est aussi l'état normal aujourd'hui**, aucun orchestrateur n'étant déployé. `ORCHESTRATOR_BASE_URL` vide rend l'appel inerte : aucune requête n'est faite. Une adresse par défaut ne résolvant vers rien transformerait chaque création de Salon en attente d'un refus de connexion, ce qui dit « pas encore construit » plus mal que de ne rien faire.

`orchestrator_url` redevient nul quand l'instance qui tenait le Salon est drainée sans reprise. Le journal survit à cela (NFR8), l'affinité non — et cette asymétrie est précisément ce qui fait de l'affinité une préférence plutôt qu'une condition de survie.
