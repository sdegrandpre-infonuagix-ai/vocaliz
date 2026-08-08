---
date: '2026-08-08'
author: 'Winston (Architect)'
purpose: 'Audit des 44 stories de Vocaliz contre le code hérité du projet Salon'
sources:
  - 'api/ — 43 migrations, 15 modèles, 7 routers, 25 services'
  - 'agent/ — agent.py, captions, mixed_audio_input, opening, 13 fichiers de tests'
  - 'mobile/ — React Native, 4 écrans, contextes auth et langue, i18n'
  - 'infra/ — AWS CDK TypeScript'
  - '_bmad-output/planning-artifacts/epics.md — 44 stories'
---

# Audit des 44 stories contre le code hérité

## Pourquoi cet audit

Le code de ce dépôt vient du projet **Salon**, un produit mûr qui diffère de Vocaliz sur quatre points seulement. Les 44 stories des Epics 6 à 10 ont pourtant été écrites comme si tout partait de zéro.

Lancé tel quel, Ralph reconstruirait des sous-systèmes existants — et, dans au moins un cas, les remplacerait par une version moins capable.

## Verdict global

```
DÉJÀ FAIT       8 stories    à retirer du périmètre ou à réduire à une vérification
PARTIEL        11 stories    socle présent, à étendre — jamais à réécrire
À CONSTRUIRE   25 stories    le vrai périmètre de Vocaliz
```

**Un peu moins de la moitié du périmètre annoncé existe déjà, en tout ou en partie.**

---

## Epic 6 — Socle Conversationnel Multi-Rooms

| Story | État | Constat |
|---|---|---|
| 6.1 Initialisation orchestrateur | **À CONSTRUIRE** | `api/` est une API REST, pas un orchestrateur par Salon |
| 6.2 Port Interprète + adaptateur S2S | **À CONSTRUIRE** | `agent.py` appelle `xai.realtime.RealtimeModel` en dur |
| 6.3 Orchestrateur, journal et curseurs | **PARTIEL** | Le **journal existe** : `utterances` + `utterance_translations`, avec un `sequence` monotone unique par session. Les **curseurs** n'existent pas |
| 6.4 Une room par participant | **À CONSTRUIRE** | Cœur du pivot. `create_room()` + `dispatch_agent()` → une room, un agent |
| 6.5 Découpage à 500 caractères | **À CONSTRUIRE** | Les `utterances` sont des tours complets, non découpés |
| 6.6 Restitution FCFS | **DÉJÀ FAIT** | `sequence` monotone assigné à l'insertion **est** l'ordre d'arrivée |
| 6.7 Adaptateur Base STT+TTS | **À CONSTRUIRE** | — |
| 6.8 Coupure de micro par l'hôte | **À CONSTRUIRE** | `POST /microphone` est un **rapport du client**, pas un contrôle. `agent/mute` vise l'agent, pas un participant |
| 6.9 Présentation des participants | **PARTIEL** | `first_spoken_language` et la détection existent ; l'annonce vocale non |
| 6.10 Historique pour arrivant tardif | **PARTIEL** | `GET /{id}/utterances` sert déjà le transcript ; la décision d'accès de l'hôte et la condensation non |
| 6.11 Nettoyage + métadonnée de pause | **À CONSTRUIRE** | — |
| 6.12 Chiffrement au repos | **DÉJÀ FAIT** | Aurora chiffré par KMS, ce qui couvre instantanés et sauvegardes. Reste à vérifier : aucun contenu de conversation dans CloudWatch |
| 6.13 Vidéo muette | **À CONSTRUIRE** | — |

### 🚩 Le journal hérité est meilleur que celui des stories

Les stories décrivent un **journal en anglais pivot** : tout est traduit vers l'anglais, puis retraduit vers chaque langue. Deux sauts, deux pertes.

Le code fait autrement, et mieux :

```
utterances               le tour tel que prononcé, dans sa langue d'origine — jamais écrasé
utterance_translations   une ligne par (tour, langue cible), mise en cache
```

Chaque traduction part donc de **l'original**, jamais d'un pivot. Le commentaire du modèle est explicite : *« Never overwritten by a translation: every translation is a derived row, and this is the only record of what was said. »*

**Adopter l'anglais pivot aurait été une régression de qualité de traduction.**

> ✅ **Tranché le 2026-08-08 : aucun pivot.** L'émetteur fait l'original — trois interlocuteurs en trois langues produisent trois originaux, et chaque traduction part directement de celui qu'elle traduit. Le PRD et les epics ont été mis à jour ; le modèle hérité de Salon est conservé.

---

## Epic 7 — Régulation de Charge & Observabilité

| Story | État | Constat |
|---|---|---|
| 7.1 Configuration persistée | **PARTIEL** | `config.py` porte des réglages (`livekit_room_max_participants`, `livekit_room_empty_timeout`), mais en variables d'environnement — pas une table modifiable à chaud |
| 7.2 Condensation | **À CONSTRUIRE** | — |
| 7.3 Saturation et blocage | **À CONSTRUIRE** | — |
| 7.4 Plafond de monologue | **À CONSTRUIRE** | — |
| 7.5 Interprète simulé + charge | **À CONSTRUIRE** | 13 fichiers de tests unitaires existent ; aucun test de charge |
| 7.6 Ordre de méta-parole | **À CONSTRUIRE** | — |

Cet epic est **le plus intact** : la régulation de charge n'a aucun équivalent dans Salon, parce qu'un agent unique à deux participants n'en avait pas besoin.

---

## Epic 8 — Modes d'Expérience & Paliers Tarifaires

| Story | État | Constat |
|---|---|---|
| 8.1 Flux d'événements comptables | **PARTIEL** | `billing_events` et `ad_broadcasts` sont des journaux append-only avec garanties d'idempotence, mais séparés — pas un flux unique |
| 8.2 Crédit offert 5 USD | **À ADAPTER** | `trial_seconds_used` est un essai **en temps**, pas un crédit monétaire |
| 8.3 / 8.4 Trois options | **À CONSTRUIRE** | `SessionCreationScreen.tsx` existe ; aucun palier |
| 8.5 Salon mixte | **À CONSTRUIRE** | — |
| 8.6 Facturation par mode | **À ADAPTER** | Facturation présente, mais **post-payée** et à tarif unique |
| 8.7 Solde prépayé en millicents | **À CONSTRUIRE** | Le plus gros écart de cet epic |
| 8.8 Vérification périodique | **PARTIEL** | Le heartbeat existe — `last_heartbeat_at`, `POST /{id}/heartbeat` — et sert déjà au métrage |
| 8.9 Alerte et fin de session | **À CONSTRUIRE** | — |
| 8.10 Octroi manuel de crédit | **À CONSTRUIRE** | `routers/admin.py` existe mais n'expose que **deux lectures** : `/participants` et `/report` |
| 8.11 Journal des crédits | **À CONSTRUIRE** | — |
| 8.12 Journal du solde payé | **À ADAPTER** | `billing_events` en est proche : montant, devise, `stripe_payment_intent_id`, statut |
| 8.13 Rabais web | **À CONSTRUIRE** | — |

### 🚩 Le modèle de facturation change de nature

```
Salon      trial_seconds_used → billed_seconds → charge Stripe APRÈS usage
Vocaliz    solde prépayé en millicents → débit toutes les 5 s → jamais de découvert
```

Ce n'est pas une extension mais un **remplacement**. `trial_seconds_used`, `billed_seconds` et la logique de `stripe_service` sortent du modèle ; `billing_events` peut rester comme journal d'encaissement.

---

## Epic 9 — Régie d'Annonces Géolocalisées

| Story | État | Constat |
|---|---|---|
| 9.1 Consentement de géolocalisation | **PARTIEL** | Le `plus_code` est collecté et la demande existe côté client — *« Empty when the participant declined the location prompt »*. Le retrait de consentement n'existe pas |
| 9.2 Inventaire d'annonces | **DÉJÀ FAIT — ET DÉPASSÉ** | voir ci-dessous |
| 9.3 Insertion entre messages | **PARTIEL** | `POST /{id}/ad` et `/ad/delivered`, `ad_broadcasts.delivered_at`. La règle « entre deux messages, jamais au milieu d'une pensée » n'est pas exprimée |
| 9.4 Fréquence par palier | **À CONSTRUIRE** | Dépend des paliers, qui n'existent pas |

### 🛑 La Story 9.2 dégraderait le système existant

Elle décrit *« une table d'inventaire où l'interprète puise »*. Le code a un **échange publicitaire** :

```
ads                       sales_pitch, bid_cents, number_of_broadcasts_left, topic, spoken_language
ads_regions               ciblage par cellules Open Location Code
advertisers_regions       régions nommées achetées par l'annonceur
ad_broadcasts             preuve de diffusion : delivered_at, amount_cents figé, facturation Stripe idempotente
ad_auction_service        enchère au SECOND PRIX — « the winner pays the least it would have
                          taken to beat the runner-up, because a first-price auction is played
                          rather than bid »
ad_billing_service        facturation des annonceurs
house_ads                 annonces maison
```

Et des garanties inscrites dans le schéma :
- `ck_ad_broadcasts_billed_only_if_delivered` — **on ne facture jamais une annonce que personne n'a entendue**
- `RESTRICT` sur la suppression — les preuves de diffusion sont indestructibles
- `amount_cents` figé au moment de la diffusion — l'historique ne se reprice pas

La Story 9.2 doit être **remplacée par une story d'adaptation**, pas exécutée.

### Deux avertissements que le code lui-même laisse

**Le ciblage par sujet est une question de consentement.** `ads.topic` n'est branché sur rien, et le commentaire est explicite : *« turning a transcript into topics is a step nobody has built, and using conversation content to place advertising is a consent question well beyond storing it for translation. »* FR50 ne parle que de géolocalisation et de langue — cette frontière doit rester dans l'architecture.

**Trois mécanismes de géographie coexistent**, et le code dit que le troisième doit disparaître : `ads_regions`, `advertisers_regions`, et les JSONB `target_countries` / `target_regions` / `circle` qui n'ont jamais eu de données.

---

## Epic 10 — Inscription Légère & Accès

| Story | État | Constat |
|---|---|---|
| 10.1 Inscription courriel ou téléphone | **DÉJÀ FAIT** | OTP courriel via SES, téléphone optionnel, `link_prior_invitations` rattache les participations antérieures |
| 10.2 Plafond de participants | **DÉJÀ FAIT** | `livekit_room_max_participants` — à déplacer en configuration persistée (voir 7.1) |
| 10.3 Lien à usage unique par invité | **DÉJÀ FAIT** | `join_token` unique **par invitation**, `expires_at`, `status` |
| 10.4 Jonction web sans installation | **DÉJÀ FAIT** | `routers/guest_web.py` |
| 10.5 Invitation vocale d'un téléphone | **DÉJÀ FAIT** | `phone_pin` à six chiffres, index unique partiel sur les invitations en attente, dispatch SIP, `sms_service` |
| 10.6 Modification d'identifiant avec ancre | **À CONSTRUIRE** | — |
| 10.7 Nom d'utilisateur et mot de passe | **À CONSTRUIRE** | L'authentification est OTP par courriel, sans mot de passe |
| 10.8 Droit d'accès et d'effacement | **À CONSTRUIRE** | — |

**Cinq stories sur huit sont déjà livrées.** C'est l'epic le plus largement acquis.

---

## Ce qui existe dans le code et n'apparaît nulle part dans la planification

| Fonctionnalité | Où |
|---|---|
| **Sous-titres en direct traduits** | `caption_language`, `caption_scale`, `CaptionsPanel.tsx`, `useCaptions.ts`, `captions.py` |
| **Mode conduite** | `DrivingMode.tsx` |
| **Rapport de participants** | `participant_report.py`, `admin.py` |
| **Codes de Salon** | `salon_code_service.py`, migrations 023–024 |
| **Santé des services** | `service_health.py`, `xai_health.py`, migration 043 |
| **Sources partagées et provenance** | migrations 020–021, `shared_source_service.py` |
| **Résumé de source** | `summary_service.py`, `source_summary` |
| **Jeton d'appareil** | `device_token`, `device_service.py` |
| **Préférences de langue** | `interface_language`, `caption_language`, `agent_language` |
| **AWS CDK** | `infra/` — l'ancienne architecture disait « pas d'infrastructure-as-code » |

Les **sous-titres** sont l'omission la plus significative : une fonctionnalité entière, livrée et testée, absente du PRD comme des epics.

---

## Recommandations

1. **Retirer du périmètre les 8 stories déjà faites**, ou les réduire à une vérification. Elles ne doivent pas atteindre Ralph sous forme de travail à faire.
2. ✅ **Fait — Story 9.2 remplacée** par « Adaptation de l'Échange Publicitaire Hérité », avec un avertissement *ne pas reconstruire*.
3. ✅ **Fait — aucun pivot.** L'émetteur fait l'original, chaque traduction est à un saut. PRD et epics mis à jour.
4. ✅ **Fait — sous-titres réintégrés** en FR73 et Story 6.14, web et mobile, dans un ensemble de langues plus large que celui de la voix.
5. **Requalifier les 11 stories partielles** en extensions, avec le point de départ nommé — un développeur qui ignore que `utterances` existe le réécrira.
6. **Puis seulement, écrire l'architecture** : socle hérité, les quatre écarts, et le nouveau.
