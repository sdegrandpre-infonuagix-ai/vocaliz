---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
status: 'complete'
completedAt: '2026-07-28'
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/ux-design-specification.md', '_bmad-output/planning-artifacts/product-brief-salon-2026-07-25.md']
workflowType: 'architecture'
project_name: 'salon'
user_name: 'BMad'
date: '2026-07-28'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements :** 31 FR organisées en 6 catégories — Création de Session & Invitation (5), Expérience de Discussion Vocale (6), Traduction Multilingue (6), Compte & Facturation (6), Retour d'Expérience & Fin de Session (4), Compte & Historique (4). Le cœur architectural : une infrastructure temps réel voix-à-voix (LiveKit + agent xAI), un système d'invitation multi-canal (notification in-app / SMS), et un système de facturation à l'usage (essai gratuit + paiement Stripe post-essai).

**Non-Functional Requirements :** Aucun seuil de performance formel (à valider empiriquement) ; sécurité axée sur la non-persistance (aucun transcript conservé, paiement tokenisé via Stripe) ; intégration avec dégradation gracieuse en cas d'indisponibilité de xAI/LiveKit/Stripe.

**Scale & Complexity :**
- Primary domain : application mobile temps réel + backend voix/téléphonie, avec une couche de facturation à l'usage
- Complexity level : **faible à l'échelle utilisateur** (2 participants max par session, solopreneur), mais **complexité d'intégration élevée** — quatre dépendances tierces critiques (xAI, LiveKit, Stripe, passerelle SMS) qui doivent toutes coopérer de façon fiable
- Estimated architectural components : ~5 (client mobile natif, backend orchestrateur, worker d'agent LiveKit/xAI, service de facturation/métrage, service de messagerie SMS/notification)

### Technical Constraints & Dependencies

- **xAI via LiveKit Agents :** intégration confirmée via le plugin `livekit-agents[xai]` (Python ou Node.js) — le modèle `xai.realtime.RealtimeModel` sert de composant LLM au sein d'une `AgentSession` LiveKit, avec sélection de voix (ex : "Ara"). Grok expose speech-to-speech réaliste (compatible API OpenAI Realtime), LLM, text-to-speech et speech-to-text bas-latence. Requiert une variable d'environnement `XAI_API_KEY`.
- **LiveKit Cloud (managé) :** gère le transport WebRTC, l'équilibrage de charge, les serveurs TURN, et l'intégration SIP téléphonique optionnelle — pas d'auto-hébergement de l'infrastructure LiveKit, pour éviter la charge opérationnelle inutile à un solopreneur
- **Infrastructure d'hébergement : AWS** — réservée au code propriétaire : le worker d'agent xAI (plugin `livekit-agents[xai]`) déployé sur **ECS Fargate** (pas de gestion de serveurs, pas de Lambda vu les connexions WebRTC persistantes de longue durée), et le backend de facturation/métrage. Définition de tâche ECS écrite à la main (JSON simple), sans outil d'infrastructure-as-code (Terraform/CDK) pour le MVP.
- **Stripe :** paiement tokenisé, déclenché seulement après épuisement de l'heure d'essai gratuite
- **Passerelle SMS** : livraison des invitations (contacts téléphone), liens d'installation post-session
- **Aucune base de données existante** — projet greenfield complet
- **Contrainte de ressources** : solopreneur, donc priorité à une architecture simple et peu de pièces mobiles

### Cross-Cutting Concerns Identified

- **Métrage du temps de conversation** (FR20) traverse presque tout le cycle de vie d'une session — doit être fiable même en cas de déconnexion/reconnexion, et alimente directement la facturation Stripe
- **Détection de langue et traduction** touchent la quasi-totalité de la catégorie "Expérience de Discussion Vocale" — c'est le sous-système le plus complexe techniquement (risque prioritaire déjà identifié dans le PRD), directement porté par le `RealtimeModel` xAI au sein de l'`AgentSession` LiveKit
- **Politique de non-persistance** (aucun transcript stocké) doit être respectée uniformément — y compris pour la question de satisfaction et l'historique (qui ne garde que les métadonnées de session, pas le contenu)
- **Double authentification légère** : téléphone vérifié (utilisateurs inscrits) vs accès anonyme à usage unique (invités web) — deux chemins d'identité à maintenir cohérents

## Starter Template Evaluation

### Primary Technology Domain

Deux domaines distincts : (1) application mobile React Native/Expo (iOS/Android), (2) worker d'agent backend LiveKit+xAI déployé sur AWS ECS Fargate.

### Starter Options Considered

**Pour le worker d'agent backend :**
- **Python via `lk app create --template agent-starter-python`** (CLI officiel LiveKit) — scaffold complet : structure de projet, Dockerfile, `.env.example`, config `livekit.toml`
- **Node.js via `agent-starter-node`** — équivalent existe, mais le plugin xAI Node.js (`@livekit/agents-plugin-xai`) est épinglé à une version nettement plus ancienne (v1.2.4 vs 1.5.x en Python) et souffre de bugs connus non résolus (paramètre `instructions` non transmis, paramètres température/modèle manquants)

**Pour les clients mobiles :**
- **`npx create-expo-app`** (CLI officiel Expo) — scaffold un projet React Native managé, prêt pour EAS Build/Submit. Le SDK LiveKit React Native (`@livekit/react-native`) gère la connexion aux salles LiveKit Cloud sur les deux plateformes depuis un seul codebase

### Selected Starter: `agent-starter-python` (LiveKit CLI)

**Rationale for Selection :**
Le plugin xAI en Python est significativement plus mature et fiable que son équivalent Node.js — choix clair pour un solopreneur qui ne peut pas se permettre de déboguer les bugs d'un plugin encore instable. Le starter officiel scaffold directement ce dont on a besoin (Dockerfile prêt pour conteneurisation, structure de projet standard) sans réinventer la configuration. Les extras `silero` (détection d'activité vocale) et `turn-detector` sont inclus dès l'installation — nécessaires pour que l'ordre de parole par silence (FR9) fonctionne correctement dès le départ, pas seulement le plugin xAI seul.

**Initialization Command:**

```bash
lk app create --template agent-starter-python
uv add "livekit-agents[xai,silero,turn-detector]"
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime :** Python, gestion des dépendances via `uv`
**Build Tooling :** Dockerfile inclus, prêt à containeriser pour ECS Fargate
**Code Organization :** Structure standard d'un worker d'agent LiveKit (session, handlers, config)
**Development Experience :** `.env.example` pour les clés (`XAI_API_KEY`, credentials LiveKit Cloud), `livekit.toml` pour la config de build

**Note technique :** Le dépôt communautaire `agent-deployment` (exemples ECS/K8s/Fly.io) est explicitement marqué déprécié/non maintenu en 2026 — la définition de tâche ECS Fargate sera écrite à la main (JSON simple, sans Terraform/CDK) en suivant le pattern Dockerfile standard du starter officiel, plutôt que copiée d'un exemple tiers obsolète.

**Note :** L'initialisation du projet avec ces commandes devrait être la première story d'implémentation (Story 1.1).

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation) :** Base de données, méthode d'authentification, style d'API, hébergement du backend REST, framework client mobile
**Important Decisions (Shape Architecture) :** Approche de mise en cache, gestion d'état client, stratégie de scaling
**Deferred Decisions (Post-MVP) :** Cache Redis, infra-as-code (Terraform/CDK), observabilité tierce

### Data Architecture

- **Base de données :** PostgreSQL (version 16 ou 17, selon le support Aurora Serverless v2 au moment de l'implémentation — PostgreSQL 18.4 est la version communautaire la plus récente [postgresql.org](https://www.postgresql.org/docs/release/), mais Aurora traîne généralement d'une version)
- **Hébergement DB :** Amazon Aurora Serverless v2 (PostgreSQL) — scale à quasi-zéro au repos, cohérent avec le principe de coût minimal
- **Modélisation :** schéma relationnel simple — `users`, `sessions` (métadonnées seulement, jamais de transcript), `friends`, `billing_events` (minutage précis FR20)
- **Validation :** Pydantic (écosystème FastAPI/Python du backend)
- **Migrations :** Alembic
- **Cache :** aucun pour le MVP, Redis déferré post-MVP

### Authentication & Security

- **Authentification :** OTP par SMS uniquement (AWS SNS), pas de mot de passe/courriel — plus simple que Cognito pour ce flux "téléphone seul"
- **Autorisation :** JWT à courte durée de vie pour utilisateurs inscrits ; token à usage unique pour la jonction anonyme LiveKit (FR5)
- **Sécurité API :** limitation de débit sur OTP et invitations
- **Chiffrement :** TLS partout, chiffrement au repos Aurora, tokenisation Stripe (aucune donnée de carte stockée)

### API & Communication Patterns

- **Style d'API :** REST
- **Documentation :** OpenAPI/Swagger auto-généré (FastAPI, v0.140.x [fastapi.tiangolo.com](https://fastapi.tiangolo.com/release-notes/))
- **Gestion d'erreurs :** codes HTTP standards + enveloppe JSON cohérente
- **Communication inter-services :** client mobile ↔ API REST ; API REST ↔ LiveKit Cloud (provisioning de salles) ; LiveKit Cloud ↔ worker d'agent xAI (dispatch d'agent LiveKit)

### Frontend Architecture

- **Client mobile :** React Native via Expo, un seul codebase TypeScript pour iOS/Android, déployé via Expo Application Services (EAS Build, EAS Submit) — React Native Paper pour les composants Material 3
- **Connexion temps réel :** SDK `@livekit/react-native` pour la connexion aux salles LiveKit Cloud — nécessite un **Expo Development Build** dès le départ (pas Expo Go), puisque l'intégration WebRTC inclut du code natif incompatible avec le sandbox Expo Go standard
- **Gestion d'état :** state/context React natif — aucun état complexe requis vu le nombre restreint d'écrans, pas de Redux/MobX
- **Page de jonction web anonyme (Journey 2) :** page statique minimale (HTML/JS + SDK LiveKit JavaScript), hébergée sur S3+CloudFront

### Infrastructure & Deployment

- **Backend REST :** AWS Lambda + API Gateway — sans serveur, coût quasi nul à faible volume
- **Worker d'agent xAI :** AWS ECS Fargate
- **Client mobile :** Expo Application Services (EAS) pour build et soumission aux stores (App Store, Google Play)
- **Secrets/config :** AWS Secrets Manager
- **CI/CD :** GitHub Actions
- **Monitoring :** CloudWatch Logs natif
- **Scaling :** Lambda auto-scale trivialement ; service ECS Fargate avec auto-scaling basé sur les tâches actives

### Decision Impact Analysis

**Implementation Sequence :**
1. Initialiser le worker d'agent depuis le starter LiveKit Python (Story 1.1)
2. Initialiser le projet mobile via `npx create-expo-app` + Expo Development Build (Story 1.2)
3. Schéma de base de données + migrations Alembic
4. API REST (auth OTP, gestion de session, facturation)
5. Provisioning de salles LiveKit depuis l'API REST
6. Client mobile React Native (écrans + intégration `@livekit/react-native`)
7. Page de jonction web anonyme

**Cross-Component Dependencies :** Le worker d'agent xAI dépend du provisioning de salle effectué par l'API REST ; la facturation Stripe dépend du métrage précis (FR20) qui doit être fiable avant que FR19/FR22 puissent être implémentées correctement.

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified :** 5 zones où des agents IA différents pourraient diverger — nommage (DB/API/code), structure de projet, format de réponse API, gestion d'état/chargement, gestion d'erreurs.

### Naming Patterns

**Database Naming :**
- Tables : `snake_case`, pluriel (`users`, `sessions`, `friends`, `billing_events`)
- Colonnes : `snake_case` (`phone_number`, `created_at`)
- Clés étrangères : `<table_singulier>_id` (`user_id`)
- Index : `ix_<table>_<colonne>` (`ix_sessions_user_id`)

**API Naming :**
- Endpoints REST : pluriel (`/sessions`, `/friends`), paramètres de route `{id}` (convention FastAPI)
- **Format JSON du wire (requêtes/réponses) : `camelCase`** — via alias Pydantic (`alias_generator`), pour que le client TypeScript/React Native consomme du JSON idiomatique JS sans couche de transformation. Le code Python interne reste `snake_case` (idiomatique PEP8) ; seule la sérialisation JSON expose le camelCase.

**Code Naming :**
- Backend Python : `snake_case` (fonctions/variables), `PascalCase` (classes), fichiers `snake_case.py`
- Client React Native/TypeScript : `camelCase` (fonctions/variables), `PascalCase` (composants), fichiers `PascalCase.tsx` pour composants, `camelCase.ts` pour utilitaires

### Structure Patterns

**Backend (FastAPI) :** organisé par domaine (`routers/sessions.py`, `routers/billing.py`, `models/`, `schemas/`, `services/`) plutôt que par couche technique seule
**Tests :** co-localisés — `test_*.py` (pytest, backend), `*.test.tsx` (client, à côté du composant testé)
**Client mobile :** organisé par feature/écran (`screens/`, `components/`, `services/`) — cohérent avec le nombre restreint d'écrans
**Config :** `.env` pour le développement local (jamais commité), AWS Secrets Manager en production

### Format Patterns

**API Response Formats :**
- Succès : ressource directe, sans enveloppe (`{id, ...}` pas `{data: {...}}`) — idiomatique REST/FastAPI
- Erreur : `{detail: string}` — convention par défaut de FastAPI, réutilisée telle quelle plutôt que d'en inventer une nouvelle
- Dates : chaînes ISO 8601 en UTC partout

**Data Formats :**
- JSON : `camelCase` (voir Naming Patterns)
- Booléens : `true`/`false` natifs, jamais `1`/`0`

### Communication Patterns

**Événements LiveKit :** utiliser la nomenclature d'événements native du SDK LiveKit (`participantConnected`, etc.) — ne jamais créer de système d'événements parallèle
**Logging :** JSON structuré (compatible CloudWatch), niveaux standards `INFO`/`WARN`/`ERROR`

### Process Patterns

**Error Handling :**
- Toute erreur utilisateur est **annoncée vocalement par l'agent en premier** (cohérent avec le pattern UX déjà établi), jamais seulement affichée silencieusement
- Le backend renvoie systématiquement `{detail: string}` en cas d'erreur HTTP

**Loading States :**
- État booléen simple `isLoading` par écran/action — pas de machine à états complexe, pas de bibliothèque de state management dédiée (cohérent avec la décision Frontend Architecture)

**Retry :**
- Aucune reprise automatique pour le MVP, sauf l'envoi SMS (une reprise unique en cas d'échec de livraison)

**Authentification :**
- Flux unique et cohérent partout : vérification OTP → émission JWT — jamais de variante

### Enforcement Guidelines

**All AI Agents MUST :**
- Respecter le camelCase JSON / snake_case Python (jamais mélanger)
- Utiliser `{detail: string}` pour toute erreur API, jamais un format alternatif
- Annoncer vocalement toute erreur avant (ou en plus de) l'affichage visuel
- Ne jamais introduire de bibliothèque de state management sans révision de cette décision

### Pattern Examples

**Bon exemple (réponse API) :**
```json
{ "sessionId": "abc123", "hostPhoneVerified": true, "createdAt": "2026-07-28T14:30:00Z" }
```

**Anti-pattern à éviter :**
```json
{ "data": { "session_id": "abc123", "host_phone_verified": true } }
```
(mélange snake_case/camelCase, enveloppe `data` superflue)

## Project Structure & Boundaries

### Complete Project Directory Structure

```
salon/
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       ├── deploy-api.yml
│       ├── deploy-agent.yml
│       └── deploy-mobile.yml
├── api/                              # Backend REST (AWS Lambda + API Gateway)
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic.ini
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── routers/
│   │   │   ├── auth.py               # OTP verify, JWT issuance
│   │   │   ├── sessions.py           # création/gestion de session
│   │   │   ├── friends.py            # amis Salon / contacts
│   │   │   ├── billing.py            # Stripe, métrage (FR20)
│   │   │   └── users.py              # historique (FR28)
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── session.py
│   │   │   ├── friend.py
│   │   │   └── billing_event.py
│   │   ├── schemas/                  # Pydantic, alias camelCase
│   │   │   ├── auth.py
│   │   │   ├── session.py
│   │   │   └── billing.py
│   │   ├── services/
│   │   │   ├── otp_service.py        # AWS SNS
│   │   │   ├── stripe_service.py
│   │   │   ├── livekit_service.py    # provisioning de salle
│   │   │   └── sms_service.py        # invitations, lien d'installation
│   │   └── db/
│   │       ├── session.py
│   │       └── alembic/versions/
│   └── tests/
│       ├── test_auth.py
│       ├── test_sessions.py
│       └── test_billing.py
├── agent/                            # Worker LiveKit+xAI (ECS Fargate)
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── livekit.toml
│   ├── .env.example
│   └── src/
│       ├── main.py                   # AgentSession + xai.realtime.RealtimeModel
│       ├── translation.py            # pipeline pivot-anglais (FR12-16)
│       ├── satisfaction.py           # question de fin de session (FR23)
│       └── billing_meter.py          # métrage précis minute/seconde (FR20)
├── mobile/                           # App Expo React Native
│   ├── app.json
│   ├── package.json
│   ├── eas.json
│   ├── tsconfig.json
│   ├── .env.example
│   ├── App.tsx
│   ├── src/
│   │   ├── screens/
│   │   │   ├── OnboardingScreen.tsx  # vérification téléphone (FR18)
│   │   │   ├── HomeScreen.tsx        # invitation vocale (FR2)
│   │   │   ├── SessionScreen.tsx     # session en cours
│   │   │   └── HistoryScreen.tsx     # historique (FR28-29)
│   │   ├── components/
│   │   │   ├── VoiceWaveform.tsx
│   │   │   ├── SalonLogo.tsx
│   │   │   ├── ConfirmationBanner.tsx
│   │   │   └── NoInstallBadge.tsx
│   │   ├── services/
│   │   │   ├── api.ts
│   │   │   └── livekit.ts            # @livekit/react-native
│   │   └── theme/
│   │       └── salonParisien.ts      # tokens couleur/typographie
│   └── __tests__/
├── web-join/                         # Jonction anonyme invité (S3+CloudFront)
│   ├── index.html
│   ├── join.js                       # LiveKit JS SDK
│   └── styles.css
└── infra/
    ├── ecs-task-definition.json
    └── lambda-config.yml
```

### Architectural Boundaries

**API Boundaries :** `api/` expose uniquement REST (auth, sessions, facturation, historique) — ne communique jamais directement avec xAI ; `agent/` communique uniquement via le dispatch d'agent LiveKit, jamais d'appel direct à `api/`
**Component Boundaries :** `mobile/` et `web-join/` ne partagent aucun code — deux clients indépendants du même backend, cohérent avec leur nature radicalement différente (app native vs page statique)
**Service Boundaries :** `otp_service`, `stripe_service`, `livekit_service`, `sms_service` sont chacun un point d'intégration tiers unique — aucune logique métier tierce en dehors de son service dédié
**Data Boundaries :** seul `api/` accède à Aurora PostgreSQL ; `agent/` ne persiste rien (politique de non-persistance), il transmet le métrage à `api/` via un appel REST en fin de session

### Requirements to Structure Mapping

- **Création de Session & Invitation (FR1-5) :** `api/src/routers/sessions.py`, `api/src/routers/friends.py`, `mobile/src/screens/HomeScreen.tsx`
- **Expérience de Discussion Vocale (FR6-11) :** `agent/src/main.py`
- **Traduction Multilingue (FR12-17) :** `agent/src/translation.py`
- **Compte & Facturation (FR18-23) :** `api/src/routers/auth.py`, `api/src/routers/billing.py`, `agent/src/billing_meter.py`
- **Retour d'Expérience & Fin de Session (FR24-27) :** `agent/src/satisfaction.py`, `api/src/routers/sessions.py`
- **Compte & Historique (FR28-31) :** `api/src/routers/users.py`, `mobile/src/screens/HistoryScreen.tsx`

**Cross-Cutting :** le métrage du temps (FR20) traverse `agent/` (mesure en temps réel) et `api/` (persistance dans `billing_events` + déclenchement Stripe)

**Précision :** un invité devient un "ami Salon" (contact dans l'appli, livraison par notification in-app) **uniquement s'il s'est lui-même inscrit à Salon avec un numéro de téléphone vérifié** — aucune acceptation mutuelle requise, mais l'inscription de son côté est nécessaire. Tant qu'il n'est pas inscrit, il reste joignable **uniquement par SMS** par l'hôte, sans entrée persistante dans `friends`. `friends.py` doit donc vérifier si le numéro invité correspond à un compte Salon existant avant de créer l'entrée de contact.

### Integration Points

**Internal Communication :** `mobile/` → `api/` (REST/HTTPS) ; `mobile/` → LiveKit Cloud (SDK direct, pas via `api/`) ; `agent/` → `api/` (heartbeat périodique + callback final pour métrage/facturation)
**External Integrations :** xAI (via `agent/`), LiveKit Cloud (via `agent/` et `mobile/`), Stripe (via `api/`), AWS SNS (via `api/`)
**Data Flow :** `mobile/` initie une session via `api/` → `api/` provisionne la salle LiveKit → `agent/` rejoint la salle et anime la conversation → `agent/` transmet le métrage à `api/` via un **heartbeat périodique (toutes les 30 secondes) pendant la session, plus un callback final** à la fin (pour ne pas perdre le métrage en cas de déconnexion brutale) → `api/` déclenche la facturation Stripe si l'essai gratuit est épuisé

### File Organization Patterns

**Configuration :** un `.env.example` par unité déployable (`api/`, `agent/`, `mobile/`), jamais de config partagée entre unités
**Source Organization :** structure par domaine dans `api/` et `agent/` ; par écran/feature dans `mobile/`
**Test Organization :** co-localisé dans chaque unité (`api/tests/`, `mobile/__tests__/`)
**Asset Organization :** SVG (logo causeuse, icône télégraphe) dans `mobile/src/components/` et dupliqués dans `web-join/` (pas de package partagé, vu le peu d'assets)

### Development Workflow Integration

**Development Server :** `api/` tourne localement via `uvicorn`, `agent/` via `python src/main.py` (connecté à un projet LiveKit Cloud de dev), `mobile/` via Expo Development Build
**Build Process :** `api/` empaqueté pour Lambda, `agent/` containerisé (Dockerfile fourni par le starter), `mobile/` construit via EAS Build
**Deployment :** GitHub Actions déploie les trois indépendamment (`deploy-api.yml`, `deploy-agent.yml`, `deploy-mobile.yml` déclenche EAS)

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility :** Toutes les technologies choisies sont compatibles entre elles — Python (API + agent) partage l'écosystème Pydantic/FastAPI, React Native/Expo est indépendant du backend (communication REST/WebRTC standard), AWS héberge tout sans dépendance circulaire.

**Pattern Consistency :** Les conventions de nommage (camelCase JSON / snake_case Python) sont appliquées uniformément dans la structure de projet. Les patterns d'erreur (`{detail}`) et de communication (événements natifs LiveKit) s'alignent avec les choix technologiques.

**Structure Alignment :** La séparation `api/` / `agent/` / `mobile/` / `web-join/` respecte les frontières définies à l'étape 5 (aucune logique métier tierce hors de son service dédié).

### Requirements Coverage Validation ✅

**Functional Requirements Coverage :** Les 31 FR sont couvertes — chaque catégorie a un mappage explicite vers un fichier/module précis (voir Requirements to Structure Mapping).

**Non-Functional Requirements Coverage :**
- Performance : aucun seuil fixé (délibéré, cohérent avec le PRD)
- Security : non-persistance respectée par construction (`agent/` ne persiste rien, `api/` ne stocke que des métadonnées), tokenisation Stripe, TLS partout
- Integration : dégradation gracieuse couverte au niveau du principe (Process Patterns → Error Handling)

### Implementation Readiness Validation ✅

Décisions, patterns et structure sont documentés avec suffisamment de détail pour qu'un agent IA implémente sans ambiguïté majeure.

### Gap Analysis Results

**Gap Important — Résolu :** Un invité devient un "ami Salon" (contact in-app) **uniquement s'il s'est inscrit à Salon avec un numéro de téléphone vérifié** — sinon, il reste joignable uniquement par SMS par l'hôte, sans entrée persistante dans `friends`. `friends.py` vérifie l'existence d'un compte enregistré pour ce numéro avant de créer l'entrée de contact.

**Gaps Mineurs (acceptés tels quels pour le MVP) :**
- Pas de mécanisme concret documenté pour détecter une panne xAI/LiveKit/Stripe (health check, circuit breaker) — le principe "message d'erreur clair" est établi (NFR Integration), l'implémentation reste à définir dans les stories
- Stratégie de rafraîchissement du JWT (expiration/refresh token) non spécifiée — détail d'implémentation laissé aux stories

### Validation Issues Addressed

Le gap important (mécanisme "ami Salon") a été résolu par le solopreneur : automatique dès la première invitation. Les gaps mineurs sont acceptés tels quels pour le MVP, à préciser durant l'implémentation.

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**✅ Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**✅ Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**✅ Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status :** READY FOR IMPLEMENTATION

**Confidence Level :** Élevé

**Key Strengths :** Séparation claire des responsabilités (api/agent/mobile/web-join), choix technologiques éprouvés ("boring tech"), coût minimisé à chaque décision (serverless, managé, pas d'infra-as-code prématurée)

**Areas for Future Enhancement :** Circuit breaker/health check pour les dépendances tierces, stratégie de refresh JWT, éventuel cache Redis si le volume grandit

### Implementation Handoff

**AI Agent Guidelines :** Suivre les décisions architecturales telles que documentées, respecter la structure de projet et les frontières entre `api/`/`agent/`/`mobile/`/`web-join/`.

**First Implementation Priority :** `lk app create --template agent-starter-python` (Story 1.1)
