# Story 11.1 — Un agent par humain, une room par paire

**Statut** — rédigée, non implémentée. Le lien agent ↔ orchestrateur est en place et testé
(`src/orchestrator_link.py`, `src/following.py`, `src/session_voice.py`, branchés dans
`agent.py`) ; il reste inerte parce que cette story n'est pas faite.

---

## Le problème, dit simplement

Vocaliz a hérité de Salon une topologie qui ne peut pas porter le produit :

```
HÉRITÉ    une room, jusqu'à trois humains, un agent
          tout le monde entend le même flux audio
          → un seul interprète pour trois personnes qui ne parlent pas la même langue

VOULU     une room par paire humain-interprète, jusqu'à trois paires
          personne n'entend l'audio de personne
          → l'écho est indisponible, pas annulé
```

**Ce n'est pas une préférence d'architecture.** Trois conséquences la rendent nécessaire :

1. **L'attribution est une heuristique dans un endroit où elle ne peut pas l'être.** Le modèle
   temps réel entend tout le monde mélangé en un seul flux, donc « qui a parlé » vient de la
   détection de locuteur actif de LiveKit — juste quand une personne parle, une supposition
   quand deux se chevauchent. Pour un interprète ce n'est pas un détail : se tromper de
   locuteur **inverse le sens d'une traduction** et redit à quelqu'un ses propres mots.

2. **Un script est écrit pour un auditeur, et il n'y a qu'une sortie audio.** L'orchestrateur
   produit une liste ordonnée dans la langue de l'écoutant. La dire dans une room où quelqu'un
   d'autre est assis lui lit la moitié d'une conversation qui ne lui était pas destinée — et
   dans sa langue à elle, pas dans la sienne.

3. **Les modes par participant n'ont aucun sens dans une room commune.** La règle produit
   PR-VOICE-001 dit que chaque participant choisit son mode et paie son tarif. Avec un seul
   interprète partagé, il n'y a rien à choisir.

C'est aussi pourquoi `MixedParticipantAudioInput` existe : 188 lignes pour mélanger plusieurs
humains en un flux. **Une bonne partie de cette story est une suppression.**

---

## Ce qui change, et où

| Composant | Aujourd'hui | Après |
|---|---|---|
| **API** — création de Salon | une room, `max_participants` = cap | une room par paire, `max_participants` = 2 |
| **API** — arrivée d'un invité | un jeton pour la room commune | provisionne sa room, dépêche son agent |
| **API** — dépêche | un agent par Salon | **un agent par participant** |
| **agent.py** | mélange N humains, attribue par heuristique | un humain, aucune attribution à faire |
| `MixedParticipantAudioInput` | 188 lignes | **supprimé** |
| `captions.attributed_speaker()` | heuristique de locuteur actif | l'unique humain de la room |
| Coupure du micro (FR/Story 6.8) | l'hôte coupe dans la room commune | l'hôte demande à l'orchestrateur, qui refuse l'entrée au journal |
| Fin de Salon | un agent voit la room se vider | chaque agent voit la sienne ; l'orchestrateur arbitre |

---

## Critères d'acceptation

### AC1 — Une room ne contient jamais deux humains
Provisionnée avec `max_participants: 2`, imposé par LiveKit et non par notre comptabilité.
`adapters/livekit_rooms.py` le fait déjà ; l'API doit s'y conformer.
**Vérifiable ainsi :** aucun jeton émis ne nomme une room qui en contient déjà deux.

### AC2 — Un agent est dépêché par participant, pas par Salon
Chaque dépêche porte, dans ses métadonnées, l'identifiant du Salon **et celui du participant**
— l'agent n'a plus à deviner pour qui il travaille.
**Vérifiable ainsi :** trois humains dans un Salon ⇒ trois dépêches, trois rooms, trois
identités d'agent distinctes.

### AC3 — L'attribution disparaît au lieu d'être améliorée
`captions.attributed_speaker()` devient l'unique humain de la room. L'heuristique de locuteur
actif est retirée, pas raffinée.
**Vérifiable ainsi :** deux personnes parlant en même temps dans deux rooms produisent deux
transcriptions correctement attribuées, ce qui est aujourd'hui impossible par construction.

### AC4 — Le mélangeur d'audio est supprimé
`MixedParticipantAudioInput` et ses tests disparaissent. `RoomOptions(audio_input=False)` et le
rebranchement manuel qui l'accompagne disparaissent avec.
**Vérifiable ainsi :** `agent.py` ne contient plus de rebranchement d'entrée audio.

### AC5 — La conversation passe par le journal et non par la room
Ce qu'un humain dit est rapporté à l'orchestrateur ; ce qu'il entend vient d'un script.
Aucun humain ne reçoit l'audio d'un autre humain, jamais.
**Vérifiable ainsi :** couper le lien à l'orchestrateur arrête la traduction et **n'arrête pas
le Salon** — chacun reste dans sa room avec son agent.

### AC6 — Chaque participant a son propre mode et son propre tarif
Le mode choisi à l'arrivée décide du modèle de son interprète, et de rien d'autre chez les
autres (PR-VOICE-001, FR32-FR42).
**Vérifiable ainsi :** un Salon mêlant Base et speech-to-speech fonctionne, et chaque siège est
facturé à son propre tarif.

---

## Le blocage à lever avant tout le reste

**L'orchestrateur répond dans le VPC ; le worker de l'agent tourne sur LiveKit Cloud.**
L'adresse `http://orchestrator.vocaliz.internal:8080` qui fonctionne depuis la Lambda de l'API
n'est joignable depuis nulle part ailleurs. C'est délibéré — l'orchestrateur tient le texte de
toutes les conversations vivantes — et c'est aussi ce qui empêche l'agent de lui parler.

Trois issues, et elles ne se valent pas :

**(a) Exposer l'orchestrateur publiquement, authentifié.** Un ALB, un certificat, et un jeton
par participant signé par l'API. Le plus rapide. Ce qu'on met dehors, c'est le service qui tient
le texte de toutes les conversations en cours — donc l'authentification n'est pas un détail
d'implémentation mais la totalité de la sécurité du produit.

**(b) Faire relayer par l'API.** L'agent parle à `app.vocaliz.net`, qui est déjà public et déjà
authentifié, et l'API transmet à l'orchestrateur. Aucune nouvelle surface exposée, aucun nouveau
modèle d'authentification. Le prix est un saut réseau supplémentaire par tour de parole —
exactement ce que la frontière texte/audio a été tracée pour éviter.

**(c) Héberger le worker de l'agent nous-mêmes**, dans le VPC, à côté de l'orchestrateur.
Supprime le problème au lieu de l'arbitrer, et supprime aussi le saut réseau. Le prix est qu'on
reprend l'exploitation d'un composant que LiveKit Cloud opère aujourd'hui — mise à l'échelle,
correctifs, disponibilité.

**Tranché : (b) maintenant, (c) à terme.** (b) se code en une journée et ne ferme aucune
porte ; (c) est la bonne place à terme, parce que la latence est ce que ce produit vend et qu'un
saut réseau par tour de parole est précisément ce qu'on a refusé de payer en descendant
l'interprète dans l'agent. (a) est la seule des trois qui crée une surface à défendre.

---

## Découpage suggéré

| # | Tranche | Contenu | Dépend de |
|---|---|---|---|
| 1 | ~~**Joignabilité**~~ | **Fait** — relais (b) par l'API, `VOCALIZ_JOURNAL=relay` | — |
| 2 | ~~**Dépêche par participant**~~ | **Fait pour les invités** — une room et un agent par invité au clic, l'hôte suit ; jetons de relais bornés | 1 |
| 3 | **Amaigrissement de l'agent** | Supprimer le mélangeur et l'attribution | 2 |
| 4 | **La conversation par le journal** | Activer `follow` ; retirer la traduction dans la room | 1, 3 |
| 5 | **Modes par siège** | Chaque interprète à son tarif | 4 |

Les tranches 1 et 2 sont indépendantes et peuvent avancer en parallèle. **Rien de la logique
textuelle ne bouge dans aucune d'elles** : les créneaux publicitaires, les présentations, la
condensation, la saturation et l'ordre d'arrivée restent dans l'orchestrateur, où ils sont déjà
écrits et testés.

---

## Ce qui est déjà fait, et qui attend cette story

```
orchestrator/src/serving.py          la surface HTTP, 906 tests
orchestrator/src/salon/script.py     l'inversion pousser → servir
agent/src/orchestrator_link.py       rapporter, demander        24 tests
agent/src/following.py               la boucle de livraison
agent/src/session_voice.py           les deux chemins, verbatim ou modèle
agent/agent.py                       branché, inerte tant qu'ORCHESTRATOR_BASE_URL est vide
```

Le circuit est complet de bout en bout et vérifié contre un vrai orchestrateur en conteneur,
avec de vraies rooms LiveKit. Il ne lui manque qu'une topologie où il a le droit de parler.

---

## Ce que la tranche 2 a livré, et sa faille refermée en cours de route

Chaque invité qui ouvre son lien reçoit maintenant sa propre room et son propre agent,
dépêché au premier `GET /guest-join/{token}` réussi et réutilisé sur tous les suivants
(`invitations.livekit_room_name`, migration 060). L'hôte, symétriquement, dépêche son propre
agent à la création — nécessaire pour que la conversation fonctionne dans les deux sens.

**La faille que tranche 1 avait ouverte sans le savoir.** Le relais vérifiait un compte
Vocaliz authentifié, jamais lequel Salon ce compte pouvait toucher — n'importe quel
utilisateur connecté pouvait interroger le journal de n'importe quel Salon. Rien ne l'avait
encore exploitée seulement parce que rien n'avait encore émis de second jeton. Un invité n'a
d'ailleurs aucun compte pour porter un jeton complet. `relay_token.py` mint désormais un
jeton borné à `(salon_id, participant_id)` — il autorise à parler comme ce participant dans
ce Salon, rien de plus, et un jeton pour Marie ne peut pas se faire passer pour Hans.

**Vérifié de bout en bout contre un vrai orchestrateur et de vraies rooms LiveKit** :
hébergement, deux participants qui rejoignent chacun leur propre room, ce que Hans dit en
allemand qui arrive à Marie marqué `de→fr`, la mauvaise portée refusée à 403, le départ
propre.

**Ce que ceci n'a pas fait, délibérément.** `dial_in` (le bouton de simulation d'appel
téléphonique) et `call_the_desk` restent sur la room partagée et ne dépêchent pas un agent
par participant — le premier n'a aucun trafic réel derrière lui tant qu'aucun trunk SIP
n'existe, le second garde sa propre room pour le bureau et n'appelle jamais
`orchestrator_client.host_salon`. Ni l'un ni l'autre n'était dans la demande, et les
convertir est un travail identique à celui déjà fait, pas un nouveau problème.

`MixedParticipantAudioInput` n'a pas été retiré (AC4, tranche 3) : avec une seule personne
par room il ne fait que mélanger une seule source, ce qui est inoffensif à laisser en place
pour l'instant.
