---
stepsCompleted: [1, 2, 3, 4]
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
