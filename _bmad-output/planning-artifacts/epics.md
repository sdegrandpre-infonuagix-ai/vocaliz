---
stepsCompleted: [1, 2, 3, 4]
status: 'complete'
lastValidated: '2026-08-08'
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/architecture.md', '_bmad-output/planning-artifacts/ux-design-specification.md', '_bmad-output/planning-artifacts/product-rule-voice-modes.md']
revisions:
  - date: '2026-08-08'
    scope: 'PR-VOICE-001 + architecture multi-rooms + modèle prépayé — Epics 6 à 10, FR32-FR72, NFR4-NFR9'
    stories: 44
    note: 'Epics 1 à 5 livrés et non renumérotés. Plusieurs FR y sont amendées ou supprimées — voir la carte de couverture.'
    validation: 'Étape 4 passée. Couverture FR complète · dépendances vers l''avant corrigées dans l''Epic 8 · story de socle NFR7 ajoutée (8.1) · initialisation de l''orchestrateur ajoutée (6.1).'
---

# vocaliz - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for vocaliz, decomposing the requirements from the PRD, UX Design, and Architecture requirements into implementable stories.

> **Nommage.** Le produit s'appelle **Vocaliz** (`vocaliz.net`). Le mot **« Salon »** désigne partout l'**objet** — une conversation entre participants : *créer un Salon*, *rejoindre un Salon*, *le Salon se ferme*. Les deux coexistent volontairement. *Verbaliz*, apparu par erreur dans une version antérieure, a été corrigé en Vocaliz partout.

## Requirements Inventory

### Functional Requirements

FR1: Un hôte peut créer un Salon en téléversant un document, en fournissant une URL de nouvelle comme source, ou sans aucune source — dans ce dernier cas, l'agent ouvre le Salon en demandant aux participants de quoi ils souhaitent discuter
FR2: Un hôte peut inviter exactement un invité à un Salon par commande vocale, en nommant un ami enregistré dans Salon (livraison par notification in-app) ou un contact par son adresse courriel (livraison du lien de jonction par courriel)
FR3: Un hôte peut ajouter un document ou une URL supplémentaire à un Salon actif, avant ou pendant celle-ci
FR4: Un invité sans l'application mobile installée peut rejoindre un Salon directement depuis un navigateur web, sans créer de compte
FR5: Un lien d'invitation ne peut être utilisé qu'une seule fois pour rejoindre un Salon
FR6: Un agent vocal lit à voix haute le contenu source du Salon aux participants
FR7: Les participants peuvent discuter du contenu source avec l'agent vocal et entre eux sans l'avoir lu ou consulté au préalable
FR8: L'agent vocal introduit des informations contrastantes provenant d'autres sources pendant la discussion
FR9: Les participants prennent la parole selon les pauses naturelles de la conversation, sans mécanisme formel de demande de parole
FR10: L'agent vocal comprend le langage naturel des participants en tout temps, sans mot-clé de réveil requis
FR11: Les participants peuvent ajuster vocalement la fréquence d'intervention proactive de l'agent (par défaut : une intervention succincte par minute lorsque les participants partagent la même langue ; plus fréquent lorsque l'agent traduit activement entre deux langues différentes)
FR12: Le système détecte automatiquement la langue parlée par chaque participant, sans sélection manuelle
FR13: L'affichage visuel de l'application (les quelques écrans existants) est présenté dans la langue vocale détectée de l'utilisateur, sans sélection manuelle
FR14: Les participants peuvent s'exprimer dans leur propre langue pendant un Salon
FR15: Le contenu parlé est traduit et lu à voix haute à chaque participant dans sa propre langue, lorsque les participants parlent des langues différentes
FR16: Le contenu traduit est lu à voix haute pendant que l'interlocuteur d'origine continue de parler, sans interrompre la conversation
FR17: L'audio traduit destiné à un participant ne crée pas d'écho dans l'audio partagé du Salon
FR18: Un nouvel utilisateur doit créer un compte avec une adresse courriel vérifiée par code à usage unique avant de pouvoir utiliser Salon pour la première fois ; le numéro de téléphone devient facultatif et n'est requis que pour être invité par SMS ou pour rattacher une participation antérieure en tant qu'invité anonyme
FR19: Un hôte dispose d'une heure d'essai gratuite à vie, cumulée sur l'ensemble de ses Salons
FR20: Le système comptabilise précisément, à la minute et à la seconde près, le temps de conversation cumulé de chaque hôte, pour déterminer le moment exact où l'heure d'essai gratuite est épuisée
FR21: Un hôte doit ajouter une méthode de paiement (Stripe) une fois son heure d'essai gratuite épuisée, pour continuer à utiliser Salon en tant qu'hôte
FR22: Un hôte est facturé 5 USD par heure (au prorata de la seconde) au-delà de son heure d'essai gratuite
FR23: Un invité n'est jamais facturé, peu importe la durée du Salon
FR24: Un participant peut quitter un Salon à tout moment par une commande vocale dans sa propre langue
FR25: Un participant peut quitter un Salon à tout moment en fermant l'application ou le navigateur
FR26: L'agent vocal pose une question simple de satisfaction immédiatement après qu'un participant a prononcé la commande de sortie de Salon
FR27: Un invité non-authentifié peut répondre à la question de satisfaction de fin de Salon sans posséder de compte persistant
FR28: Un utilisateur inscrit peut consulter son historique de Salons passés et de partenaires de discussion
FR29: Un utilisateur inscrit peut démarrer un nouveau Salon avec n'importe quel partenaire de discussion précédent
FR30: Un invité anonyme reçoit automatiquement un courriel avec un lien d'installation de l'application native une fois son Salon terminé
FR31: Un invité anonyme peut installer l'application native via ce lien et continuer à utiliser Salon en tant qu'utilisateur inscrit

#### Révision 2026-08-08 — PR-VOICE-001 & architecture multi-rooms

> Ces requirements amendent ou remplacent une partie des FR1 à FR31 ci-dessus. Les mentions `REMPLACE` / `AMENDE` / `SANS OBJET` font autorité en cas de contradiction.

FR32: Un Salon offre toujours le mode speech-to-speech comme option d'expérience, en plus du mode Base
FR33: **Quatre paliers** d'expérience coexistent, chacun n'achetant qu'une chose de plus que le précédent :

```
Base    3 USD/h        avec annonces   voix synthétique (STT+TTS)
Mode A  7,50 USD/h     avec annonces   voix naturelle   (grok-voice-think-fast-1.0)
Mode B  15 USD/h       sans annonces   voix naturelle   (grok-voice-think-fast-1.0)   tarif promotionnel de lancement
Mode C  22,50 USD/h    sans annonces   voix premium     (grok-voice-think-fast-2.0)
```

**Il n'existe aucun palier gratuit.** Le mode Base est le prix plancher, non une gratuité. Le crédit de bienvenue de FR51 est le seul usage sans débours, et il s'épuise.

**Les tarifs absorbent 30 % de commission de magasin** — le taux plein d'Apple et de Google, sans recours aux programmes réduits. Majoration ÷ 0,70 puis arrondi. Ce choix a deux conséquences délibérées :

1. **La falaise du million disparaît.** Les taux réduits (15 %) sont conditionnés à un revenu annuel sous un million de dollars ; les absorber aurait imposé une hausse de tarifs le jour du franchissement, sur des clients déjà acquis. Tarifer au taux plein dès le départ supprime ce rendez-vous.
2. **Sous un million, la commission réellement prélevée n'est que de 15 %** — Apple Small Business Program et service fee réduit de Google. Les 15 points d'écart entre le taux tarifé et le taux payé constituent une **marge de croissance délibérée**, encaissée pendant toute la phase d'amorçage. Sur un million de ventes, cela représente ≈ **150 000 USD** de marge supplémentaire.
3. **Le canal navigateur devient nettement plus rentable** — jusqu'à 30 points d'écart avec le magasin, contre 15 auparavant. C'est le levier du rabais de FR71.
FR34: À la création d'un Salon, l'hôte configure **ses trois options personnelles** ; aucune ne s'applique aux autres participants
FR35: À la jonction, chaque participant payeur configure **les mêmes trois options**, indépendamment de l'hôte et des autres

> **Les trois options d'un participant payeur**, présentées au même écran — à la création pour l'hôte, à la jonction pour un invité :
>
> | | Option | Valeurs | Défaut |
> |---|---|---|---|
> | 1 | **Palier d'expérience** (FR33) | Base · Mode A · Mode B · Mode C | aucun — choix explicite requis |
> | 2 | **Vidéo muette** (FR72) | activée · désactivée | désactivée |
> | 3 | **Montant de recharge** (FR56) | entre le plancher de sa granularité et `plafond_recharge` | plancher de sa granularité |
>
> Elles sont **personnelles et indépendantes** : deux participants du même Salon peuvent tenir trois choix différents chacun. Une seule option échappe à cette règle et n'appartient qu'à l'hôte — « l'hôte paie tout » (FR42), qui écrase le palier des invités qu'il couvre, et toujours vers le haut.
FR36: Le mode choisi persiste toute la durée du Salon, sauf changement explicite du participant
FR37: Un Salon réunit simultanément des participants en mode Base et en mode speech-to-speech ; le mode Base n'est ni bloqué ni dégradé
FR38: Le mode Base et le mode speech-to-speech sont deux adaptateurs du même port Interprète (Base = STT + LLM + TTS ; S2S = modèle temps réel audio↔audio)
FR39: Les annonces résident dans une **table d'inventaire**. Au moment opportun de sa room, l'interprète de chaque participant y **puise** une annonce correspondant à son ciblage, la lit, et enregistre la diffusion. L'insertion a lieu entre deux messages et jamais à l'intérieur d'une intervention découpée — sauf au-delà du plafond de monologue. Chaque interprète suit son propre rythme, sans synchronisation entre rooms
FR40: Chaque participant est facturé au tarif horaire de son propre mode, au prorata de la seconde — **REMPLACE FR22**
FR41: Un participant doit disposer d'un solde suffisant pour consommer un mode, tous les paliers étant payants — **FR23 SUPPRIMÉE** (l'invité paie désormais)
FR42: À la création, l'hôte peut activer « l'hôte paie tout » : il est facturé au tarif Mode B multiplié par le nombre de participants, et tous les participants passent en Mode B sans annonces — **PRIME SUR FR35**
FR43: Le plafond de participants d'un Salon est configurable et initialisé à 3 — **REMPLACE FR2** (« exactement un invité »)
FR44: L'ordre de restitution est premier arrivé premier servi : aucun tour de parole, aucune demande de parole, aucune attribution par l'agent — **FR9 SUPPRIMÉE**
FR45: L'hôte peut couper le micro d'un participant ; cette action ne donne ni ne retire la parole, l'ordre restant FCFS
FR46: Chaque participant occupe sa propre room LiveKit avec son interprète dédié et reçoit la restitution dans sa langue, sans audio partagé — **ÉTEND FR15**, **REND FR17 SANS OBJET** (l'écho devient impossible par construction)
FR47: Un lien de jonction à usage unique distinct est émis pour chaque invité — **ÉTEND FR5**
FR48: *(retirée — fusionnée dans FR40 ; il n'existe pas de tarif de groupe distinct)*
FR49: Quand le retard de l'interprète d'une room dépasse le seuil de saturation, **ce participant seul** reçoit le signal vocal « Vocaliz is busy » et l'ajout de ses propres messages au journal est suspendu jusqu'au retour sous le seuil de déblocage. La saturation est **par room** : chaque interprète étant indépendant et allant à son rythme, les autres participants ne sont ni avertis ni bloqués
FR50: Une annonce porte un **ensemble de géolocalisations cibles** et un **ensemble de langues cibles** — celles parlées par les humains à qui elle sera lue. L'interprète d'un participant sélectionne une annonce dont les deux ensembles contiennent respectivement sa géolocalisation et sa langue détectée, et la lui lit dans sa langue ; des participants d'un même Salon peuvent recevoir des annonces différentes
FR51: Toute personne s'inscrit avec une adresse courriel, un numéro de téléphone, ou les deux, et reçoit **une seule fois à vie un crédit offert de 5 USD**, utilisable dans n'importe quel mode payant et tous rôles confondus (hôte ou invité). Exprimé en monnaie plutôt qu'en minutes, ce crédit s'adapte au tarif du mode choisi. **Le crédit n'est accordé que si aucun des identifiants fournis n'a déjà servi** : tout identifiant ayant déjà donné lieu à un crédit est brûlé **définitivement, sans péremption**. Le **crédit lui-même expire 30 jours calendaires** après son octroi, calculé **à la seconde** — **REMPLACE FR19**, **AMENDE FR18**, **REND FR27 SANS OBJET**
FR52: Les messages d'un Salon sont bornés à 500 caractères maximum et découpés sur frontière de phrase ; aucune insertion tierce à l'intérieur d'une intervention découpée, sauf au-delà du plafond de monologue
FR53: Quand le retard d'un interprète dépasse le seuil de condensation, il restitue les messages en attente sous forme condensée plutôt qu'intégrale, et l'annonce explicitement au participant
FR54: Les paramètres opérationnels du Salon sont persistés individuellement et modifiables sans déploiement
FR55: **À solde épuisé, le Salon du participant se termine.** Il n'existe aucun palier gratuit vers lequel se replier. La fin est précédée d'une **alerte** déclenchée dès que le solde couvre moins de `seuil_alerte_solde` (3 min), afin de laisser le temps de recharger. **Si le participant est l'hôte, le Salon se ferme pour tout le monde** — aussi son alerte est-elle déclenchée plus tôt, à `seuil_alerte_hote` (5 min), et lui rappelle-t-elle explicitement cette conséquence. L'épuisement du seul `solde_offert` ne déclenche rien tant que `solde_paye` prend le relais : il donne lieu à une simple **annonce de transition** — « ton crédit de bienvenue est terminé, je continue avec ton solde » — sans interruption
> **Identité — règle de base (FR51).** Un identifiant est **soit une adresse courriel, soit un numéro de cellulaire, soit les deux**. Un seul suffit pour s'inscrire et pour utiliser le produit. Toute règle du système doit fonctionner avec un identifiant unique ; disposer des deux n'ouvre que deux capacités supplémentaires : recevoir les liens sur deux canaux, et modifier l'un des deux en conservant l'autre comme ancre (FR64).

FR56: **Le paiement précède l'usage.** Un payeur alimente un **solde prépayé** avant de consommer un mode payant — des secondes en banque. Le solde est tenu **en millicents** — millièmes de cent — et **décrémenté toutes les 5 secondes** (`intervalle_echantillonnage`) : le taux de consommation dépend du palier et de l'ensemble des participants que le payeur porte — invités couverts par FR42, participants téléphoniques et leur supplément de FR57. Le **reste fractionnaire est reporté d'un tick au suivant**, afin qu'aucune dérive ne s'accumule. **Seuls les blocs de 5 secondes complétés sont facturés** : un bloc entamé n'est jamais débité, l'arrondi se faisant toujours **en faveur du client**. Le cent reste l'unité d'**affichage et de prélèvement**, jamais celle de comptabilisation. Le solde est **présenté à l'utilisateur en secondes restantes**, dérivées du taux effectif à l'instant considéré. Quand il descend sous `seuil_alerte_solde`, une **recharge** est déclenchée, précédée d'une demande vocale au payeur. **Si un moyen de paiement est déjà enregistré chez Stripe, le débit se fait par `PaymentIntent` hors session** — en quelques secondes, sans quitter la conversation. Le lien envoyé **par courriel et par SMS** n'est que le **chemin de repli**, réservé au premier paiement ou à l'échec du débit hors session. Le montant de la recharge suit la granularité choisie par le payeur — `weekly_budget_limit` (10 USD, par défaut) ou `monthly_budget_limit` (43,33 USD). Le solde inutilisé est **reporté sans expiration**. **À solde épuisé, le Salon se termine** (FR55) — il n'existe aucun palier gratuit vers lequel se replier, et le solde ne devient jamais négatif. **La séquence de clôture est le seul usage autorisé à solde zéro** : elle n'est jamais facturée et se borne à sa propre durée. Le **compteur cumulatif à vie** n'est jamais réinitialisé
FR57: L'hôte peut inviter vocalement un **numéro de téléphone** à rejoindre le Salon. L'appelé reçoit un appel entrant et se voit attribuer sa propre room LiveKit et son propre interprète IA, sans inscription ni application. **L'hôte choisit son palier parmi A, B ou C** — le mode Base n'est pas offert par téléphone — et paie ce palier **majoré de `supplement_telephonique` (7,50 USD/h)**. C'est **toujours** l'hôte qui paie un participant téléphonique, que l'option « l'hôte paie tout » (FR42) soit active ou non
FR58: L'interprète de chaque participant lui annonce, dans sa propre langue, les langues détectées des autres humains présents dans le Salon. **Dès qu'un participant prend la parole pour la première fois, il est présenté aux autres avec sa langue**, juste avant la restitution de son premier message
FR59: Un participant rejoignant un Salon déjà en cours peut recevoir, dans sa langue, la conversation tenue depuis la création du Salon, lue depuis le journal persisté (NFR8). **L'hôte décide, au moment de l'invitation tardive, si l'arrivant y a accès** — c'est une décision d'accès, distincte de la forme de restitution. **La forme suit ensuite la règle générale de FR53** : restitution intégrale si le retard résultant est sous `seuil_condensation`, condensée au-delà. Quand l'accès est accordé, les participants déjà présents en sont informés
FR60: L'interprète retire systématiquement les pauses mortes et les hésitations non signifiantes (« euh », faux départs, répétitions involontaires) de la parole de son humain **avant l'ajout au journal**. Le journal ne contient que du contenu utile. Le nettoyage est toujours actif, quel que soit le mode ou le palier
FR61: Une pause est jugée **signifiante** lorsqu'elle dépasse `seuil_pause_signifiante` (2 000 ms). Elle est alors convertie en **métadonnée inscrite dans le texte du journal**, au format `[pause=N]` où `N` est la durée en **millisecondes**, plafonnée à `pause_max` (5 000 ms). En deçà du seuil, la pause relève de FR60 et est supprimée. Cette métadonnée est comprise et appliquée par les seuls interprètes IA ; elle n'est **jamais prononcée** ni affichée
FR62: Quand plusieurs prises de parole de l'interprète sont prêtes au même instant, elles sont émises dans cet ordre déterministe : **1.** signal de saturation (FR49) et demande de recharge (FR56) · **2.** alerte de solde bas et annonce de fin de Salon imminent (FR55) · **3.** annonce publicitaire (FR39). Aucune n'est supprimée : l'ordre les séquence, il ne les arbitre pas
FR67: Tout crédit offert — **bienvenue automatique de 5 USD** comme **réactivation manuelle de 3 USD** — donne lieu à une **écriture comptable** distincte, conservée durablement. Chaque écriture suit son crédit dans quatre états : **émis**, **consommé**, **périmé non consommé** et **abandonné par suppression de compte**. L'invariant `émis = consommé + périmé + abandonné` vaut pour toute écriture close. La charge réelle est celle du **montant consommé**, seul à engager un coût fournisseur. Des totaux par période sont produits pour chaque état
FR68: Le `solde_paye` donne lieu à un **journal comptable symétrique**, suivant les mouvements dans le temps : **encaissé**, **consommé**, **remboursé**, et **restant dû à la clôture** de la période. Ce dernier montant est le **passif envers les utilisateurs** — l'argent client détenu à l'instant considéré. Il n'est jamais mêlé aux crédits offerts, qui sont une charge et non une dette
FR75: Le **mode conduite** est **vocal uniquement** : l'écran devient **noir**, sans rien à regarder. Il suspend la vidéo (FR72), les sous-titres (FR73) et les voyants de parole (FR74) — non pour les masquer, mais pour **supprimer la raison de baisser les yeux**. La conversation vocale se poursuit inchangée dessous
FR76: Le mode conduite s'active et se désactive **manuellement par un interrupteur**, et **automatiquement dès que la position GPS se déplace à plus de `vitesse_activation_conduite` (10 km/h)**. La vitesse est calculée **sur l'appareil**, jamais transmise ni conservée. **Une sortie manuelle prime** : elle suspend l'activation automatique pour le reste du Salon, faute de quoi un passager serait enfermé dans un écran noir pour tout son trajet
FR74: Un **voyant de parole** indique, pour **chaque paire humain-interprète du Salon**, qui est en train de parler : **vert** quand la voix est active, **rouge** quand elle ne l'est pas. Chaque participant voit l'état de **toutes les paires**, pas seulement de la sienne — sans quoi il ignorerait que quelqu'un d'autre est en train de s'exprimer, puisqu'il ne l'entend jamais directement
FR73: Des **sous-titres en direct traduits** sont disponibles pour l'hôte comme pour chaque participant, **sur le web et sur mobile**. Ils sont offerts dans **toutes les langues que la traduction textuelle supporte**, un ensemble **plus large** que celui des langues parlées par le speech-to-speech : on peut donc suivre une conversation en lisant dans une langue que la voix ne saurait pas prononcer. Chaque participant choisit sa langue de sous-titres et la taille de leur affichage, indépendamment des autres
FR72: Un participant peut activer une **vidéo muette en direct** de lui-même, visible des autres participants. La vidéo ne porte **aucun son** — l'audio reste intégralement dans le chemin des interprètes — et n'est **jamais enregistrée** : elle est vécue en direct puis perdue. Elle est **optionnelle et désactivée par défaut**, chacun décidant pour lui-même. Sa fonction est l'**assurance d'identité** : savoir que son interlocuteur est bien la personne annoncée
FR71: Une recharge effectuée depuis un **navigateur** bénéficie d'un **rabais de 5 %** (`rabais_recharge_web`) par rapport à la même recharge initiée depuis l'application mobile, l'utilisateur en étant informé au moment du choix. Le taux est ventilable **par plateforme et par région**, les commissions de magasin évitées allant de 5 % à 30 % selon la combinaison
FR70: Toute personne peut, depuis l'interface web ou mobile, **obtenir une copie des données la concernant** et **demander leur effacement**. La demande est traitée dans un délai borné, après vérification de son identité. L'effacement porte sur ses propres paroles dans les journaux et sur ses données de compte ; il **pseudonymise** ce qui doit être conservé au titre d'obligations comptables, et **ne rétablit jamais** l'éligibilité au crédit de bienvenue
FR69: Après **un an d'inactivité** d'un utilisateur dont le `solde_paye` est positif, un courriel lui est envoyé lui signalant que son compte chez **Vocaliz.net** est inactif depuis un an et lui indiquant **le solde restant à son compte**. Le message est envoyé en copie à **s.degrandpre@vocaliz.net**. L'envoi est renouvelé à chaque anniversaire d'inactivité tant que le solde reste positif, et chaque tentative est journalisée
FR66: L'exploitant peut accorder manuellement un **second crédit** à un utilisateur ou à une cohorte, **par commande en ligne exécutée depuis l'environnement de production**, malgré le registre des identifiants brûlés, à condition qu'au moins `delai_min_second_cadeau` se soit écoulé depuis le crédit précédent. Le montant est choisi à l'octroi et peut différer du crédit de bienvenue. Chaque octroi est **journalisé** — auteur, horodatage, identifiants visés, montant, motif. Le registre n'est jamais effacé : c'est une **exception explicite**, jamais une péremption. **Aucune interface d'administration n'est construite** ; le contrôle d'accès est celui de l'environnement de production
FR65: À l'inscription, l'utilisateur choisit un **nom d'utilisateur** unique et un **mot de passe**. Ceux-ci constituent une voie d'authentification à part entière, en complément du code à usage unique envoyé sur un identifiant. **Pour une demande de remboursement, la vérification par le moyen de paiement Stripe enregistré est également recevable** : elle permet de restituer le `solde_paye` d'une personne ayant perdu l'accès à ses identifiants comme à son mot de passe
FR64: Depuis l'interface web ou mobile, un participant peut modifier **l'un** de ses deux identifiants en conservant l'autre — changer son courriel en gardant son numéro, ou changer son numéro en gardant son courriel — **jamais les deux à la fois**. L'identifiant conservé sert d'**ancre de continuité**. Le nouvel identifiant est vérifié puis inscrit au registre des identifiants brûlés. **Le `solde_offert` conserve son montant courant : il n'est ni réattribué, ni remis à 5 USD**
FR63: Un mécanisme périodique s'exécute **toutes les 5 secondes** et vérifie, pour chaque payeur actif, que son `solde` couvre **un bloc complet supplémentaire** au taux effectif. Le coût de ce bloc est **arrondi à la hausse au cent** — la vérification est conservatrice, à l'inverse de la facturation qui arrondit vers le bas. Si la couverture est insuffisante, l'interprète en avertit poliment le participant et la bascule en mode Base est appliquée, une recharge étant déclenchée dans le même temps

**Paramètres persistés (FR54) et valeurs initiales :**

```
plafond_participants          3
seuil_saturation              300 s      → déclenche « Vocaliz is busy » + blocage
seuil_deblocage               240 s      → hystérésis, évite l'oscillation
seuil_condensation            120 s      → doit rester < seuil_saturation
plafond_monologue             300 s
taille_max_message            500 caractères
credit_bienvenue              5 USD      → solde_offert accordé une fois à vie (FR51)
peremption_credit             2 592 000 s → 30 jours CALENDAIRES, expiration du solde_offert
                                            octroi + 30 × 86 400 s, à la seconde près
                                            le REGISTRE des identifiants brûlés, lui, ne périme jamais
avertissement_peremption      604 800 s   → 7 jours avant l'échéance, sur les canaux disponibles
retention_journal             1 an        → depuis la CRÉATION du Salon ; au terme, journal et curseurs
                                            sont effacés automatiquement (NFR8)
delai_min_second_cadeau       90 jours    → délai minimal avant qu'un administrateur puisse
                                            accorder un second crédit malgré le registre (FR66)
credit_reactivation           3 USD       → montant par défaut d'un second crédit ; surchargeable
                                            à l'octroi. Achète 1 h 30 en Base, 36 min en Mode A
prix_mode_base                3 USD/h    → prix plancher ; il n'existe AUCUN palier gratuit
                                            tous les prix absorbent 30 % de commission de magasin (÷ 0,70)
                                            sous 1 M$ de ventes, la commission réelle n'est que de 15 % :
                                            les 15 points d'écart sont une marge de croissance assumée
seuil_alerte_solde            180 s      → quand le solde couvre moins de 3 min au taux effectif,
                                           la demande de recharge est déclenchée (FR63)
seuil_alerte_hote             300 s      → seuil relevé pour un HÔTE : son épuisement ferme le Salon
                                           pour tout le monde, il mérite plus de préavis (FR55)
preavis_fermeture_invites     15 s       → préavis donné aux invités avant la fermeture du Salon,
                                           sans jamais en nommer la cause ni la personne (FR55)
prix_mode_a                   7,50 USD/h
prix_mode_b                   15 USD/h   (promotionnel)
prix_mode_c                   22,50 USD/h
modele_mode_a                 grok-voice-think-fast-1.0
modele_mode_b                 grok-voice-think-fast-1.0
modele_mode_c                 grok-voice-think-fast-2.0
frequence_annonces_mode_c     aucune
frequence_annonces_base       1 / 5 min
frequence_annonces_mode_a     1 / 10 min
delai_offre_upgrade           60 s
max_repetitions_offre         2
periode_encaissement_defaut   weekly     → granularité de recharge par défaut ; « monthly » optionnel, au choix du payeur
weekly_budget_limit           10 USD     → montant PLANCHER d'une recharge en granularité hebdomadaire (FR56)
monthly_budget_limit          43,33 USD  → montant plancher en granularité mensuelle : 10 × 52 ÷ 12
montant_recharge              = plancher → réglable par le payeur, entre le plancher de sa granularité
                                           et `plafond_recharge`
intervalle_echantillonnage    5 s        → cadence unique du décrément (FR56) et de la vérification (FR63)
                                         → unité de facturation : seuls les blocs de 5 s COMPLÉTÉS sont facturés
rabais_recharge_web           5 %        → rabais sur une recharge initiée depuis un navigateur (FR71)
                                            VENTILABLE par plateforme, par région ET PAR TRANCHE DE REVENU :
                                            la commission évitée va de 5 % (Android É.-U. sous 1 M$)
                                            à 30 % (iOS hors É.-U. au-dessus de 1 M$)
vitesse_activation_conduite   10 km/h    → au-delà, le mode conduite s'active seul (FR76)
vitesse_sortie_conduite       5 km/h     → HYSTÉRÉSIS : en deçà seulement, la sortie automatique
                                            est envisagée — un feu rouge ne doit pas rallumer l'écran
delai_sortie_conduite         120 s      → durée pendant laquelle il faut rester sous le seuil de
                                            sortie avant que le mode ne se désactive de lui-même
debit_max_video               200 kbps   → plafond de débit par flux vidéo, ≈ 240p à 15 fps (FR72)
                                            DÉCISION PRODUIT, non un réglage provisoire : la vignette sert à
                                            reconnaître un visage, pas à lire une expression
                                            à ce niveau la vidéo coûte ≈ 2 % du palier Base ;
                                            en 720p elle en coûterait 15 % pour aucun gain d'identification
plafond_recharge              500 USD    → montant maximal d'une recharge, et donc du passif porté par usager
                                         → un hôte qui couvre d'autres participants doit relever son montant :
                                           son taux effectif est la SOMME de ce qu'il porte (FR63)
                                         → la recharge est déclenchée par le BESOIN, jamais par le calendrier ;
                                           le solde inutilisé est reporté sans expiration
delai_expiration_recharge     300 s      → au-delà, la demande de recharge en attente expire et les modes
                                           mémorisés sont abandonnés ; on reste en Base (FR56)
supplement_telephonique       7,50 USD/h → majoration du palier choisi, toujours à la charge de l'hôte (FR57)
mode_telephonique_par_defaut  Mode B     → palier appliqué si l'hôte n'en précise aucun ; Base non offert par téléphone
seuil_pause_signifiante       2000 ms    → en deçà la pause est supprimée (FR60), au-delà elle devient `[pause=N]` (FR61)
pause_max                     5000 ms    → plafond inscrit dans la métadonnée, quelle que soit la durée réelle
taille_max_condense           1000 car.  → borne de sortie de toute condensation (FR53), y compris un rattrapage d'arrivant
historique_arrivant_par_defaut oui       → accès de l'arrivant à l'historique ; l'hôte le refuse explicitement (FR59)
```

**Deux compteurs distincts, à ne pas confondre :**

```
solde  =  solde_offert  +  solde_paye        tenu EN MILLICENTS, décrémenté toutes les 5 s
                                             reste fractionnaire reporté au tick suivant
                                             affiché en SECONDES restantes, dérivées du taux effectif
                                             arrondi au cent à l'affichage et au prélèvement, jamais en interne
                                             jamais négatif

solde_offert       cadeau de bienvenue de 5 USD offert par Vocaliz, UNE FOIS à vie (FR51)
                   accordé seulement si AUCUN identifiant fourni n'a déjà servi
                   EXPIRE 30 jours calendaires après l'octroi, à la seconde près
                   libellé de configuration : "Vocaliz welcome credit"
                   consommé EN PREMIER · JAMAIS REMBOURSABLE
                   comptablement : charge d'acquisition, pas un passif
solde_paye         argent réellement versé par l'utilisateur · reporté sans expiration
                   libellé de configuration : "Your topped-up balance"
                   SEUL MONTANT REMBOURSABLE · comptablement : passif à provisionner

⚠ Les deux parts sont PERSISTÉES SÉPARÉMENT. `solde` n'est qu'une vue calculée.
  Tout mouvement consigne la part qu'il affecte — piste d'audit opposable en litige.
total_cumulatif    total payé à vie · jamais remis à zéro
```

**Il n'existe plus de « quota » distinct.** Le crédit offert est une part du solde, pas un compteur séparé : son épuisement n'est un événement que si `solde_paye` ne prend pas le relais — auquel cas c'est la vérification de couverture de FR63 qui agit, comme pour n'importe quel solde insuffisant. **Un seul chemin mène au mode Base.**

**Ce que 5 USD achètent**, selon le mode choisi :

```
Base      3 $/h  →  1 h 40        Mode B     15 $/h  →  0 h 20
Mode A 7,50 $/h  →  0 h 40        Mode C  22,50 $/h  →  0 h 13
```

**Coût réel de l'acquisition** : au maximum **3,68 $** par nouvel inscrit — une heure de Mode A au coût de 3,68 $/h. Le cadeau reste attractif tout en descendant sous le seuil qui rendait sa collecte industrielle intéressante.

**Un seul événement, toutes les 5 secondes.** Le décrément (FR56) et la vérification de couverture (FR63) partagent la même cadence : on débite le bloc écoulé, puis on vérifie que le solde couvre le suivant.

**Pourquoi cette granularité.** L'arrondi vers le bas abandonne le bloc entamé. Sur des Salons courts, la taille du bloc décide donc de ce qui est perdu :

```
bloc de 60 s   →  perte moyenne 30 s/Salon   =  10 % d'un Salon de 5 min
bloc de 15 s   →  perte moyenne 7,5 s/Salon  =  2,5 %
bloc de  5 s   →  perte moyenne 2,5 s/Salon  =  0,8 %
```

Le surcoût d'infrastructure est nul : 180 000 ticks/mois à 100 usagers représentent 0,07 écriture par seconde et ≈ 0,07 $/mois d'I/O Aurora, sans effet sur le plancher de 0,5 ACU déjà payé.

**Pourquoi les millicents et non les cents.** Aucun intervalle ne produit un nombre entier de cents pour tous les paliers — la fraction est inévitable, elle ne peut qu'être portée :

```
bloc de 5 s     Base 0,417 ¢  ·  Mode A 1,042 ¢  ·  Mode B 2,083 ¢  ·  Mode C 3,125 ¢  ·  taux max 8,333 ¢
```

**Implémentation exacte du report.** `500 ÷ 720` est un développement décimal illimité : aucune unité décimale — cent, millicent, microcent — ne le représente exactement. Le report doit donc être un **accumulateur entier**, jamais un flottant :

```
consommation  +=  blocs_complétés × tarif_horaire_en_cents     ← entier, unité « cent·bloc »
montant_dû     =  consommation ÷ 720, ARRONDI VERS LE BAS      ← 720 blocs de 5 s dans une heure
                                                                 une seule division, au moment de facturer
```

Aucun flottant n'entre jamais dans le grand livre, et l'arrondi n'a lieu qu'une fois, à la frontière, dans le sens favorable au client.

**Arrondi aux blocs complétés.** Un Salon de 1 h 1 min 2 s est facturée **1 h 1 min 0 s** — les 2 secondes sont abandonnées. L'échantillonnage se faisant aux 5 secondes, facturer une fraction de bloc reviendrait à facturer un temps qui n'a jamais été mesuré : c'est ce que cette règle évite, et avec elle toute contestation possible. Conséquence assumée : un Salon de moins de cinq secondes n'est pas facturée.

**Réserve de mise en œuvre.** À 5 secondes, la gigue d'ordonnancement devient une fraction non négligeable du bloc — 200 ms de retard représentent 4 % d'un bloc, contre 0,3 % à la minute. Le débit doit donc se calculer sur le **temps réellement écoulé** entre deux ticks, jamais sur la cadence nominale supposée.

**Taux de consommation effectif**, en cents par seconde — c'est la somme de tout ce que le payeur porte :

```
taux_effectif = Σ  ( prix_palier_p + supplement_telephonique si p est téléphonique )  ÷ 3600
                p ∈ participants portés par le payeur

exemple  hôte en Mode B + 1 invité couvert (FR42) + 1 téléphonique en Mode C
         = (15 + 15 + 22,50 + 7,50) ÷ 3600  =  60 $/h  =  1,667 cent/s
```

Le taux change dès qu'un participant rejoint, quitte ou change de palier — d'où un solde en cents et non en secondes. Les secondes affichées sont une **vue**, recalculée à chaque changement de taux.

**Ordre de consommation :** `solde_offert` d'abord, puis `solde_paye`. À solde nul, **fin de Salon** (FR55) — jamais de découvert, jamais d'impayé, et aucun palier gratuit vers lequel se replier.

### NonFunctional Requirements

NFR1: Performance — Aucun seuil de latence formel n'est fixé pour le MVP ; la latence du pipeline voix→traduction→voix sera validée empiriquement une fois l'usage réel commencé.
NFR2: Security — Salon ne conserve aucun transcript de Salon pour le MVP (traitement éphémère en mémoire) ; les liens d'invitation à usage unique expirent après la première connexion ; les méthodes de paiement sont gérées entièrement via Stripe (tokenisation).
NFR3: Integration — En cas d'indisponibilité de xAI, LiveKit, ou Stripe, le système doit présenter un message d'erreur clair plutôt qu'un échec silencieux.
NFR9: Confidentiality — Toute donnée personnelle persistée est **chiffrée au repos** : journal et curseurs (NFR8), soldes et écritures comptables, identifiants, consentements de géolocalisation, registre des identifiants brûlés. Les clés sont gérées par AWS KMS et font l'objet d'une rotation. Les sauvegardes sont chiffrées au même titre. **Aucun contenu de conversation n'est jamais écrit dans les journaux applicatifs.**
NFR8: Durability — **Le journal de chaque Salon et les curseurs de chaque interprète sont persistés**, afin de reprendre une conversation après une panne et de prouver la diffusion des annonces. La **durée de conservation est d'un an à compter de la création du Salon**, après quoi le journal et ses curseurs sont **effacés automatiquement**. Cette exigence **abroge la partie de NFR2** qui promettait un traitement éphémère en mémoire et l'absence de tout transcript : Vocaliz conserve désormais le contenu des conversations pendant un an. Restent à définir : le chiffrement au repos et les modalités d'accès et d'effacement à la demande de la personne concernée.

> ⚠️ **NFR2 amendée.** La promesse « aucun transcript de Salon, traitement éphémère en mémoire » ne tient plus. Ce qui subsiste de NFR2 : liens d'invitation à usage unique et tokenisation Stripe.

NFR4: Observability — Le système instrumente les métriques de PR-VOICE-001 : taux d'adoption speech-to-speech, répartition Mode A / Mode B, taux de complétion en mode Base, satisfaction par mode, taux de conversion Base→payant, ratio de coût d'exploitation par mode, taux de Salons sans incident. S'y ajoutent le retard par participant, le retard maximal du Salon, le taux de condensation, le nombre de blocages et le **ratio de méta-parole**, reliés aux paramètres de FR54.

> **Ratio de méta-parole** — proportion du temps de parole d'un interprète consacrée à parler *de* la conversation plutôt qu'à la restituer.
> **Compté comme méta-parole :** présentation des participants (FR58), phrase d'annonce d'une condensation (FR53), signal « Vocaliz is busy » (FR49), annonces publicitaires (FR39), alerte de solde bas et annonce de fin de Salon (FR55), demande vocale de recharge (FR56), auto-présentation au participant téléphonique (FR57).
> **Non compté :** toute restitution issue du journal, y compris le contenu **condensé** — seule la phrase qui annonce la condensation est de la méta-parole, pas le résumé lui-même.
> **Mesuré par palier** (Base / Mode A / Mode B / Mode C), le palier le moins cher cumulant mécaniquement le plus d'interruptions.

S'y ajoutent deux métriques de conversion du crédit de bienvenue :

> **Taux de conversion avant péremption** — pourcentage des nouveaux inscrits ayant effectué **au moins une recharge Stripe** avant l'expiration de leur crédit de bienvenue (30 jours). Mesuré **par cohorte d'inscription**, une cohorte n'étant close qu'une fois sa fenêtre de péremption écoulée.
>
> **Délai avant première recharge** — nombre de **minutes écoulées entre l'inscription et la première recharge Stripe réussie**. Publié en **distribution** — médiane, p25, p75, p90 — et non en moyenne seule, une poignée de retardataires suffisant à rendre une moyenne trompeuse. Les personnes n'ayant jamais rechargé sont **exclues du délai** mais **comptées au dénominateur** du taux de conversion.
NFR5: Testability — Le projet fournit une infrastructure de test de charge capable de simuler jusqu'à 50 participants et d'asserter les retards par curseur, le retard maximal, la latence p50/p95, le déclenchement de la condensation, les événements de saturation et la durée des blocages, sans consommer de crédits fournisseur.
NFR7: Auditability — Les faits financiers et opérationnels sont écrits **une seule fois**, dans un **flux d'événements unique, append-only**, qui fait seul autorité. Le journal d'audit des octrois (FR66), les écritures comptables des crédits offerts (FR67) et du solde payé (FR68), ainsi que les métriques de NFR4, en sont des **vues dérivées** — jamais des écritures parallèles. Trois écritures concurrentes du même fait finissent toujours par diverger, et rien ne permet alors de dire laquelle a raison.
NFR6: Modularity — L'interprète est un port ; l'orchestrateur ne référence aucun fournisseur en dur. Trois adaptateurs sont livrés : `InterpreteS2S` (temps réel), `InterpreteBase` (STT+LLM+TTS), `InterpreteFake` (scripté, déterministe). Cette contrainte réduit également l'exposition au fournisseur unique signalée en NFR3.

> **Deux ensembles de langues, délibérément différents.**
>
> ```
> LANGUES PARLÉES    intersection des adaptateurs d'interprète — le speech-to-speech
>                    étant le plus restrictif, c'est lui qui définit la liste
>                    → changer de palier ne change JAMAIS les langues parlées disponibles
>
> LANGUES ÉCRITES    toutes celles que la traduction textuelle supporte — ensemble PLUS LARGE
>                    → on peut suivre en lisant une langue que la voix ne sait pas prononcer
> ```
>
> Une langue supportée par le seul adaptateur Base n'est pas ajoutée aux **langues parlées** — elle disparaîtrait à la montée en gamme. Mais elle peut parfaitement figurer parmi les **langues de sous-titres** (FR73), où aucun adaptateur vocal n'intervient.

### Additional Requirements

- Starter template worker d'agent : `lk app create --template agent-starter-python` + `uv add "livekit-agents[xai,silero,turn-detector]"` (Story 1.1)
- Starter template mobile : `npx create-expo-app` avec Expo Development Build (pas Expo Go) requis dès le départ pour supporter `@livekit/react-native` (Story 1.2)
- Infrastructure AWS : Lambda + API Gateway (API REST), ECS Fargate (worker d'agent xAI), Aurora Serverless v2 PostgreSQL, S3+CloudFront (page de jonction web), Secrets Manager (clés API), CloudWatch Logs (monitoring), GitHub Actions (CI/CD)
- Intégrations tierces : xAI (plugin `livekit-agents[xai]`), LiveKit Cloud (managé, pas d'auto-hébergement), Stripe (paiement), AWS SES (OTP et invitations par courriel)
- Base de données : schéma relationnel (`users`, `Salons`, `friends`, `billing_events`), migrations Alembic
- Authentification : OTP par courriel (AWS SES), JWT à courte durée pour utilisateurs inscrits, token à usage unique pour jonction anonyme
- Métrage de facturation : heartbeat périodique (30s) du worker vers l'API + callback final, pour fiabilité en cas de déconnexion
- Règle métier "ami Salon" : un contact ne devient un ami Salon (livraison in-app) que s'il s'est lui-même inscrit avec une adresse courriel vérifiée ; sinon, joignable uniquement par SMS
- Conventions : JSON camelCase (alias Pydantic) / Python snake_case interne, erreurs API au format `{detail: string}`, dates ISO 8601 UTC

**Révision 2026-08-08 — topologie multi-rooms.** L'architecture d'origine (une `AgentSession` LiveKit unique par salle, `xai.realtime.RealtimeModel` comme composant LLM) est remplacée :

```
SALON  =  { room₁ … room_N }  +  ORCHESTRATEUR

room_i    humain_i  ⟷ audio ↔ audio ⟷  interprète_i   [port : S2S | Base | Fake]
                                              ↕  messages texte EN, ≤ 500 caractères

ORCHESTRATEUR
  JOURNAL      append-only, en mémoire, ordonné par horodatage d'arrivée
               ↑ l'ordre FCFS de FR44 EST l'ordre du journal — rien d'autre à maintenir
  curseur_i    position atteinte par l'interprète du participant i
  retard_i     = tête du journal − curseur_i

  condensation · saturation + blocage des ajouts · plafond de monologue
  configuration persistée · métrage

TABLES        annonces   (créatif TEXTE dans la langue où l'annonceur l'a écrit,
                          géolocalisations cibles, LANGUES cibles, substitutions par langue)
                          ↳ même modèle que les tours : original + traductions dérivées
              diffusions (participant, annonce, horodatage)
              ↑ l'interprète y PUISE au moment voulu — aucune file, aucun push
              ↑ langues et géolocalisations sont des ENSEMBLES : une même annonce
                s'adresse à plusieurs langues et plusieurs régions
```

**Il n'existe pas de file de messages.** Un message n'est pas livré une fois puis retiré : il est livré N fois, une par participant, à des rythmes différents (retard propre, annonces, condensation). Il n'y a donc jamais de moment où on pourrait le retirer. Une seule structure — le journal — plus un curseur par interprète. Tout se dérive de là :

| Concept | Dérivation |
|---|---|
| Ordre FCFS (FR44) | ordre du journal |
| Retard d'un interprète | `tête − curseur_i` |
| Saturation (FR49) | `retard_i > seuil_saturation` — **par room**, jamais globale |
| Condensation (FR53) | avancer `curseur_i` plus vite que le temps réel, en résumant l'intervalle sauté |
| Blocage (FR49) | refuser les ajouts **de la room saturée seule** |
| Accès à l'historique (FR59) | `curseur_i = 0` si accordé, `curseur_i = tête` sinon |
| Forme de la restitution | conséquence du retard, jamais une décision distincte : intégrale sous `seuil_condensation`, condensée au-delà |
| Nettoyage (FR60) | à l'**ingestion**, une seule fois — le journal ne contient que du contenu utile |
| Métadonnée (FR61) | `[clé=valeur]` inline dans le texte du journal — `[pause=4000]` = silence de 4 000 ms. Lue par les interprètes, jamais prononcée, non comptée comme contenu |

**Il n'existe aucune file dans le système.** Deux modèles, tous deux en lecture :

```
messages   journal partagé   · l'interprète AVANCE SON CURSEUR    · restitués N fois
annonces   table d'inventaire · l'interprète PUISE à la demande   · diffusion enregistrée
```

Migrer les annonces vers le journal casserait le ciblage géographique par participant (FR50) et les fréquences différenciées par palier (FR33) : un message s'adresse à tous, une annonce à une seule personne. La table `diffusions` sert à ne pas rejouer une annonce déjà entendue, à faire respecter les fréquences, et à alimenter NFR4.

**Trois leviers de régulation, dans cet ordre :** le **nettoyage** (FR60) réduit le volume à la source, une fois pour tous ; la **condensation** (FR53) rattrape par room quand le retard s'installe ; la **saturation** (FR49) alerte et suspend les ajouts d'une room quand les deux premiers ne suffisent plus.

- **Journal polyglotte, aucun pivot** (décision du 2026-08-08) : chaque tour est inscrit **dans la langue où il a été prononcé** — l'émetteur fait l'original. Les traductions sont des lignes **dérivées de cet original**, jamais d'une autre traduction. Trois interlocuteurs en trois langues produisent trois originaux, et chaque restitution est **à un seul saut** de celui qu'elle traduit.

```
utterances               tour prononcé · langue de l'ÉMETTEUR · jamais écrasé
utterance_translations   (tour, langue cible) → texte · dérivé de l'original · mis en cache
```

  Un pivot — anglais ou autre — aurait imposé deux sauts et deux pertes à toute paire ne l'incluant pas. Il a été envisagé puis écarté : le modèle hérité de Salon est meilleur et déjà construit.

  **Aucune traduction quand elle n'est pas nécessaire.** Un tour déjà dans la langue de celui qui l'écoute ou le lit est restitué tel quel. Dans un Salon monolingue — le cas le plus fréquent, et celui du parcours de référence — **le sous-système de traduction reste entièrement inactif**. Le coût et la latence de traduction sont proportionnels à la **diversité linguistique**, jamais au volume de la conversation.
- **Port Interprète** (NFR6) : l'orchestrateur ne connaît que des identifiants de room, des tours horodatés et leur langue d'origine. Aucun appel fournisseur en dur, aucune langue privilégiée.
- **Anti-écho** : résolu par construction — aucun audio n'est partagé entre participants.
- **Vidéo muette** (FR72) : chemin média **distinct** des rooms d'interprétation, sans aucune piste audio, jamais persisté. Elle n'ajoute ni minutes de participant ni minutes d'agent — **uniquement du transfert de données**, à 0,12 USD/GB. Le coût dépend entièrement du plafond de débit :

```
Salon à 3, par heure       240p/15fps   0,81 GB  →  0,10 $   ≈ +2 % du palier Base
                           360p/24fps   2,0 GB   →  0,24 $   ≈ +5 %
                           720p         6,1 GB   →  0,73 $   ≈ +15 %

À 100 usagers × 5 min/jour · 125 Salon-heures/mois
                           240p   ≈ 12 $/mois     ← +4 % de l'infrastructure
                           720p   ≈ 91 $/mois     ← +28 %
```

  Le plafond `debit_max_video` doit donc être **explicite** : laissé au défaut d'un SDK WebRTC, il monterait à 720p et multiplierait le coût par sept sans améliorer l'identification d'un visage. La vidéo est sacrifiée avant l'audio en cas de dégradation réseau.
- **Journal persisté** (NFR8, décision du 2026-08-08) : le journal de chaque Salon **et** les curseurs de chaque interprète sont écrits durablement, pour permettre la **reprise après panne** et **prouver la diffusion des annonces**. Le journal contenant la conversation complète, il **est** un transcript : **NFR2 est amendée en conséquence** et la promesse de non-conservation ne tient plus. **Conservation : un an depuis la création du Salon**, puis effacement automatique. Restent à définir : chiffrement au repos et modalités d'accès et d'effacement à la demande.
- **Hébergement de l'orchestrateur : AWS, ECS Fargate**, dans le même compte et le même réseau que le worker d'interprète. Le journal étant désormais persisté, une instance qui reprend un Salon **relit l'état depuis le stockage** plutôt que de le perdre. L'affinité Salon↔instance reste souhaitable pour la performance, mais elle n'est plus une condition de survie : un déploiement draine par confort, non par nécessité.
- **Nouvelles tables** : configuration des paramètres (FR54), soldes prépayés (`solde_offert` / `solde_paye`, persistés séparément), registre des identifiants brûlés, inventaire d'annonces et diffusions, consentement de géolocalisation, comptes (nom d'utilisateur, condensat de mot de passe).
- **Story 1.1 invalidée** : le starter `agent-starter-python` ne couvre plus la topologie orchestrateur + N rooms.
- **Retour du SMS** : le projet avait délibérément abandonné le SMS au profit du courriel (commits `5180510`, `770c339`). FR56 le réintroduit — le lien d'autorisation Stripe part **par les deux canaux**. AWS SNS redevient donc une dépendance, en plus de SES.
- **SIP téléphonique requis** : FR57 rend obligatoire l'intégration SIP de LiveKit Cloud, décrite comme « optionnelle » dans l'architecture d'origine. Une room SIP est un participant comme un autre du point de vue de l'orchestrateur — même port Interprète, même journal, même curseur. Nouvelle ligne de coût à modéliser : **les minutes téléphoniques sortantes s'ajoutent au coût de l'interprète**, et le tarif Mode B de 10 USD/h n'a pas été calculé en les incluant.
- **Tarifs fournisseurs vérifiés le 2026-08-08** ([docs.x.ai/docs/models](https://docs.x.ai/docs/models), [livekit.com/pricing](https://livekit.com/pricing)) :

```
xAI    grok-voice-think-fast-1.0  0,05 $/min  =  3,00 $/h   ← RETENU (agent/agent.py)
       grok-voice-think-fast-2.0  0,08 $/min  =  4,80 $/h   ← écarté : ruine le Mode A
       Speech-to-Text (streaming) 0,20 $/h    ·  REST 0,10 $/h
       Text-to-Speech             15,00 $/1M caractères
       grok-4.3 (texte)           1,25 $/1M entrée · 2,50 $/1M sortie

LiveKit  minutes d'agent   0,01 $/min = 0,60 $/h  ← un Salon d'agent PAR INTERPRÈTE
         WebRTC            0,0005 $/min ≈ 0,03 $/h
         minutes SIP       0,004 $/min = 0,24 $/h   (offre Ship)
         entrant US local  0,01 $/min = 0,60 $/h
         forfait Ship      50 $/mois, 5 000 minutes d'agent incluses
```

**Coût estimé par participant et par heure** (3 participants, hypothèses de volume TTS et de part d'orchestrateur indiquées) :

**Coût estimé par participant et par heure**, avec `grok-voice-think-fast-1.0` :

Les prix affichés absorbent **30 % de commission de magasin**. La colonne **« net à 15 % »** est ce qui reste tant que les ventes annuelles restent sous un million de dollars — taux réduits d'Apple et de Google — ; la colonne **« net à 30 % »** est le régime de long terme.

| Palier | Prix | Net à 15 % | Net à 30 % | Coût estimé | Marge sous 1 M$ | Marge au-delà |
|---|---|---|---|---|---|---|
| **Base** | 3 $/h | 2,55 $ | 2,10 $ | ≈ **1,58 $/h** | **+0,97** (+1,27 avec pub) | **+0,52** |
| **Mode A** | 7,50 $/h | 6,38 $ | 5,25 $ | ≈ **3,68 $/h** | **+2,70** | **+1,57** |
| **Mode B** | 15 $/h | 12,75 $ | 10,50 $ | ≈ **3,65 $/h** | **+9,10** | **+6,85** |
| **Mode C** | 22,50 $/h | 19,13 $ | 15,75 $ | ≈ **5,45 $/h** | **+13,68** | **+10,30** |
| **Téléphone en A** | 7,50 + 7,50 = 15 $/h | 12,75 $ | 10,50 $ | ≈ **4,44 $/h** (SIP 0,24 + PSTN ~0,60) | **+8,31** | **+6,06** |
| **Téléphone en B** | 15 + 7,50 = 22,50 $/h | 19,13 $ | 15,75 $ | ≈ **4,44 $/h** | **+14,69** | **+11,31** |
| **Téléphone en C** | 22,50 + 7,50 = 30 $/h | 25,50 $ | 21 $ | ≈ **6,24 $/h** | **+19,26** | **+14,76** |

**Deux choses que cette grille encode :**

- **Une marge de croissance, pas une erreur de calcul.** Sous un million de ventes, l'écart entre le taux tarifé (30 %) et le taux réellement prélevé (15 %) revient à l'exploitant. C'est ≈ **150 000 USD** sur le premier million — de quoi financer l'amorçage sans lever de fonds.
- **Aucune hausse de tarif à prévoir.** Le franchissement du million ne déclenche plus de rendez-vous tarifaire : la marge se resserre vers la colonne « net à 30 % », qui reste positive sur les quatre paliers. Les clients acquis pendant l'amorçage ne subissent jamais d'augmentation.

**Taux de commission de référence :**

```
                       sous 1 M$          au-dessus de 1 M$
Apple, achat intégré   15 %               30 %
Google, service        10 %               20 % (nouvelles installations) à 25 % (existantes)
Google, facturation     5 %               5 %
                       ───────            ───────
                       ≈ 15 %             ≈ 30 %

Apple, lien externe     0 % (É.-U.)       0 % (É.-U.) — sous réserve de la Cour suprême
Google, lien web       10 %               15 %
```

> Une recharge par **navigateur** échappe à la commission : le net y vaut le prix affiché, diminué du seul rabais de 5 % de FR71. Avec des tarifs calés sur 30 %, le canal web devient le plus profitable de très loin — jusqu'à 30 points d'écart avec le magasin. Le rabais de 5 % est prudent au regard de cet écart et pourra être relevé, plateforme par plateforme.

> Le surcoût téléphonique réel est de ≈ 0,84 $/h — 0,24 $ de minutes SIP plus ≈ 0,60 $ de terminaison PSTN. Le supplément de 7,50 $/h le couvre environ six fois même après commission de magasin : c'est une **prime de commodité** — rejoindre par simple appel, sans compte, sans application, sans lien à cliquer — et non un recouvrement de coût. Le tarif de terminaison PSTN sortante restant non vérifié, la marge absorbe aussi cette incertitude.
>
> Effet de bord à connaître : à ce niveau, **un participant téléphonique en Mode A coûte à l'hôte le même prix qu'un participant applicatif en Mode B** (10 $/h). Le supplément vaut désormais un palier entier.

**Conséquences :**
1. **Décision prise le 2026-08-08 : `grok-voice-think-fast-1.0` pour les Modes A et B.** Avec la 2.0 à 4,80 $/h, le Mode A perdait 0,48 $/h — le coût de l'interprète absorbait 96 % du prix de vente. La 1.0 à 3,00 $/h rend le palier rentable. Appliqué dans [agent/agent.py](agent/agent.py).
1bis. **La 2.0 n'est pas abandonnée : elle devient le Mode C, à 22,50 USD/h.** Plutôt que de subventionner le meilleur modèle sur un palier qui ne le supporte pas, on le vend à son prix. C'est le port Interprète (NFR6) qui rend cela possible : le modèle devient un paramètre d'adaptateur par palier, pas une constante du produit.
2. **Il n'existe plus aucun palier gratuit (décision du 2026-08-08).** Le mode Base est vendu 3 USD/h contre ≈ 1,58 USD/h de coût — soit 2,55 $ net sous un million de ventes, donc +0,97 $/h avant publicité et +1,27 $/h après. Tous les paliers sont rentables, ce qui referme la seule fuite structurelle du modèle. Corollaire : **il n'existe plus de repli gratuit**, donc un solde épuisé met fin au Salon (FR55) — et ferme le Salon si le payeur est l'hôte.
2bis. **Les tarifs absorbent 30 % de commission de magasin** (majoration ÷ 0,70 puis arrondi), soit le taux plein d'Apple et de Google. Sous un million de ventes, la commission réellement prélevée n'est que de 15 % : **l'écart de 15 points est une marge de croissance délibérée**, ≈ 150 000 USD sur le premier million. Au franchissement du seuil, la marge se resserre sans qu'aucune hausse de tarif ne soit nécessaire — les clients acquis pendant l'amorçage ne subissent jamais d'augmentation.
3. **Coûts fixes dominants à faible volume.** À 100 usagers × 5 min/jour : LiveKit ≈ 158 $/mois + AWS ≈ 165 $/mois = **323 $/mois quoi qu'il arrive**, dont 77 $ dus au seul NAT Gateway et à l'ACU minimum d'Aurora, facturés même à zéro usage.
4. **Planification du forfait LiveKit** : 5 000 minutes d'agent incluses ÷ 3 interprètes ≈ **27 Salons d'une heure par mois** avant facturation à l'usage.
5. **Modèle prépayé (FR56, révisé le 2026-08-08).** Le paiement précède l'usage : le trou d'encaissement disparaît entièrement, ainsi que tout risque d'impayé, de rétrofacturation sur consommation contestée et de créance à recouvrer. Le solde ne devient jamais négatif ; à zéro, le Salon se termine. **Trois conséquences comptables :**
   - **Trésorerie positive** — l'argent entre avant que le coût fournisseur ne sorte. Pour un solopreneur, c'est structurellement plus sûr qu'un postpayé.
   - **Passif à porter** — le solde non consommé est une dette envers l'utilisateur, à provisionner. Reporté sans expiration, il ne s'éteint jamais de lui-même.
   - **Frais Stripe selon la granularité**, le forfait de 0,30 $ étant fixe :

```
recharges de 10 $     →  frais ≈ 5,9 % du montant rechargé
recharges de 43,33 $  →  frais ≈ 3,6 % du montant rechargé
```

   Les deux montants sont homothétiques : `monthly_budget_limit` = 10 × 52 ÷ 12 = 43,33 $.
6. **Non vérifié** : le tarif de terminaison PSTN **sortante** (LiveKit ne publie que l'entrant), le CPM publicitaire réel estimé ici à 25 $, et le mode de facturation LiveKit selon que les interprètes sont managés ou auto-hébergés sur Fargate (écart ≈ 100 $/mois).

### UX Design Requirements

UX-DR1: Design tokens — palette "Salon Parisien" (bourgogne profond, or/laiton en accent, beige ivoire chaud, charbon pour le texte), typographie serif classique pour les titres (ex. Playfair Display) + sans-serif accessible pour le corps
UX-DR2: Composant réutilisable — Indicateur d'Onde Vocale (6 barres animées, états écoute/traduction/silencieux, label ARIA requis)
UX-DR3: Composant réutilisable — Badge Logo Causeuse (grand logo rond, silhouette de causeuse classique à 3 places en ligne dorée, centré en haut de chaque écran)
UX-DR4: Composant réutilisable — Bandeau de Confirmation (affichage d'état d'invitation, non-tapable)
UX-DR5: Composant réutilisable — Badge "Sans Installation" (pilule or, écran de jonction anonyme uniquement)
UX-DR6: Icône vectorielle custom — manipulateur télégraphique du 19ᵉ siècle (clé Morse) pour l'écran de vérification téléphone, remplaçant une icône téléphone générique
UX-DR7: Accessibilité WCAG AA — contraste 4.5:1 minimum, cibles tactiles 44×44px minimum, labels ARIA sur tout élément purement visuel, compatibilité VoiceOver/TalkBack
UX-DR8: Responsive — page de jonction web anonyme fonctionnelle sur mobile et desktop (breakpoint simple <768px/≥768px), layout à une colonne
UX-DR9: Pattern d'interaction voice-first — toute confirmation/erreur annoncée vocalement en premier, affichage visuel secondaire seulement ; récupération gracieuse par nouvelle demande polie en cas d'incompréhension
UX-DR10: Écran d'onboarding — vérification téléphone (OTP), friction minimale, aucune question superflue
UX-DR11: Écran "Home"/invitation — capture de la commande vocale "invite [nom]", confirmation vocale + bandeau visuel
UX-DR12: Écran de Salon — Indicateur d'Onde Vocale actif, sortie par commande vocale ("Je quitte le Salon")
UX-DR13: Écran d'historique — liste simple des Salons passés et partenaires (pas de fil de messages)

### FR Coverage Map

```
FR1:  Epic 2  - Création de Salon (document, URL, ou sans source)
FR2:  Epic 2  - Invitation vocale (ami Salon ou contact)          ⚠ REMPLACÉE par FR43 (Epic 10)
FR3:  Epic 2  - Ajout de source en cours de Salon
FR4:  Epic 3  - Jonction web sans installation                    ⚠ AMENDÉE par FR51 (Epic 10)
FR5:  Epic 3  - Lien à usage unique                               ⚠ ÉTENDUE par FR47 (Epic 10)
FR6:  Epic 2  - Lecture à voix haute
FR7:  Epic 2  - Discussion sans lecture préalable
FR8:  Epic 2  - Contraste d'autres sources
FR9:  Epic 2  - Parole par pauses naturelles                      ⛔ SUPPRIMÉE par FR44 (Epic 6)
FR10: Epic 2  - Compréhension langage naturel, toujours à l'écoute
FR11: Epic 2  - Ajustement vocal de la fréquence d'intervention
FR12: Epic 2  - Détection automatique de langue
FR13: Epic 2  - Affichage dans la langue détectée
FR14: Epic 2  - Expression dans sa propre langue
FR15: Epic 2  - Traduction et lecture dans la langue du destinataire  ⚠ ÉTENDUE par FR46 (Epic 6)
FR16: Epic 2  - Interprétation simultanée sans interrompre
FR17: Epic 2  - Pas d'écho audio                                  ⛔ SANS OBJET — résolu par FR46 (Epic 6)
FR18: Epic 1  - Compte + vérification courriel                    ⚠ AMENDÉE par FR51 (Epic 10)
FR19: Epic 4  - Heure d'essai gratuite à vie                      ⛔ SUPPRIMÉE par FR51 (Epic 8)
FR20: Epic 4  - Métrage précis minute/seconde
FR21: Epic 4  - Ajout de méthode de paiement Stripe
FR22: Epic 4  - Facturation 5$/heure au prorata                   ⛔ REMPLACÉE par FR40 (Epic 8)
FR23: Epic 4  - Invité jamais facturé                             ⛔ SUPPRIMÉE par FR41 (Epic 8)
FR24: Epic 2  - Sortie vocale de Salon
FR25: Epic 3  - Sortie par fermeture app/navigateur
FR26: Epic 2  - Question de satisfaction
FR27: Epic 3  - Satisfaction pour invité anonyme                  ⛔ SANS OBJET — tous inscrits (FR51)
FR28: Epic 5  - Consultation de l'historique
FR29: Epic 5  - Nouveau Salon avec partenaire précédent
FR30: Epic 3  - Courriel automatique avec lien d'installation
FR31: Epic 3  - Installation et conversion en utilisateur inscrit

FR32: Epic 8  - Speech-to-speech toujours offert en option
FR33: Epic 9  - Quatre paliers payants (Base 3$ / A 7,50$ / B 15$ / C 22,50$), aucun gratuit
FR34: Epic 8  - Choix du mode par l'hôte à la création
FR35: Epic 8  - Choix du mode par le participant à la jonction
FR36: Epic 8  - Persistance du mode pendant le Salon
FR37: Epic 8  - Salon mixte Base / speech-to-speech
FR38: Epic 6  - Deux adaptateurs du port Interprète
FR39: Epic 9  - Insertion d'annonces entre messages
FR40: Epic 8  - Facturation au tarif du mode du participant
FR41: Epic 8  - Moyen de paiement requis au-delà du quota
FR42: Epic 8  - Option « l'hôte paie tout »
FR43: Epic 10 - Plafond de participants configurable (3)
FR44: Epic 6  - Restitution premier arrivé premier servi
FR45: Epic 6  - Coupure de micro par l'hôte
FR46: Epic 6  - Une room par participant, sans audio partagé
FR47: Epic 10 - Un lien à usage unique par invité
FR48: —       - Retirée, fusionnée dans FR40
FR49: Epic 7  - Signal « Vocaliz is busy » et blocage d'entrée
FR50: Epic 9  - Annonces géolocalisées par participant
FR51: Epic 10 - Inscription légère + crédit de bienvenue de 5 USD à vie
FR52: Epic 6  - Messages ≤ 500 caractères, découpage par phrase
FR53: Epic 7  - Condensation par l'interprète en retard
FR54: Epic 7  - Paramètres opérationnels persistés
FR55: Epic 8  - Alerte de solde bas, fin de Salon, fermeture du Salon si hôte
FR56: Epic 8  - Solde prépayé, recharge Stripe hors session, repli par lien
FR57: Epic 10 - Invitation vocale d'un numéro de téléphone (SIP), payée par l'hôte
FR58: Epic 6  - Présentation d'un participant et de sa langue à sa 1ʳᵉ prise de parole
FR59: Epic 6  - Accès à l'historique pour un arrivant tardif (décision de l'hôte)
FR60: Epic 6  - Nettoyage des pauses et hésitations à l'ingestion
FR61: Epic 6  - Métadonnée de pause signifiante dans le journal
FR62: Epic 7  - Ordre déterministe d'émission de la méta-parole
FR63: Epic 8  - Vérification périodique de la couverture du solde
FR64: Epic 10 - Modification d'un identifiant avec ancre de continuité
FR65: Epic 10 - Nom d'utilisateur et mot de passe
FR66: Epic 8  - Octroi manuel d'un second crédit par commande en ligne
FR67: Epic 8  - Journal comptable des crédits offerts (émis/consommé/périmé/abandonné)
FR68: Epic 8  - Journal comptable du solde payé (encaissé/consommé/remboursé/dû)
FR69: Epic 8  - Relance annuelle des comptes inactifs à solde positif

NFR7: Epic 8  - Flux d'événements unique, journaux et métriques dérivés
NFR8: Epic 6  - Journal et curseurs persistés, reprise après panne  ⚠ AMENDE NFR2
NFR9: Epic 6  - Chiffrement au repos de toute donnée personnelle

FR70: Epic 10 - Droit d'accès et d'effacement de la personne concernée
FR71: Epic 8  - Rabais de 5 % sur recharge par navigateur
FR72: Epic 6  - Vidéo muette en direct, optionnelle, jamais enregistrée
FR73: Epic 6  - Sous-titres traduits en direct, web et mobile, langues élargies
              ↳ largement HÉRITÉ de Salon : captions.py, CaptionsPanel, useCaptions
FR74: Epic 6  - Voyant de parole vert/rouge par paire humain-interprète
FR75: Epic 6  - Mode conduite : écran noir, vocal uniquement
              ↳ DÉJÀ LIVRÉ par Salon : mobile/src/components/DrivingMode.tsx
FR76: Epic 6  - Activation manuelle et automatique au-delà de 10 km/h

NFR4: Epic 7  - Instrumentation des métriques PR-VOICE-001
NFR5: Epic 7  - Infrastructure de test de charge (jusqu'à 50)
NFR6: Epic 6  - Port Interprète, aucun fournisseur en dur
```

## Epic List

### Epic 1: Inscription & Identité
Un nouvel utilisateur peut créer un compte Salon en vérifiant son adresse courriel — condition préalable à toute utilisation du produit en tant qu'hôte.
**FRs covered:** FR18
**Note d'implémentation :** Story 1.1 = initialisation des deux projets (`lk app create --template agent-starter-python`, `npx create-expo-app`) — première story technique avant toute fonctionnalité utilisateur.

### Epic 2: Salon de Discussion Vocale
Un hôte inscrit peut créer un Salon à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de Salon.
**FRs covered:** FR1, FR2, FR3, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR24, FR26

### Epic 3: Accès Invité Sans Installation
Un contact sans l'application peut rejoindre un Salon depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.
**FRs covered:** FR4, FR5, FR25, FR27, FR30, FR31

### Epic 4: Essai Gratuit & Facturation
Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.
**FRs covered:** FR19, FR20, FR21, FR22, FR23

### Epic 5: Historique & Reconnexion
Un utilisateur inscrit peut consulter ses Salons passés et démarrer rapidement un nouveau Salon avec un partenaire déjà connu.
**FRs covered:** FR28, FR29

> **Epics 1 à 5 : livrés.** Les Epics 6 à 10 ci-dessous en amendent une partie — voir les marqueurs ⚠ et ⛔ de la carte de couverture.

> ## 🛑 À lire avant d'implémenter quoi que ce soit
>
> Le code de ce dépôt vient du projet **Salon**, un produit mûr dont Vocaliz ne diffère que sur quatre points : la topologie audio, la vidéo, le modèle prépayé et les paliers. Les stories ci-dessous ont pourtant été écrites comme si tout partait de zéro.
>
> **Chaque story porte donc un bandeau d'état.** Il fait autorité sur le texte de la story :
>
> | Marqueur | Signification |
> |---|---|
> | ✅ **DÉJÀ LIVRÉ** | Existe et fonctionne. Se réduit à une **vérification** — ne pas reconstruire |
> | ⚠️ **PARTIELLEMENT HÉRITÉ** | Un socle existe. **Étendre**, jamais réécrire. Le point de départ est nommé |
> | *(sans bandeau)* | À construire |
>
> Audit complet : [story-audit-2026-08-08.md](story-audit-2026-08-08.md) — **8 stories déjà livrées, 12 partiellement héritées, 24 à construire.**

### Epic 6: Socle Conversationnel Multi-Rooms
Une conversation Salon se déroule à travers un orchestrateur central et un interprète dédié par participant : chacun parle sa langue dans sa propre room et reçoit celle des autres, sans audio partagé et donc sans écho possible.
**FRs covered:** FR38, FR44, FR45, FR46, FR52, FR58, FR59, FR60, FR61, FR72, FR73, FR74 · **NFR6, NFR8, NFR9** · **Supprime** FR9 · **Rend FR17 sans objet** · **Étend** FR12, FR15 · **Amende NFR2**
**Note d'implémentation :** la Story 1.1 (starter `agent-starter-python`) ne couvre pas l'orchestrateur, composant déployable nouveau — la **Story 6.1** l'initialise. Le worker d'interprète issu du starter est conservé et hébergera les adaptateurs du port. Construire pour N participants, configurer à 3.

### Epic 7: Régulation de Charge & Observabilité
Le Salon reste utilisable quand la conversation s'emballe : l'interprète condense pour rattraper, le système annonce sa saturation et bloque l'entrée le temps de redescendre, et tous les seuils sont ajustables sans déploiement.
**FRs covered:** FR49, FR53, FR54, FR62 · **NFR4, NFR5**
**Note d'implémentation :** à 3 participants ces mécanismes ne se déclencheront quasiment jamais en production. Les seuils configurables de FR54 sont ce qui permet de les exercer réellement en test.

### Epic 8: Modes d'Expérience & Paliers Tarifaires
Chaque participant choisit son propre mode parmi quatre paliers payants, dispose d'un crédit de bienvenue de 5 USD, est prévenu avant que son solde ne s'épuise, et n'est facturé que pour son propre mode.
**FRs covered:** FR32, FR34, FR35, FR36, FR37, FR40, FR41, FR42, FR51, FR55, FR56, FR63, FR66, FR67, FR68, FR69, FR71 · **NFR7** · **Supprime** FR19, FR23 · **Remplace** FR22

### Epic 9: Régie d'Annonces Géolocalisées
Les participants en Base et en Mode A entendent des annonces pertinentes pour leur région, dans leur langue, glissées entre deux messages et jamais au milieu d'une pensée.
**FRs covered:** FR33, FR39, FR50

### Epic 10: Inscription Légère & Accès Sans Installation
Toute personne invitée rejoint un Salon depuis son navigateur en quelques secondes avec un courriel ou un téléphone, sans installer d'application, dans la limite du plafond de participants.
**FRs covered:** FR43, FR47, FR51, FR57, FR64, FR65, FR70 · **Amende** FR4, FR18 · **Remplace** FR2 · **Étend** FR5 · **Rend FR27 sans objet**
**Note d'implémentation :** FR57 rend obligatoire l'intégration SIP de LiveKit Cloud, jusqu'ici notée « optionnelle » dans l'architecture.

## Epic 1: Inscription & Identité

Un nouvel utilisateur peut créer un compte Salon en vérifiant son adresse courriel — condition préalable à toute utilisation du produit en tant qu'hôte.

### Story 1.1: Initialisation des Projets

As a développeur,
I want les projets agent et mobile initialisés depuis les starters officiels,
So that je peux commencer à construire des fonctionnalités sur une fondation cohérente.

**Acceptance Criteria:**

**Given** aucun projet n'existe encore
**When** j'exécute `lk app create --template agent-starter-python` et `uv add "livekit-agents[xai,silero,turn-detector]"`
**Then** le worker d'agent est scaffoldé avec Dockerfile, config `livekit.toml`, et `.env.example`

**And Given** aucun projet mobile n'existe encore
**When** j'exécute `npx create-expo-app` et configure un Expo Development Build
**Then** le projet mobile React Native est prêt à être développé et testé sur un appareil réel

### Story 1.2: Vérification Courriel par OTP

As a nouvel utilisateur,
I want créer un compte en vérifiant mon adresse courriel,
So that je peux utiliser Salon pour la première fois. (FR18)

**Acceptance Criteria:**

**Given** un nouvel utilisateur ouvre l'application pour la première fois
**When** il entre son adresse courriel
**Then** un code OTP est envoyé via AWS SES et une entrée `users` est préparée

**And Given** l'utilisateur entre le code OTP reçu
**When** le code est valide et non expiré
**Then** le compte est créé, un JWT est émis, et l'utilisateur peut utiliser Salon

**And Given** l'utilisateur entre un code invalide ou expiré
**When** la vérification échoue
**Then** l'agent l'informe vocalement de l'erreur et propose de renvoyer un nouveau code

### Story 1.3: Écran d'Inscription

As a nouvel utilisateur,
I want un écran d'inscription clair et rapide,
So that la friction avant ma premier Salon soit minimale. (UX-DR1, UX-DR6, UX-DR10, UX-DR7)

**Acceptance Criteria:**

**Given** l'écran d'inscription est affiché
**When** il se charge
**Then** il utilise la palette "Salon Parisien" (bourgogne, or, ivoire) et l'icône télégraphique custom plutôt qu'une icône téléphone générique

**And Given** un utilisateur avec un lecteur d'écran actif
**When** il navigue l'écran
**Then** tous les champs et boutons respectent le contraste WCAG AA et les cibles tactiles 44×44px minimum

## Epic 2: Salon de Discussion Vocale

Un hôte inscrit peut créer un Salon à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de Salon.

### Story 2.1: Création de Salon avec Document/URL

As a hôte inscrit,
I want créer un Salon à partir d'un document téléversé ou d'une URL de nouvelle,
So that je peux démarrer une discussion sur ce contenu. (FR1)

**Acceptance Criteria:**

**Given** un hôte inscrit et authentifié
**When** il téléverse un document ou fournit une URL
**Then** un Salon est créé avec ce contenu comme source, et une salle LiveKit est provisionnée

### Story 2.2: Invitation Vocale d'un Ami ou Contact

As a hôte,
I want inviter un ami Salon ou un contact téléphone par simple commande vocale,
So that je n'ai jamais à manipuler de lien ou de menu. (FR2)

**Acceptance Criteria:**

**Given** un Salon actif et un hôte qui dit "invite [nom]"
**When** le nom correspond à un ami Salon déjà enregistré
**Then** une notification in-app est envoyée à cet ami

**And Given** le nom correspond à un contact non-inscrit
**When** l'hôte prononce l'invitation
**Then** un courriel est envoyé à ce contact avec un lien de Salon

**And Given** l'agent ne comprend pas le nom mentionné
**When** la résolution échoue
**Then** l'agent redemande poliment à voix haute

### Story 2.3: Ajout de Source en Cours de Salon

As a hôte,
I want ajouter un document ou une URL supplémentaire pendant un Salon actif,
So that la discussion peut évoluer sans devoir en créer une nouvelle. (FR3)

**Acceptance Criteria:**

**Given** un Salon actif dont l'hôte est participant
**When** l'hôte ajoute un nouveau document ou une URL
**Then** la nouvelle source est associée au Salon et disponible pour l'agent

### Story 2.4: Lecture à Voix Haute et Facilitation Sans Lecture Préalable

As a participant,
I want que l'agent lise et anime le contenu à voix haute,
So that je peux discuter d'un document sans l'avoir lu au préalable. (FR6, FR7)

**Acceptance Criteria:**

**Given** un Salon démarré avec une source de contenu
**When** les participants rejoignent
**Then** l'agent lit le contenu à voix haute et pose des questions pour engager la discussion

**And Given** un participant n'a pas consulté le document au préalable
**When** il participe à la discussion
**Then** il peut suivre et contribuer normalement grâce à la lecture de l'agent

### Story 2.5: Contraste avec d'Autres Sources

As a participant,
I want que l'agent introduise des informations contrastantes d'autres sources,
So that la discussion gagne en profondeur. (FR8)

**Acceptance Criteria:**

**Given** une discussion en cours sur un sujet donné
**When** l'agent identifie une occasion de contraste pertinent
**Then** il introduit l'information contrastante à voix haute, en citant sa source

### Story 2.6: Conversation Naturelle Sans Mot-Clé de Réveil

As a participant,
I want parler naturellement sans mot-clé de réveil ni mécanisme formel de demande de parole,
So that la conversation reste fluide comme entre humains. (FR9, FR10)

**Acceptance Criteria:**

**Given** un Salon actif
**When** un participant commence à parler
**Then** l'agent le comprend sans qu'un mot-clé de réveil soit prononcé

**And Given** deux participants parlent en alternance
**When** une pause naturelle survient
**Then** l'agent ou l'autre participant peut prendre la parole sans mécanisme explicite de demande

### Story 2.7: Ajustement Vocal de la Fréquence d'Intervention

As a participant,
I want ajuster à voix haute la fréquence d'intervention de l'agent,
So that je garde le contrôle du rythme de la conversation. (FR11)

**Acceptance Criteria:**

**Given** un Salon avec des participants de même langue
**When** aucun ajustement n'est demandé
**Then** l'agent intervient au maximum une fois par minute, de façon succincte

**And Given** un participant dit "parle moins souvent" ou "interviens plus"
**When** la demande est reçue
**Then** l'agent ajuste sa fréquence d'intervention en conséquence pour le reste du Salon

### Story 2.8: Détection de Langue et Expression Multilingue

As a participant,
I want m'exprimer dans ma propre langue sans configuration,
So that la barrière linguistique ne limite jamais la conversation. (FR12, FR14)

**Acceptance Criteria:**

**Given** un participant rejoint un Salon
**When** il commence à parler
**Then** le système détecte automatiquement sa langue sans sélection manuelle

**And Given** la langue est détectée
**When** le participant continue de parler
**Then** il peut s'exprimer entièrement dans cette langue tout au long du Salon

### Story 2.9: Affichage Visuel dans la Langue Détectée

As a utilisateur,
I want que les écrans de l'application s'affichent dans ma langue vocale détectée,
So that je n'aie jamais besoin de configurer manuellement une langue d'interface. (FR13)

**Acceptance Criteria:**

**Given** la langue vocale d'un utilisateur est détectée
**When** un écran de l'application s'affiche
**Then** le texte visuel est présenté dans cette langue

### Story 2.10: Traduction Simultanée en Direct Sans Écho

As a participant,
I want entendre une traduction en direct dans ma langue pendant que l'autre continue de parler,
So that la conversation reste fluide malgré la barrière linguistique. (FR15, FR16, FR17)

**Acceptance Criteria:**

**Given** deux participants parlant des langues différentes
**When** l'un d'eux parle
**Then** son discours est traduit et lu à voix haute au destinataire dans sa propre langue

**And Given** la traduction est en cours de lecture pour un destinataire
**When** l'interlocuteur d'origine continue de parler
**Then** la traduction ne l'interrompt pas et le microphone du destinataire est temporairement coupé pour éviter tout écho sur le flux partagé

### Story 2.11: Sortie Vocale de Salon

As a participant,
I want quitter un Salon en disant "Je quitte le Salon" dans ma propre langue,
So that je peux terminer proprement sans manipuler l'écran. (FR24)

**Acceptance Criteria:**

**Given** un Salon actif
**When** un participant prononce la commande de sortie dans sa langue
**Then** le Salon se termine pour ce participant

### Story 2.12: Question de Satisfaction de Fin de Salon

As a participant,
I want qu'on me demande vocalement si la conversation a été agréable,
So that mon ressenti soit capturé sans effort. (FR26)

**Acceptance Criteria:**

**Given** un participant vient de prononcer la commande de sortie
**When** le Salon se termine pour lui
**Then** l'agent lui pose immédiatement, à voix haute, la question "Est-ce que votre conversation dans Salon a été une belle expérience ?"

## Epic 3: Accès Invité Sans Installation

Un contact sans l'application peut rejoindre un Salon depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.

> **⚠ Superseded par l'Epic 10 (2026-08-08).** Les stories 3.1 à 3.5 ci-dessous sont livrées et conservées comme trace de l'existant, mais la notion d'« invité anonyme » n'existe plus : FR51 impose désormais une inscription légère (courriel ou téléphone) à toute personne. La promesse retenue est « sans installation », pas « sans compte ». En cas de contradiction, l'Epic 10 fait autorité.

### Story 3.1: Jonction Web Anonyme via Lien à Usage Unique

As a contact invité sans l'application,
I want rejoindre un Salon directement depuis mon navigateur,
So that je peux participer sans installer quoi que ce soit. (FR4, FR5, UX-DR5, UX-DR8)

**Acceptance Criteria:**

**Given** un hôte invite un contact sans l'application Salon
**When** le contact reçoit le courriel et clique le lien
**Then** il rejoint le Salon depuis son navigateur, sans installer d'application

**And Given** un lien de Salon a déjà été utilisé une fois
**When** quelqu'un tente de le réutiliser
**Then** l'accès est refusé

**And Given** la page de jonction s'affiche
**When** elle se charge sur mobile ou desktop
**Then** elle affiche le badge "Sans Installation" et s'adapte correctement aux deux formats

### Story 3.2: Sortie de Salon par Fermeture

As a invité anonyme,
I want pouvoir simplement fermer mon navigateur pour quitter,
So that je n'aie pas besoin de connaître une commande vocale spécifique. (FR25)

**Acceptance Criteria:**

**Given** un invité anonyme dans un Salon actif
**When** il ferme l'application ou l'onglet du navigateur
**Then** il quitte le Salon proprement

### Story 3.3: Question de Satisfaction pour Invité Anonyme

As a invité anonyme,
I want répondre à la question de satisfaction sans avoir de compte,
So that mon ressenti compte même sans inscription. (FR27)

**Acceptance Criteria:**

**Given** un invité anonyme quitte un Salon
**When** l'agent pose la question de satisfaction
**Then** l'invité peut y répondre vocalement sans que la réponse soit liée à un profil persistant

### Story 3.4: Courriel de Suivi avec Lien d'Installation

As a invité sans compte,
I want recevoir un courriel avec un lien d'installation après mon Salon,
So that je puisse facilement installer l'application si l'expérience m'a plu. (FR30)

**Acceptance Criteria:**

**Given** un invité sans compte termine sa premier Salon
**When** le Salon se termine
**Then** il reçoit automatiquement un courriel avec un lien d'installation de l'application

### Story 3.5: Conversion en Utilisateur Inscrit

As a invité sans compte ayant reçu le lien d'installation,
I want installer l'application et continuer à utiliser Salon en tant qu'utilisateur inscrit,
So that je conserve mon historique pour mes futurs Salons. (FR31)

**Acceptance Criteria:**

**Given** un invité sans compte a reçu le courriel d'installation
**When** il installe l'application et complète la vérification courriel
**Then** il devient un utilisateur inscrit à part entière

## Epic 4: Essai Gratuit & Facturation

Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.

### Story 4.1: Heure d'Essai Gratuite à Vie par Hôte

As a hôte,
I want bénéficier d'une heure d'essai gratuite cumulée sur toutes mes Salons,
So that je peux essayer Salon avant de payer. (FR19)

**Acceptance Criteria:**

**Given** un hôte utilise Salon pour la première fois
**When** il démarre des Salons
**Then** son temps cumulé en tant qu'hôte est suivi contre un plafond d'une heure à vie

**And Given** un invité participe à un Salon
**When** le temps est comptabilisé
**Then** son temps à lui n'est jamais compté contre l'essai gratuit de qui que ce soit (FR23)

### Story 4.2: Métrage Précis du Temps de Conversation

As a système,
I want comptabiliser le temps de conversation à la minute et à la seconde près,
So that l'essai gratuit et la facturation soient exacts. (FR20)

**Acceptance Criteria:**

**Given** un Salon actif avec un hôte
**When** la conversation se déroule
**Then** le worker d'agent envoie un heartbeat de métrage toutes les 30 secondes à l'API

**And Given** une déconnexion brutale survient
**When** le Salon se termine de façon inattendue
**Then** le métrage déjà transmis via heartbeat n'est pas perdu

### Story 4.3: Ajout de Méthode de Paiement Stripe

As a hôte dont l'heure gratuite est épuisée,
I want ajouter une méthode de paiement,
So that je peux continuer à utiliser Salon en tant qu'hôte. (FR21)

**Acceptance Criteria:**

**Given** un hôte a épuisé son heure d'essai gratuite
**When** il tente de démarrer un nouveau Salon en tant qu'hôte
**Then** il doit ajouter une méthode de paiement via Stripe avant de continuer

### Story 4.4: Facturation à l'Heure Après l'Essai Gratuit

As a hôte avec une méthode de paiement enregistrée,
I want être facturé au prorata de mon temps d'utilisation au-delà de l'essai gratuit,
So that je paie seulement ce que j'utilise. (FR22, FR23)

**Acceptance Criteria:**

**Given** un hôte a dépassé son heure gratuite et a une méthode de paiement
**When** il utilise Salon en tant qu'hôte
**Then** il est facturé 5 USD par heure, au prorata de la seconde

**And Given** un invité participe à un Salon facturé
**When** la facturation est calculée
**Then** l'invité n'est jamais facturé, peu importe la durée

## Epic 5: Historique & Reconnexion

Un utilisateur inscrit peut consulter ses Salons passés et démarrer rapidement un nouveau Salon avec un partenaire déjà connu.

### Story 5.1: Consultation de l'Historique de Salons

As a utilisateur inscrit,
I want consulter mes Salons passés et mes partenaires de discussion,
So that je peux me souvenir de mes conversations précédentes. (FR28, UX-DR13)

**Acceptance Criteria:**

**Given** un utilisateur inscrit avec au moins un Salon passé
**When** il consulte son historique
**Then** il voit une liste simple de ses Salons passés et partenaires, sans fil de messages détaillé

### Story 5.2: Nouveau Salon avec un Partenaire Précédent

As a utilisateur inscrit,
I want démarrer rapidement un nouveau Salon avec un partenaire déjà connu,
So that je n'aie pas à répéter le processus d'invitation complet. (FR29)

**Acceptance Criteria:**

**Given** un utilisateur consulte son historique
**When** il sélectionne un partenaire précédent pour un nouveau Salon
**Then** un nouveau Salon démarre avec ce partenaire déjà identifié

## Epic 6: Socle Conversationnel Multi-Rooms

Une conversation Salon se déroule à travers un orchestrateur central et un interprète dédié par participant : chacun parle sa langue dans sa propre room et reçoit celle des autres, sans audio partagé et donc sans écho possible.

### Story 6.1: Initialisation du Composant Orchestrateur

As a développeur,
I want un projet orchestrateur déployable dès la première story,
So that tout ce qui suit ait un endroit où vivre. (NFR6, remplace la Story 1.1 pour ce composant)

**Acceptance Criteria:**

**Given** la topologie multi-rooms
**When** les composants déployables sont recensés
**Then** l'orchestrateur en est un **nouveau, distinct du worker d'interprète** — le starter `agent-starter-python` de la Story 1.1 ne le couvre pas et ne peut pas le couvrir

**Given** aucun projet orchestrateur n'existe
**When** je l'initialise
**Then** j'obtiens un service qui démarre, expose un point de santé, lit sa configuration depuis l'environnement, et journalise son démarrage

**And Given** l'hébergement
**When** il est défini
**Then** l'orchestrateur vit dans **AWS, sur ECS Fargate** — au même titre que le worker d'interprète, dans le même compte et le même réseau, sans nouvelle plateforme à administrer

**And Given** que le journal d'un Salon et les curseurs de ses interprètes sont **persistés** (NFR8)
**When** un Salon est actif
**Then** son état survit à l'instance qui l'héberge : une autre instance peut le **reprendre en relisant le stockage**

**And Given** un arrêt brutal — panne, éviction, échec de santé
**When** il survient
**Then** les Salons hébergés sont **repris** : chaque interprète retrouve son curseur et reprend la restitution là où il l'avait laissée, sans perte de contenu

**And Given** un déploiement ou un arrêt de tâche planifié
**When** il survient
**Then** l'instance **draine** — elle cesse d'accepter de nouveaux Salons et attend la fin de ceux qu'elle héberge — par confort d'expérience, non par nécessité technique

**And Given** l'affinité entre un Salon et son instance
**When** le service est mis à l'échelle
**Then** elle reste souhaitable pour la performance — éviter de relire l'état à chaque message — mais n'est plus une condition de survie

**And Given** le projet initialisé
**When** il est construit
**Then** il produit une image conteneur avec son `Dockerfile`, et une **définition de tâche ECS Fargate écrite à la main** en JSON, conformément au choix d'architecture de ne pas recourir à un outil d'infrastructure-as-code pour le MVP

**And Given** les secrets nécessaires
**When** le service démarre
**Then** il les lit depuis AWS Secrets Manager et **échoue au démarrage avec un message explicite** si l'un manque — jamais silencieusement, jamais à la première requête

**And Given** le pipeline GitHub Actions existant
**When** l'orchestrateur est ajouté
**Then** il est construit et déployé par le même pipeline que les composants existants, sans chaîne parallèle

**And Given** un développeur sur son poste
**When** il lance l'orchestrateur localement
**Then** il démarre sans dépendance à AWS ni à un fournisseur payant, de sorte que les stories suivantes soient développables hors ligne

**And Given** le worker d'interprète existant, issu de `agent-starter-python`
**When** l'orchestrateur est introduit
**Then** il est **conservé** et deviendra l'hôte des adaptateurs du port Interprète (Story 6.2) — l'orchestrateur ne le remplace pas, il s'ajoute à côté

**And Given** l'orchestrateur initialisé
**When** il est livré
**Then** il ne contient **aucune logique métier** : ni journal, ni curseurs, ni facturation — seulement de quoi démarrer, se configurer, se déployer et être observé

### Story 6.2: Port Interprète et Adaptateur Speech-to-Speech

As a développeur,
I want un port Interprète accompagné d'un premier adaptateur speech-to-speech,
So that l'orchestrateur ne dépende jamais d'un fournisseur en particulier. (FR38, NFR6)

**Acceptance Criteria:**

**Given** aucun port n'existe encore
**When** je définis l'interface Interprète (`ingest`, `render`, `insert_annonce`, `condense`)
**Then** l'orchestrateur ne référence que cette interface, jamais un SDK fournisseur

**And Given** le port est défini
**When** j'implémente `InterpreteS2S` sur le modèle temps réel audio↔audio
**Then** un humain seul dans sa room converse avec son interprète en voix naturelle, sans passage par du texte à l'intérieur de la room

**And Given** un appel fournisseur échoue
**When** l'adaptateur ne répond pas
**Then** l'orchestrateur reçoit une erreur typée et le participant en est informé vocalement (NFR3)

### Story 6.3: Orchestrateur de Salon, Journal et Curseurs

> ⚠️ **PARTIELLEMENT HÉRITÉ — étendre, ne pas réécrire.**
> **Le journal existe :** `models/utterance.py` — `utterances` (tour, langue, `sequence` monotone unique par Salon) et `utterance_translations` (couple tour-langue, mis en cache). `services/utterance_service.py`, endpoints `POST` et `GET /{salon_id}/utterances`.
> **Ce qui manque :** les **curseurs par interprète**, et le passage d'un journal *par Salon en base* à un journal *tenu par un orchestrateur par Salon*.

As a participant,
I want que ma parole soit transmise aux autres par un orchestrateur central,
So that nous partagions tous la même conversation malgré nos langues différentes. (FR46)

**Acceptance Criteria:**

**Given** un Salon actif
**When** un interprète produit un message
**Then** il est ajouté au journal de l'orchestrateur **dans la langue où il a été prononcé**, avec cette langue, horodaté à l'arrivée, et n'est jamais écrasé — l'émetteur fait l'original

**And Given** le journal
**When** il est consulté
**Then** il constitue l'unique structure de messages du Salon — il n'existe pas de file séparée, un message étant restitué N fois à des rythmes différents et ne pouvant donc jamais être « consommé »

**And Given** chaque interprète
**When** il restitue
**Then** il avance son propre curseur dans le journal, indépendamment des autres, et restitue dans la langue de son participant

**And Given** un tour dont la langue d'origine est **déjà celle du participant qui l'écoute**
**When** il est restitué
**Then** **aucune traduction n'a lieu** : l'original est restitué tel quel, et aucune ligne de traduction n'est créée

**And Given** un Salon dont tous les participants partagent la même langue
**When** il se déroule
**Then** **le sous-système de traduction reste entièrement inactif** — le coût et la latence de traduction sont proportionnels à la diversité linguistique du Salon, jamais au volume de la conversation

**And Given** un tour à restituer dans une langue autre que celle où il a été prononcé
**When** il est traduit
**Then** la traduction part **directement de l'original**, jamais d'une autre traduction — trois interlocuteurs en trois langues produisent trois originaux, et chaque restitution est à **un seul saut** de celui qu'elle traduit

**And Given** une traduction déjà produite pour un couple (tour, langue)
**When** un autre participant demande la même langue
**Then** elle est **réutilisée** plutôt que refaite — plusieurs participants lisant ou écoutant la même langue partagent une seule traduction

**And Given** un interprète et son curseur
**When** son retard est évalué
**Then** il vaut la distance entre la tête du journal et son curseur, exprimée en secondes de contenu

**And Given** le journal et les curseurs
**When** ils sont écrits
**Then** ils le sont **durablement** (NFR8) : le journal survit à la fermeture du Salon comme à l'arrêt de l'instance, et chaque curseur est persisté avec lui pour permettre à un interprète de reprendre exactement là où il s'était arrêté

**And Given** une reprise après panne
**When** une instance reprend un Salon
**Then** elle relit le journal et les curseurs depuis le stockage, et la restitution repart sans perte ni doublon

### Story 6.4: Une Room LiveKit par Participant

As a participant,
I want ma propre room avec mon interprète dédié,
So that je n'entende jamais d'écho ni d'audio superposé. (FR46)

**Acceptance Criteria:**

**Given** un participant rejoint un Salon
**When** son Salon démarre
**Then** une room LiveKit lui est provisionnée, contenant uniquement lui et son interprète

**And Given** trois participants dans un même Salon
**When** ils parlent tous
**Then** aucun flux audio n'est partagé entre les rooms — l'écho est impossible par construction (rend FR17 sans objet)

**And Given** un participant quitte
**When** sa room se ferme
**Then** les autres rooms restent actives et la conversation continue sans interruption

### Story 6.5: Découpage des Interventions à 500 Caractères

As a participant,
I want que mes longues interventions soient découpées proprement,
So that les autres puissent s'intercaler sans que je monopolise la conversation. (FR52)

**Acceptance Criteria:**

**Given** une intervention dépassant `taille_max_message`
**When** l'interprète la transmet
**Then** elle est découpée en messages consécutifs de 500 caractères maximum chacun

**And Given** un découpage est nécessaire
**When** le point de coupe est calculé
**Then** il tombe sur une frontière de phrase, jamais au milieu d'un mot

**And Given** une intervention découpée est en cours de transmission
**When** un contenu tiers (message d'un autre participant ou annonce) est prêt
**Then** il n'est pas inséré entre les morceaux

### Story 6.6: Restitution Premier Arrivé Premier Servi

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `utterances.sequence` est un entier monotone assigné à l'insertion, unique par Salon (`uq_utterances_salon_sequence`). C'est **exactement** l'ordre d'arrivée que FR44 demande. Salon n'a d'ailleurs jamais eu de mécanisme d'attribution de parole à supprimer. Cette story se réduit à **vérifier** que l'ordre survit à la topologie multi-rooms.

As a participant,
I want parler quand je veux sans demander la parole,
So that la conversation reste libre et naturelle. (FR44)

**Acceptance Criteria:**

**Given** plusieurs participants parlent
**When** leurs messages sont ajoutés au journal
**Then** ils sont restitués strictement dans l'ordre du journal, qui est l'ordre d'arrivée — aucune structure d'ordonnancement supplémentaire n'est nécessaire

**And Given** un participant souhaite parler
**When** il commence
**Then** aucun tour, aucune demande de parole et aucune attribution par l'agent n'est requis (supprime FR9)

**And Given** deux messages arrivent au même instant
**When** l'ordre doit être départagé
**Then** l'horodatage d'arrivée à l'orchestrateur fait foi, de façon déterministe et reproductible

### Story 6.7: Adaptateur Base en Transcription et Synthèse

As a utilisateur du mode Base,
I want participer pleinement avec une voix synthétique,
So that je puisse utiliser Salon au tarif le plus bas. (FR38, FR37)

**Acceptance Criteria:**

**Given** le port Interprète existe
**When** j'implémente `InterpreteBase` (STT + LLM + TTS)
**Then** il satisfait exactement le même contrat que `InterpreteS2S`, sans aucune modification de l'orchestrateur

**And Given** un Salon où un participant est en Base et un autre en speech-to-speech
**When** ils conversent
**Then** les deux participent normalement, et l'expérience du mode Base n'est ni bloquée ni dégradée

**And Given** un participant en mode Base
**When** il reçoit une restitution
**Then** elle est lue en voix synthétique dans sa langue détectée

**And Given** les langues supportées par chaque adaptateur
**When** l'ensemble offert par le produit est déterminé
**Then** il vaut leur **intersection**, jamais leur union — le speech-to-speech étant le plus restrictif, c'est lui qui la définit

**And Given** un participant qui change de palier en cours de Salon ou d'un Salon à l'autre
**When** sa langue est restituée
**Then** elle reste disponible à l'identique : **changer de palier ne change jamais les langues offertes**

**And Given** une langue supportée par le seul adaptateur Base
**When** son ajout est envisagé
**Then** elle est **refusée** — elle disparaîtrait à la montée en gamme, altérant l'expérience du client au moment précis où il paie davantage

### Story 6.8: Coupure de Micro par l'Hôte

As a hôte,
I want pouvoir couper le micro d'un participant,
So that je puisse gérer une situation problématique sans fermer le Salon. (FR45)

**Acceptance Criteria:**

**Given** un hôte dans un Salon actif
**When** il coupe le micro d'un participant
**Then** l'ingestion de ce participant s'arrête et son interprète l'en informe vocalement

**And Given** un micro coupé
**When** les autres participants parlent
**Then** le participant coupé continue de recevoir normalement la restitution

**And Given** le micro est coupé puis rétabli
**When** le participant reparle
**Then** son message rejoint le journal par ordre d'arrivée, sans aucune priorité

### Story 6.9: Présentation des Participants et de Leur Langue

> ⚠️ **PARTIELLEMENT HÉRITÉ.** La détection de langue existe et est déjà enregistrée : `salon_events.first_spoken_language` — *« first heard »*, écrit une seule fois et jamais révisé — et `users.detected_language`. `livekit_service.guest_display_name()` produit déjà un libellé affichable, dérivé de l'invitation et **jamais du courriel**, pour ne pas exposer l'adresse d'un invité aux autres.
> **Ce qui manque :** l'**annonce vocale** elle-même, déclenchée à la première prise de parole.

As a participant,
I want savoir qui parle quelle langue dès que chacun s'exprime,
So that je comprenne immédiatement que je suis traduit et à qui je m'adresse. (FR58)

**Acceptance Criteria:**

**Given** un participant prend la parole pour la première fois dans le Salon
**When** sa langue est détectée
**Then** l'interprète de chaque autre participant le présente dans la langue de son propre humain, en nommant sa langue

**And Given** cette présentation
**When** elle est restituée
**Then** elle précède immédiatement la restitution de son premier message — on sait qui parle avant d'entendre ce qu'il dit

**And Given** un participant a déjà été présenté
**When** il reprend la parole plus tard
**Then** aucune présentation supplémentaire n'a lieu — la présentation est unique par participant et par Salon

**And Given** un participant entre dans un Salon où d'autres se sont déjà exprimés
**When** sa room est prête
**Then** son interprète lui annonce, dans sa langue, les participants déjà présentés et leur langue

**And Given** un ou plusieurs participants ne se sont pas encore exprimés
**When** l'annonce initiale est faite
**Then** l'interprète ne les mentionne pas et n'invente jamais une langue non détectée — ils seront présentés à leur première prise de parole

**And Given** le nom du participant est connu (utilisateur inscrit, ou nom prononcé par l'hôte à l'invitation)
**When** la présentation est faite
**Then** elle utilise ce nom ; à défaut, elle emploie une désignation neutre plutôt qu'un numéro de téléphone

**And Given** un participant téléphonique (FR57)
**When** il prend la parole pour la première fois
**Then** il est présenté aux autres exactement comme n'importe quel participant, et reçoit lui aussi l'annonce des participants déjà présentés

**And Given** tous les participants partagent la même langue
**When** les présentations ont lieu
**Then** l'interprète le signale simplement, sans énumération inutile

### Story 6.10: Accès à l'Historique pour un Arrivant Tardif

> ⚠️ **PARTIELLEMENT HÉRITÉ.** `GET /{salon_id}/utterances` sert déjà le transcript complet d'un Salon, traductions comprises.
> **Ce qui manque :** la **décision d'accès de l'hôte** au moment de l'invitation tardive, et la **condensation** quand le volume l'exige.

As a participant rejoignant une conversation en cours,
I want savoir ce qui s'est dit avant mon arrivée,
So that je puisse participer sans faire répéter tout le monde. (FR59)

**Acceptance Criteria:**

**Given** un Salon actif
**When** des messages sont restitués
**Then** le journal conserve la conversation complète — rien n'en est retiré, ce qui rend le condensé possible sans structure supplémentaire

**And Given** le journal
**When** sa conservation est définie
**Then** il est **persisté** (NFR8), pour la reprise après panne et la preuve de diffusion des annonces — la promesse de non-conservation de NFR2 ne s'applique plus

**And Given** un journal atteignant `retention_journal` (1 an depuis la **création du Salon**)
**When** l'échéance survient
**Then** le journal **et ses curseurs** sont effacés automatiquement, sans intervention

**And Given** un Salon de longue durée
**When** l'échéance est calculée
**Then** elle court depuis la **création** du Salon, jamais depuis sa fermeture ni depuis le dernier message — un seul instant de référence, indiscutable

**And Given** l'effacement d'un journal
**When** il est exécuté
**Then** les **écritures comptables** de FR67 et FR68 et le **flux d'événements** de NFR7 ne sont **pas** affectés : ils ne contiennent aucun contenu de conversation et relèvent d'obligations distinctes

**And Given** un hôte invite un participant alors que la conversation est déjà en cours
**When** il prononce l'invitation
**Then** il précise s'il accorde ou non l'accès à l'historique, dans la même commande vocale (« invite Marie, avec l'historique » / « sans l'historique »)

**And Given** l'hôte n'a rien précisé
**When** l'invitation est traitée
**Then** `historique_arrivant_par_defaut` s'applique — **oui** initialement : l'arrivant y a accès, et l'hôte doit le refuser explicitement pour le lui retirer

**And Given** l'hôte accorde l'accès
**When** la room de l'arrivant est prête et les présentations lui ont été faites
**Then** son curseur est positionné **au début du journal** — aucun mécanisme spécifique n'est requis, la restitution suit ensuite les règles ordinaires

**And Given** l'hôte refuse l'accès
**When** l'arrivant entre
**Then** son curseur est positionné **directement à la tête du journal** : il reçoit les présentations et rejoint la conversation en direct, sans aucun accès à ce qui s'est dit avant lui

**And Given** un curseur placé au début du journal et un retard résultant **inférieur** à `seuil_condensation`
**When** l'interprète restitue
**Then** l'historique est restitué **intégralement**, message par message — un Salon jeune n'a rien à résumer

**And Given** un curseur placé au début du journal et un retard résultant **supérieur** à `seuil_condensation`
**When** l'interprète restitue
**Then** l'intervalle est condensé selon FR53, borné par `taille_max_condense` — accorder l'accès et condenser sont deux décisions distinctes, la seconde découlant du seul volume

**And Given** un participant rejoint un Salon où personne n'a encore parlé
**When** sa room est prête
**Then** rien n'est restitué, quelle que soit la décision de l'hôte — le journal est vide

**And Given** un rattrapage d'historique est en cours
**When** la conversation se poursuit en direct
**Then** les messages ajoutés pendant ce temps sont rattrapés à leur tour selon la même règle, sans traitement particulier

**And Given** l'hôte accorde l'accès à l'historique à un arrivant
**When** l'accès est effectif
**Then** les participants déjà présents en sont informés vocalement par leur propre interprète — nul ne doit ignorer que ce qu'il a dit avant l'arrivée de cette personne lui est restitué

### Story 6.11: Nettoyage des Disfluences et Métadonnée de Pause

As a participant,
I want que les « euh » des autres disparaissent mais que leurs silences porteurs de sens me parviennent,
So that j'entende leur pensée plutôt que leur respiration, sans perdre ce qu'ils n'ont pas dit. (FR60, FR61)

**Acceptance Criteria:**

**Given** un humain parle avec des pauses mortes, des « euh », des faux départs ou des répétitions involontaires
**When** son interprète produit le message
**Then** ces éléments sont retirés **avant l'ajout au journal**, de sorte que le journal ne contienne que du contenu utile

**And Given** le nettoyage a lieu à l'ingestion et non à la restitution
**When** N participants reçoivent le message
**Then** le nettoyage n'est effectué **qu'une seule fois**, et tous en bénéficient — jamais N fois côté restitution

**And Given** le nettoyage réduit le volume de contenu
**When** les retards sont calculés
**Then** ils sont mesurés sur le contenu nettoyé, ce qui réduit mécaniquement le retard de **toutes** les rooms et retarde condensation et saturation

**And Given** une pause **inférieure ou égale** à `seuil_pause_signifiante` (2 000 ms)
**When** le nettoyage s'applique
**Then** elle est purement et simplement supprimée, comme toute disfluence (FR60)

**And Given** une pause **supérieure** à `seuil_pause_signifiante`
**When** le nettoyage s'applique
**Then** elle n'est pas supprimée mais convertie en métadonnée `[pause=N]` inscrite dans le texte du journal, `N` étant la durée en **millisecondes** — `[pause=4000]` pour une pause de 4 secondes

**And Given** une pause dépassant `pause_max` (5 000 ms)
**When** la métadonnée est inscrite
**Then** `N` est plafonné à `pause_max` — un silence de trente secondes devient `[pause=5000]`, jamais davantage

**And Given** `seuil_pause_signifiante` et `pause_max`
**When** ils sont modifiés
**Then** ils sont persistés et ajustables indépendamment, sans déploiement (FR54)

**And Given** une métadonnée `[pause=N]` dans le journal
**When** un interprète restitue le message
**Then** il applique un silence dans la parole de son participant et ne prononce **jamais** le marqueur lui-même

**And Given** une métadonnée `[pause=N]`
**When** elle est restituée dans une autre langue
**Then** l'interprète l'applique de façon idiomatique — la durée est une indication d'intention, pas une contrainte au centième

**And Given** un humain prononce littéralement une suite de mots ressemblant au marqueur
**When** le message est ingéré
**Then** cette suite est neutralisée et traitée comme du contenu ordinaire — un participant ne peut pas injecter de métadonnée en la prononçant

**And Given** une métadonnée `[pause=N]`
**When** la taille du message est évaluée pour `taille_max_message`
**Then** le marqueur ne compte pas comme du contenu, n'étant pas de la parole

**And Given** une métadonnée `[pause=N]`
**When** le retard d'un interprète est calculé
**Then** les `N` millisecondes comptent, la pause occupant réellement du temps à la restitution

**And Given** un intervalle contenant des métadonnées de pause
**When** l'interprète le condense (FR53)
**Then** les marqueurs sont abandonnés avec le reste — on ne résume pas des silences

**And Given** le canal de métadonnées du journal
**When** de nouveaux marqueurs seront ajoutés plus tard (emphase, ton, ironie)
**Then** ils suivent la même forme `[clé=valeur]` et les mêmes règles : jamais prononcés, jamais injectables, non comptés comme contenu

**And Given** le nettoyage
**When** il s'applique
**Then** il ne supprime, ne reformule ni ne résume aucun mot porteur de contenu — c'est du nettoyage, pas de la condensation (FR53)

**And Given** l'adaptateur `InterpreteBase` (STT + LLM + TTS)
**When** il ingère
**Then** le nettoyage s'applique sur le texte transcrit

**And Given** l'adaptateur `InterpreteS2S` (audio ↔ audio)
**When** il ingère
**Then** le nettoyage s'applique également, le modèle ne devant jamais reproduire les hésitations de l'humain dans le message émis

**And Given** l'interprète lui-même produit de la parole vers son humain
**When** il restitue
**Then** il ne produit ni hésitation ni pause morte — la règle vaut dans les deux sens

### Story 6.12: Chiffrement au Repos

> ✅ **LARGEMENT DÉJÀ LIVRÉ.** Le cluster Aurora est chiffré par KMS, ce qui couvre **le stockage, les instantanés et les sauvegardes** — c'est documenté dans `models/salon_event.py`, avec la raison de ne pas chiffrer au niveau colonne : *« column encryption would have forced a deterministic scheme on the key columns and ruled out every query but equality »*.
>
> **Ce qui reste :** vérifier qu'**aucun contenu de conversation n'atteint CloudWatch**. C'est le seul point non acquis, et le plus facile à violer par accident.

As a participant,
I want que mes conversations conservées soient chiffrées,
So that leur persistance ne devienne pas leur exposition. (NFR9)

**Acceptance Criteria:**

**Given** le journal d'un Salon et les curseurs de ses interprètes
**When** ils sont écrits
**Then** ils le sont **chiffrés au repos**, avec des clés gérées par **AWS KMS**

**And Given** les autres données personnelles persistées — soldes, écritures comptables, identifiants, consentements de géolocalisation, registre des identifiants brûlés
**When** elles sont écrites
**Then** elles sont chiffrées au repos au même titre : le chiffrement porte sur **tout stockage de donnée personnelle**, jamais sur le seul journal

**And Given** les sauvegardes et les instantanés
**When** ils sont produits
**Then** ils sont chiffrés au même titre — une sauvegarde en clair annule le chiffrement de la base qu'elle copie

**And Given** les clés de chiffrement
**When** leur cycle de vie est défini
**Then** elles font l'objet d'une **rotation**, et leur usage est journalisé par KMS

**And Given** les journaux applicatifs — CloudWatch et sortie standard
**When** l'orchestrateur ou un interprète écrit une trace
**Then** **aucun contenu de conversation n'y figure jamais** : ni message, ni condensé, ni métadonnée de pause, ni fragment de transcription

**And Given** un message de diagnostic portant sur un message du journal
**When** il est écrit
**Then** il ne référence que des **identifiants et des longueurs**, jamais du texte — ce qui est chiffré en base ne doit pas reparaître en clair dans les traces

**And Given** le transport
**When** les données circulent
**Then** elles le sont déjà chiffrées par TLS et WebRTC — le chiffrement au repos complète cette protection, il ne la remplace pas

### Story 6.16: Mode Conduite — Écran Noir, Vocal Uniquement

As a participant au volant,
I want que l'application n'ait rien à me montrer,
So that je n'aie aucune raison de baisser les yeux. (FR75)

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `mobile/src/components/DrivingMode.tsx`. Son commentaire d'en-tête énonce le principe mieux qu'une spécification ne le ferait : *« The point is not to hide the interface — it is to remove the reason to glance at it. »*
>
> **Ce qui reste :** étendre la suspension aux deux nouveautés — vidéo (FR72) et voyants de parole (FR74) — qui n'existaient pas dans Salon.

**Acceptance Criteria:**

**Given** un participant activant le mode conduite
**When** il s'affiche
**Then** l'écran devient **entièrement noir** et remplace la salle, plutôt que de se superposer à une partie d'elle — la conversation vocale se poursuit inchangée dessous

**And Given** le mode conduite actif
**When** les fonctions visuelles sont évaluées
**Then** **la vidéo (FR72), les sous-titres (FR73) et les voyants de parole (FR74) sont tous suspendus** — il ne reste que la voix

**And Given** la suspension des sous-titres
**When** elle prend effet
**Then** la **langue de sous-titres est vidée** pendant toute la durée du mode : personne ne lit, donc rien n'est traduit, donc **rien n'est facturé** pour des tours que ce participant ne verra jamais. Le choix précédent est restauré à la sortie

**And Given** l'écran du téléphone
**When** le mode est actif
**Then** il est **maintenu éveillé** — un téléphone qui se verrouille au bout de trente secondes obligerait à le réveiller, le déverrouiller et retrouver l'application pour sortir du mode, c'est-à-dire exactement le tâtonnement que le mode veut éviter. Le verrou est relâché dès la sortie

**And Given** un conducteur voulant sortir du mode
**When** il touche l'écran
**Then** **toute la surface est la sortie** : la seule chose qu'on puisse faire au toucher, sans regarder, est de taper la vitre

**And Given** un conducteur voulant quitter le Salon
**When** il cherche à raccrocher
**Then** une cible distincte le permet **en une seule action**, placée en bas où le pouce repose plutôt que là où un contact involontaire atterrit

**And Given** l'affichage résiduel
**When** il est rendu
**Then** il est **volontairement terne** — assez lumineux pour se trouver dans le noir, trop pour attirer l'œil — et la barre d'état passe en clair pour ne pas briller en blanc dans un habitacle sombre

### Story 6.17: Activation Automatique du Mode Conduite

As a participant qui prend la route,
I want que le mode conduite s'active sans que j'y pense,
So that je n'aie pas à manipuler mon téléphone au moment où je ne dois pas. (FR76)

**Acceptance Criteria:**

**Given** un interrupteur dans l'interface
**When** le participant le bascule
**Then** le mode conduite s'active ou se désactive immédiatement, en toute circonstance — **le contrôle manuel existe toujours**

**And Given** une position GPS se déplaçant à plus de `vitesse_activation_conduite` (10 km/h)
**When** le seuil est franchi
**Then** le mode conduite **s'active de lui-même**

**And Given** un participant qui **sort manuellement** du mode alors qu'il se déplace encore
**When** sa sortie est enregistrée
**Then** l'activation automatique est **suspendue pour le reste du Salon**. Sans cette règle, un passager de train ou d'autobus serait renvoyé à l'écran noir à chaque tentative de sortie — enfermé dans une fonction de sécurité qui ne le concerne pas

**And Given** un arrêt momentané — feu rouge, embouteillage, gare
**When** la vitesse retombe
**Then** le mode **reste actif** : la désactivation automatique exige de rester sous `vitesse_sortie_conduite` (5 km/h) pendant `delai_sortie_conduite` (120 s). Deux seuils distincts, sinon le mode clignote à chaque intersection

**And Given** la vitesse
**When** elle est déterminée
**Then** elle est **calculée sur l'appareil**, à partir de la position, et **jamais transmise ni conservée**. Rien de ce mécanisme n'atteint le serveur — c'est un réglage d'affichage local, pas une donnée de télémétrie

**And Given** la distinction avec la géolocalisation publicitaire de FR50
**When** les deux sont comparées
**Then** elles sont **indépendantes** : FR50 recueille une cellule Plus Code de 5,5 km avec consentement explicite, à des fins de ciblage ; FR76 lit une vitesse instantanée qui ne quitte jamais l'appareil. **Refuser l'une n'implique pas de refuser l'autre**, et le consentement de FR50 ne vaut pas autorisation pour FR76

**And Given** l'autorisation de localisation
**When** elle est requise
**Then** elle est demandée **au moment d'activer l'automatisme**, jamais à l'installation, et son refus laisse l'interrupteur manuel pleinement fonctionnel

**And Given** la consommation de batterie
**When** la vitesse est surveillée
**Then** la précision demandée au système est la **plus basse suffisante** pour distinguer 5 de 10 km/h — un suivi haute précision continu viderait la batterie d'un trajet, pour une décision binaire

**And Given** un participant sur navigateur, ou sur un appareil sans position
**When** l'automatisme est évalué
**Then** il est simplement **indisponible**, et l'interrupteur manuel reste le seul chemin — sans message d'erreur ni dégradation annoncée

**And Given** un seuil de 10 km/h
**When** il est appliqué
**Then** il attrape aussi les **coureurs, cyclistes et passagers** — c'est assumé : le mode s'active à tort plutôt que de manquer un conducteur, et la sortie manuelle rattrape le faux positif en une action

### Story 6.15: Voyant de Parole par Paire

As a participant,
I want voir qui est en train de parler,
So that je sache qu'une conversation a lieu, même quand je n'entends personne. (FR74)

**Acceptance Criteria:**

**Given** la topologie multi-rooms, où personne n'entend directement personne
**When** le besoin de ce voyant est évalué
**Then** il comble un signal que la topologie a supprimé : **le silence dans mon oreille ne veut plus dire que personne ne parle** — il veut dire que mon interprète n'a pas encore de quoi me restituer

**And Given** chaque paire humain-interprète du Salon
**When** son état est affiché
**Then** il l'est en **deux couleurs** : **vert** quand la voix est active, **rouge** quand elle ne l'est pas

**And Given** les deux voix d'une même paire
**When** elles sont représentées
**Then** **l'humain et son interprète ont chacun leur voyant** — savoir que Marie parle et savoir que son interprète restitue sont deux informations différentes, et la seconde explique le délai de la première

**And Given** un participant
**When** il consulte l'affichage
**Then** il voit l'état de **toutes les paires du Salon**, pas seulement de la sienne — c'est tout l'objet du voyant

**And Given** LiveKit, qui publie nativement l'état de parole des participants d'une room
**When** cet état doit atteindre les autres participants
**Then** il **transite par l'orchestrateur**, car les humains ne partagent aucune room : c'est le même chemin que les tours de parole, sur le canal de données

**And Given** la détection de parole
**When** elle est produite
**Then** elle s'appuie sur le **VAD Silero déjà présent** dans `livekit-agents[silero]` et sur l'état de parole natif de LiveKit — rien de neuf à construire côté détection

**And Given** un participant en **mode conduite**
**When** l'écran est noir
**Then** **aucun voyant n'est affiché** — il n'y a rien à regarder, c'est tout l'objet du mode. Le voyant sert à qui peut regarder ; en conduite, la conversation est vocale et rien d'autre (FR75)

**And Given** un participant téléphonique (FR57)
**When** son état est affiché
**Then** sa paire a les mêmes voyants que les autres : c'est la seule information visuelle disponible à son sujet, puisqu'il n'a pas de vidéo

**And Given** un participant daltonien
**When** les voyants sont affichés
**Then** la couleur n'est **pas le seul porteur d'information** — la forme ou l'animation distingue les deux états, conformément à l'exigence de contraste et d'accessibilité de UX-DR7

### Story 6.14: Sous-Titres Traduits en Direct

As a participant,
I want lire la conversation traduite en même temps que je l'entends,
So that je puisse suivre même dans une langue que la voix ne sait pas prononcer. (FR73)

> **Largement hérité de Salon.** `agent/src/captions.py`, `mobile/src/components/CaptionsPanel.tsx`, `mobile/src/hooks/useCaptions.ts`, les colonnes `caption_language` et `caption_scale`, et la table `utterance_translations` existent et fonctionnent. Cette story **adapte**, elle ne reconstruit pas.

**Acceptance Criteria:**

**Given** une conversation en cours
**When** un participant active les sous-titres
**Then** il lit chaque tour de parole traduit dans **sa** langue de sous-titres, indépendamment de celle des autres participants

**And Given** l'ensemble des langues de sous-titres
**When** il est comparé à celui des langues parlées
**Then** il est **plus large** : la traduction textuelle supporte des langues que le speech-to-speech ne prononce pas, et on peut donc suivre en lisant ce qu'on ne pourrait pas entendre

**And Given** un participant dont la langue de sous-titres n'est pas parlée par les adaptateurs
**When** il rejoint
**Then** il lit normalement — seule la restitution vocale se rabat sur une langue parlée disponible

**And Given** la traduction d'un tour
**When** elle est produite
**Then** elle part de **l'original tel que prononcé** (`utterances.text`), jamais d'une autre traduction, et est mise en cache dans `utterance_translations` — un tour lu par trois personnes dans la même langue coûte une seule traduction

**And Given** un tour prononcé dans la langue de sous-titres du lecteur
**When** il s'affiche
**Then** **aucune traduction n'a lieu** : l'original s'affiche tel quel. C'est aussi le sens de `caption_language = ""` — « comme prononcé, ne rien traduire », un choix à part entière

**And Given** les sous-titres
**When** ils sont offerts
**Then** ils le sont **sur le web comme sur mobile**, à l'hôte comme à chaque participant — aucune des deux plateformes n'est un citoyen de seconde classe

**And Given** un participant
**When** il règle son affichage
**Then** il choisit sa langue de sous-titres et leur taille (`caption_scale`), réglages qui **suivent son compte** d'un appareil à l'autre

**And Given** la valeur vide de `caption_language`
**When** elle est enregistrée
**Then** elle signifie « comme prononcé, ne rien traduire » — un choix à part entière, distinct de NULL qui signifie « jamais choisi »

**And Given** la topologie multi-rooms
**When** les sous-titres sont diffusés
**Then** ils transitent par le canal de données de la room du participant, sans jamais rejoindre le chemin audio

### Story 6.13: Vidéo Muette en Direct

As a participant,
I want voir mon interlocuteur sans l'entendre,
So that je sache que c'est bien lui, maintenant que je n'entends plus jamais sa vraie voix. (FR72)

**Acceptance Criteria:**

**Given** l'architecture multi-rooms, où chacun n'entend que son interprète
**When** le besoin d'assurance d'identité est évalué
**Then** la vidéo comble un signal que la topologie a supprimé : **la voix ne prouve plus rien**, chaque parole étant restituée par une IA

**And Given** un participant qui active sa vidéo
**When** elle est diffusée
**Then** elle l'est **sans aucun son** — l'audio reste intégralement dans le chemin des interprètes, la vidéo n'ouvre jamais de second canal sonore

**And Given** la vidéo
**When** elle transite
**Then** elle emprunte un **chemin média distinct des rooms d'interprétation**, de sorte que l'absence d'audio partagé entre participants reste intacte et que l'écho demeure impossible

**And Given** la vidéo
**When** sa conservation est définie
**Then** elle n'est **jamais enregistrée ni persistée** — vécue en direct puis perdue. NFR8 ne s'y applique pas : le journal texte suffit à la reprise et à la preuve publicitaire

**And Given** un participant
**When** il rejoint un Salon
**Then** sa vidéo est **désactivée par défaut** ; il l'active s'il le souhaite, et peut la couper à tout moment

**And Given** le **mode conduite** (FR75)
**When** il est actif
**Then** la vidéo est **suspendue dans les deux sens** — ni publiée, ni reçue. L'écran est noir, il n'y a rien à regarder, et une caméra braquée sur un pare-brise n'apporte rien à personne

**And Given** un Salon où certains ont la vidéo et d'autres non
**When** il se déroule
**Then** il fonctionne normalement : la vidéo est une couche indépendante, aucune fonctionnalité n'en dépend

**And Given** un participant téléphonique (FR57)
**When** il rejoint
**Then** il n'a ni vidéo entrante ni sortante, et les autres en sont informés

**And Given** un flux vidéo publié
**When** son débit est configuré
**Then** il est plafonné à `debit_max_video` (200 kbps, ≈ 240p à 15 fps) — **le plafond est explicite, jamais laissé au défaut du SDK**, qui monterait à 720p et multiplierait le coût par sept

**And Given** l'usage visé — reconnaître un visage, non lire une expression
**When** la résolution est choisie
**Then** une vignette suffit : à 240p la vidéo coûte ≈ 2 % du palier Base, contre 15 % en 720p pour aucun gain d'identification

**And Given** une bande passante insuffisante
**When** la connexion se dégrade
**Then** **la vidéo est sacrifiée avant l'audio, toujours** — une conversation sans image reste une conversation, l'inverse n'est rien

**And Given** l'accès à la caméra
**When** il est requis
**Then** il est demandé **au moment de l'activation**, jamais à l'installation ni à la premier Salon : l'interprète condense pour rattraper, le système annonce sa saturation et bloque l'entrée le temps de redescendre, et tous les seuils sont ajustables sans déploiement.

### Story 7.1: Configuration Persistée des Paramètres du Salon

> ⚠️ **PARTIELLEMENT HÉRITÉ.** `src/config.py` centralise déjà les réglages — `livekit_room_max_participants`, `livekit_room_empty_timeout` et le reste.
> **Ce qui manque :** ils vivent en **variables d'environnement**, donc leur modification exige un redéploiement. FR54 demande une **table persistée modifiable à chaud**. La liste des paramètres à y verser inclut ceux qui sont aujourd'hui dans `config.py`.

As a exploitant,
I want ajuster les seuils sans redéployer,
So that je puisse régler le produit en production sans intervention de développement. (FR54)

**Acceptance Criteria:**

**Given** les paramètres opérationnels du Salon
**When** le système démarre
**Then** chacun est lu depuis un stockage persistant, avec les valeurs initiales documentées

**And Given** un paramètre est modifié
**When** la modification est enregistrée
**Then** elle prend effet sans redéploiement ni redémarrage

**And Given** `seuil_condensation` est configuré
**When** il est supérieur ou égal à `seuil_saturation`
**Then** la configuration est refusée avec une erreur explicite — sinon la condensation ne se déclencherait jamais avant l'alarme

**And Given** `seuil_deblocage` est configuré
**When** il est supérieur ou égal à `seuil_saturation`
**Then** la configuration est refusée — sinon le système oscille

### Story 7.2: Condensation par l'Interprète en Retard

As a participant,
I want que mon interprète résume plutôt que de m'ensevelir,
So that je reste dans la conversation même quand elle s'emballe. (FR53)

**Acceptance Criteria:**

**Given** le retard d'un interprète (`tête − curseur_i`) dépasse `seuil_condensation` (120 s)
**When** il restitue
**Then** il produit une version condensée de l'intervalle non encore restitué plutôt qu'une restitution intégrale

**And Given** une condensation a lieu
**When** elle est restituée
**Then** le curseur avance jusqu'à la fin de l'intervalle résumé — plus vite que le temps réel, ce qui réduit le retard

**And Given** une condensation a lieu
**When** elle est restituée
**Then** l'interprète l'annonce explicitement au participant, du type « pendant que tu écoutais, trois personnes ont dit ceci, en substance… »

**And Given** la condensation est active
**When** le retard redescend sous le seuil
**Then** l'interprète revient à la restitution intégrale, message par message

**And Given** la condensation d'un interprète
**When** elle s'applique
**Then** elle ne modifie ni le journal ni les curseurs des autres participants — chacun condense pour son propre compte

**And Given** `InterpreteFake` est utilisé
**When** le seuil est franchi
**Then** le déclenchement, l'avancée du curseur et la réduction du retard sont vérifiables de façon déterministe

### Story 7.3: Signal de Saturation et Blocage d'Entrée

As a participant,
I want savoir quand le système sature,
So that je ne parle pas dans le vide. (FR49)

**Acceptance Criteria:**

**Given** le retard de l'interprète d'une room — `retard_i` — dépasse `seuil_saturation` (300 s)
**When** le seuil est franchi
**Then** cet interprète émet le signal « Vocaliz is busy » à son seul participant, dans sa langue, la marque restant en anglais

**And Given** chaque interprète est indépendant et avance à son propre rythme
**When** une room sature
**Then** les autres participants ne sont **ni avertis ni bloqués** — la saturation est un état de room, jamais un état de Salon

**And Given** le signal est actif dans une room
**When** ce participant produit un nouveau message
**Then** l'ajout de **ses** messages au journal est suspendu et son interprète le lui dit immédiatement, plutôt que de le laisser parler dans le vide

**And Given** une room est bloquée
**When** les autres participants parlent
**Then** leurs messages continuent d'être ajoutés au journal normalement, et le participant bloqué continue de les recevoir

**And Given** une intervention déjà commencée est en cours de découpe
**When** le blocage survient
**Then** ses morceaux restants sont ajoutés malgré le blocage, afin de ne pas trancher une pensée en deux

**And Given** `retard_i` redescend sous `seuil_deblocage` (240 s)
**When** le seuil bas est franchi
**Then** les ajouts de cette room sont rouverts, sans oscillation entre les deux seuils

**And Given** la condensation de FR53 s'applique en continu et par room
**When** la saturation se déclenche malgré elle
**Then** cela signifie que la régulation de cette room est saturée — le signal est une alarme, pas un premier recours

**And Given** plusieurs rooms d'un même Salon
**When** l'une sature et les autres non
**Then** le Salon fonctionne dans un état mixte, chaque room ayant son propre statut de saturation

### Story 7.4: Plafond de Monologue

As a participant,
I want que personne ne monopolise indéfiniment,
So that la conversation reste partagée. (FR52)

**Acceptance Criteria:**

**Given** un participant parle en continu depuis moins de `plafond_monologue` (300 s)
**When** du contenu tiers est prêt
**Then** aucune insertion n'a lieu à l'intérieur de son intervention

**And Given** un participant parle en continu depuis plus de `plafond_monologue`
**When** du contenu tiers est prêt
**Then** l'insertion est autorisée à l'intérieur de son intervention découpée

**And Given** `plafond_monologue` et `seuil_saturation` partagent la même valeur initiale
**When** on modifie l'un des deux
**Then** ils restent persistés et modifiables indépendamment l'un de l'autre

### Story 7.5: Interprète Simulé et Infrastructure de Test de Charge

As a développeur,
I want simuler jusqu'à 50 participants sans coût fournisseur,
So that la décision de lever le plafond repose sur des mesures et non sur un pari. (NFR5, NFR6)

**Acceptance Criteria:**

**Given** le port Interprète existe
**When** j'implémente `InterpreteFake`
**Then** il produit des tours de texte à cadence, longueur et langue paramétrables, de façon déterministe

**And Given** l'infrastructure de charge
**When** je lance un scénario à N participants
**Then** elle mesure le retard de chaque curseur, le retard maximal du Salon, la latence p50/p95, le taux de condensation, le nombre et la durée des blocages

**And Given** un scénario à 50 participants avec `InterpreteFake`
**When** il s'exécute
**Then** aucun appel fournisseur payant n'est émis

**And Given** les critères de passage de 3 à 50 participants
**When** un scénario complet s'exécute
**Then** le rapport indique si latence médiane < 10 s, contenu condensé < 20 %, zéro blocage sur une heure, et coût par participant < 50 % du prix de son mode

**And Given** les métriques de NFR4
**When** un Salon s'exécute
**Then** elles sont émises et consultables, en test comme en production

**And Given** le ratio de méta-parole
**When** il est calculé pour un interprète
**Then** il rapporte le temps de parole non issu du journal au temps de parole total, en excluant le contenu condensé mais en incluant la phrase qui l'annonce

**And Given** le ratio de méta-parole
**When** il est publié
**Then** il est ventilé par palier — Base, Mode A, Mode B, Mode C — afin de rendre visible la charge d'interruption spécifique au palier le moins cher

**And Given** une cohorte de nouveaux inscrits
**When** sa fenêtre de péremption de 30 jours est écoulée
**Then** le **taux de conversion avant péremption** est publié : proportion de la cohorte ayant effectué au moins une recharge Stripe réussie avant l'expiration de son crédit

**And Given** une cohorte dont la fenêtre n'est pas encore close
**When** le taux est consulté
**Then** il est signalé comme **partiel** et jamais comparé à une cohorte close — sans quoi toute cohorte récente paraîtrait catastrophique

**And Given** une première recharge Stripe réussie
**When** elle est enregistrée
**Then** le **délai en minutes depuis l'inscription** est mesuré et conservé

**And Given** le délai avant première recharge
**When** il est publié
**Then** il l'est en **distribution** — médiane, p25, p75, p90 — et non en moyenne seule

**And Given** une personne n'ayant jamais rechargé
**When** les deux métriques sont calculées
**Then** elle est **exclue du délai** et **comptée au dénominateur** du taux de conversion

**And Given** une recharge échouée puis réussie
**When** le délai est mesuré
**Then** il court jusqu'à la **première réussite**, les tentatives échouées étant comptées séparément — un refus de carte n'est pas un refus d'acheter

### Story 7.6: Ordre d'Émission de la Méta-Parole

As a développeur,
I want un ordre déterministe quand plusieurs prises de parole de l'interprète sont prêtes ensemble,
So that la séquence soit reproductible et testable. (FR62)

**Acceptance Criteria:**

**Given** plusieurs prises de parole de l'interprète prêtes au même instant
**When** un emplacement inter-messages se libère
**Then** elles sont émises dans cet ordre :
```
1. signal « Vocaliz is busy » (FR49) et demande de recharge (FR56)
2. alerte de solde bas et annonce de fin de Salon imminent (FR55)
3. annonce publicitaire (FR39)
```

**And Given** cet ordre
**When** il est appliqué
**Then** **aucune prise de parole n'est supprimée ni reportée indéfiniment** — l'ordre les séquence, il ne les arbitre pas : les quatre sortent, l'une après l'autre

**And Given** la présentation d'un participant (FR58) et la restitution d'historique (FR59)
**When** elles ont lieu
**Then** elles interviennent à l'entrée dans la room, avant que le participant n'entre dans le flux de la conversation — elles ne concourent jamais avec les quatre ci-dessus

**And Given** la phrase annonçant une condensation (FR53)
**When** elle est émise
**Then** elle reste solidaire de la restitution qu'elle introduit et ne participe pas à cet ordonnancement

**And Given** deux exécutions du même scénario
**When** les mêmes prises de parole sont prêtes simultanément
**Then** la séquence produite est identique — l'ordre ne dépend jamais de l'ordonnancement interne des tâches

## Epic 8: Modes d'Expérience & Paliers Tarifaires

Chaque participant choisit son propre mode parmi quatre paliers payants, dispose d'un crédit de bienvenue de 5 USD, est prévenu avant que son solde ne s'épuise, et n'est facturé que pour son propre mode.

### Story 8.1: Flux d'Événements Comptables

> ⚠️ **PARTIELLEMENT HÉRITÉ — et le code montre déjà les bonnes propriétés.** `billing_events` et `ad_broadcasts` sont des journaux append-only, avec des garanties inscrites dans le schéma : `stripe_invoice_item_id` NULL rend la facturation **idempotente**, `ck_ad_broadcasts_billed_only_if_delivered` interdit de facturer ce qui n'a pas été diffusé, et `amount_cents` fige le prix au moment du fait pour que l'historique ne se reprice jamais.
> **Ce qui manque :** ce sont **deux journaux séparés**, pas un flux unique dont les vues dérivent. Reprendre leurs propriétés, unifier leur forme.

As a exploitant de Vocaliz,
I want que tout fait financier soit écrit une seule fois, dans un flux qui fait autorité,
So that mes journaux et mes métriques ne puissent jamais se contredire. (NFR7)

**Acceptance Criteria:**

**Given** un fait financier ou opérationnel — octroi de crédit, recharge, débit, remboursement, péremption, abandon
**When** il survient
**Then** il est écrit **une seule fois** dans un flux d'événements **append-only**, qui constitue la **seule source de vérité**

**And Given** un événement écrit
**When** il est enregistré
**Then** il porte un identifiant, un horodatage, un type, son sujet, son montant s'il y en a un, et son auteur — système ou exploitant

**And Given** le flux
**When** il est manipulé
**Then** aucun événement n'y est jamais **modifié ni supprimé** : une correction s'exprime par un événement compensatoire, jamais par une réécriture

**And Given** le journal d'audit des octrois (FR66), les écritures des crédits offerts (FR67), le journal du solde payé (FR68) et les métriques (NFR4)
**When** ils sont produits
**Then** ils sont **dérivés du flux**, jamais écrits en parallèle — trois écritures concurrentes du même fait finissent toujours par diverger, et rien ne permet alors de dire laquelle a raison

**And Given** une vue dérivée
**When** elle est reconstruite depuis le flux
**Then** elle produit **exactement le même résultat** qu'avant reconstruction — c'est la propriété qui rend le flux vérifiable

**And Given** une divergence constatée entre une vue et le flux
**When** elle est arbitrée
**Then** **le flux fait foi** et la vue est reconstruite

**And Given** le flux
**When** sa conservation est définie
**Then** elle est **durable et indépendante des comptes utilisateurs** — la suppression d'un compte n'efface aucun événement déjà écrit

### Story 8.2: Crédit Offert de 5 USD à Vie

> ⚠️ **À ADAPTER — un essai existe, mais d'une autre nature.** `users.trial_seconds_used` compte un essai **en temps** (une heure gratuite), consommé au fil des Salons.
> **Le changement :** l'essai devient **monétaire** — `solde_offert` de 5 USD, dont la durée varie selon le palier choisi. `trial_seconds_used` sort du modèle. À y ajouter : la péremption à 30 jours, l'avertissement à 7 jours, et le registre des identifiants brûlés, qui n'ont aucun équivalent hérité.

As a nouvel utilisateur,
I want essayer la voix naturelle sans débours,
So that je puisse juger avant de payer. (FR51)

**Acceptance Criteria:**

**Given** une personne s'inscrit avec un courriel ou un téléphone
**When** son compte est créé
**Then** son `solde_offert` est crédité de **5 USD**, une seule fois à vie

**And Given** les identifiants fournis à l'inscription
**When** le crédit est évalué
**Then** chacun est confronté au registre des identifiants ayant déjà donné lieu à un crédit — **si l'un d'eux y figure, aucun crédit n'est accordé**

**And Given** un crédit accordé
**When** il est enregistré
**Then** **tous** les identifiants fournis sont inscrits au registre et brûlés définitivement, y compris ceux qui n'ont pas servi à l'authentification

**And Given** un compte supprimé puis recréé avec les mêmes identifiants
**When** le crédit est évalué
**Then** aucun crédit n'est accordé — le registre survit à la suppression du compte, sinon la protection ne vaut rien

**And Given** le registre des identifiants brûlés
**When** le temps passe
**Then** il **ne périme jamais** : un identifiant brûlé le reste définitivement, indépendamment de la péremption du crédit lui-même

**And Given** un crédit accordé
**When** sa date d'expiration est calculée
**Then** elle vaut l'instant de l'octroi plus `peremption_credit` (30 jours calendaires, soit 2 592 000 secondes), **à la seconde près**, l'heure du jour étant conservée

**And Given** le calcul de l'expiration
**When** il est appliqué
**Then** il compte des **jours calendaires** — week-ends et jours fériés inclus, sans aucun calendrier à consulter et sans dépendance à une juridiction

**And Given** un `solde_offert` non consommé
**When** sa date d'expiration est atteinte
**Then** il est ramené à zéro ; le `solde_paye` et le `total_cumulatif` sont inchangés

**And Given** un participant en pleine Salon au moment où son crédit expire
**When** l'expiration survient
**Then** elle s'applique immédiatement, et la suite dépend de son `solde_paye` : s'il couvre, la conversation continue sans rien changer ; sinon, l'alerte puis la fin de Salon de FR55 s'appliquent normalement

**And Given** un `solde_offert` encore positif
**When** il reste `avertissement_peremption` (7 jours) avant l'échéance
**Then** l'utilisateur est averti sur **tous ses canaux disponibles** — courriel, SMS, ou les deux selon ses identifiants — un crédit qui s'évanouit en silence étant une charge d'acquisition dépensée pour rien

**And Given** l'avertissement de péremption
**When** il est rédigé
**Then** il énonce le **montant restant** et **ce qu'il achète** dans chaque palier — « il te reste 3,20 $, soit 1 h 36 en Base ou 38 min en Mode A » — plutôt qu'une simple date

**And Given** un `solde_offert` déjà épuisé
**When** l'échéance des 7 jours est atteinte
**Then** aucun avertissement n'est envoyé — il n'y a plus rien à perdre

**And Given** l'avertissement
**When** il a été envoyé
**Then** il ne l'est **qu'une seule fois** par crédit, jamais répété quotidiennement jusqu'à l'échéance

**And Given** une personne dont un identifiant est brûlé
**When** elle s'inscrit malgré tout
**Then** son compte est créé normalement et elle peut recharger pour utiliser n'importe quel palier — seul le cadeau lui est refusé, jamais le service

**And Given** un `solde_offert` et un `solde_paye` tous deux positifs
**When** un mode payant est consommé
**Then** le `solde_offert` est débité **en premier**, jusqu'à épuisement

**And Given** le crédit est exprimé en monnaie et non en minutes
**When** la personne choisit son mode
**Then** sa durée d'essai varie avec le tarif : 2 h en Mode A, 1 h en Mode B, 40 min en Mode C

**And Given** une personne a consommé ses 10 USD offerts
**When** elle rejoint un nouveau Salon
**Then** son `solde_offert` reste à zéro, quels que soient le Salon et son rôle, hôte ou invité — le crédit n'est jamais réattribué

**And Given** le mode Base
**When** il est consommé
**Then** il débite le solde comme tout autre palier, au tarif `prix_mode_base` (3 USD/h) — **aucun palier n'est gratuit**

**And Given** le `solde_offert` s'épuise alors que le `solde_paye` est positif
**When** la transition survient
**Then** aucune bascule de mode n'a lieu : l'interprète annonce simplement « ton crédit d'essai est terminé, je continue avec ton solde » et la conversation se poursuit à l'identique

**And Given** les deux parts du solde
**When** elles sont stockées
**Then** `solde_offert` et `solde_paye` sont deux valeurs **distinctes et persistées séparément** — jamais un total unique dont on déduirait les parts, `solde` n'étant qu'une **vue calculée**

**And Given** tout mouvement du solde, crédit comme débit
**When** il est enregistré
**Then** il consigne **laquelle des deux parts** il affecte, constituant une piste d'audit opposable en cas de contestation

**And Given** un remboursement est demandé
**When** il est calculé
**Then** il porte **exclusivement sur `solde_paye`** — le crédit offert par Vocaliz n'est jamais remboursable, quelle que soit la part consommée

**And Given** un utilisateur n'ayant jamais rechargé, dont seul le crédit offert a été entamé
**When** il réclame un remboursement
**Then** le montant remboursable est **zéro**, et la réponse énonce explicitement qu'aucune somme n'a été versée par lui

**And Given** les libellés destinés à l'utilisateur
**When** ils sont stockés en configuration
**Then** ils le sont **en anglais canonique** — `"Vocaliz welcome credit"` et `"Your topped-up balance"` — comme tout contenu destiné à la restitution : journal, créatifs publicitaires, annonces système

**And Given** un libellé de configuration en anglais
**When** il est présenté à un participant
**Then** il est traduit dans sa langue détectée au moment de la restitution, par le même chemin que n'importe quel contenu — la configuration ne contient jamais de variantes par langue

**And Given** le solde est présenté à l'utilisateur
**When** il est affiché ou annoncé
**Then** les deux parts sont **distinguées et nommées** par ces libellés, afin que nul ne puisse soutenir avoir cru disposer de dix dollars lui appartenant

**And Given** l'ordre de consommation
**When** il est appliqué
**Then** le `solde_offert` est débité en premier — ce qui protège aussi le remboursement : l'argent réellement versé par l'utilisateur reste intact le plus longtemps possible

### Story 8.3: Configuration des Trois Options par l'Hôte à la Création

As a hôte,
I want configurer mes trois options en créant le Salon,
So that je décide de mon expérience et de mon budget sans les imposer aux autres. (FR32, FR34)

**Acceptance Criteria:**

**Given** un hôte crée un Salon
**When** l'écran de création s'affiche
**Then** il y configure **trois options personnelles, au même endroit** :
```
1. PALIER D'EXPÉRIENCE   Base 3 $/h      annonces · voix synthétique
                         Mode A 7,50 $/h  annonces · voix naturelle
                         Mode B 15 $/h    sans annonces · voix naturelle
                         Mode C 22,50 $/h sans annonces · voix premium
                         → aucun palier n'est gratuit, le tarif est visible pour chacun

2. VIDÉO MUETTE          activée · désactivée          → désactivée par défaut

3. MONTANT DE RECHARGE   entre le plancher de sa granularité et 500 $
                         → plancher par défaut
```

**And Given** ces trois options
**When** elles sont enregistrées
**Then** elles sont **personnelles à l'hôte** et n'imposent rien aux autres participants

**And Given** les quatre paliers
**When** ils sont présentés
**Then** chacun n'ajoute **qu'une seule chose** au précédent — voix naturelle, puis absence d'annonces, puis modèle premium — de sorte que l'écart de prix soit toujours attribuable à une différence unique

**And Given** un utilisateur disposant d'un `solde_offert` non nul (Story 8.2)
**When** les paliers lui sont présentés
**Then** chacun affiche **la durée que son crédit couvre**, et non son seul tarif horaire :
```
Base     offert pendant 1 h 40 avec ton crédit de bienvenue
Mode A   offert pendant 0 h 40 avec ton crédit de bienvenue
Mode B   offert pendant 0 h 20 avec ton crédit de bienvenue
Mode C   offert pendant 0 h 13 avec ton crédit de bienvenue
```

**And Given** un crédit partiellement consommé
**When** les durées sont affichées
**Then** elles sont calculées sur le **solde offert restant**, jamais sur les 5 USD initiaux

**And Given** un utilisateur dont le `solde_offert` est épuisé
**When** les paliers lui sont présentés
**Then** le tarif horaire s'affiche seul, sans mention de crédit

**And Given** l'hôte choisit un mode
**When** le Salon démarre
**Then** ce choix ne s'applique qu'à lui et n'impose rien aux autres participants

**And Given** un Salon est créé
**When** les options s'affichent
**Then** le speech-to-speech est toujours proposé, quel que soit le contexte

### Story 8.4: Configuration des Trois Options par le Participant à la Jonction

As a participant invité,
I want configurer mes propres options en rejoignant,
So that je ne subisse pas les choix de quelqu'un d'autre. (FR35)

**Acceptance Criteria:**

**Given** un invité clique un lien de jonction
**When** l'écran de jonction s'affiche
**Then** il y configure **les mêmes trois options** que l'hôte — palier, vidéo muette, montant de recharge — indépendamment des choix de celui-ci

**And Given** trois participants dans un même Salon
**When** chacun a configuré ses options
**Then** les trois jeux de choix coexistent sans interaction : un palier différent, une vidéo active ou non, un montant de recharge propre à chacun

**And Given** l'invité n'a jamais utilisé Vocaliz
**When** il choisit un mode
**Then** son crédit de bienvenue de 5 USD s'applique avant toute demande de paiement

**And Given** l'hôte a activé « l'hôte paie tout »
**When** l'invité rejoint
**Then** il est placé en Mode B sans annonces et aucun choix de mode ne lui est demandé — FR42 prime sur FR35, et toujours vers le haut

### Story 8.5: Salon Mixte et Persistance du Mode

As a participant,
I want conserver mon mode tout le Salon,
So that mon expérience reste stable et prévisible. (FR36, FR37)

**Acceptance Criteria:**

**Given** trois participants ont choisi trois modes différents
**When** le Salon se déroule
**Then** chacun vit son propre mode et l'orchestrateur ne fait aucune distinction entre eux

**And Given** un participant a choisi son mode
**When** le Salon se poursuit
**Then** ce mode persiste jusqu'à la fin, sauf changement explicite de sa part

**And Given** un participant change explicitement de mode en cours de Salon
**When** le changement est appliqué
**Then** l'adaptateur de sa room est remplacé sans rupture de Salon

### Story 8.6: Facturation par Mode et Option « L'Hôte Paie Tout »

> ⚠️ **À ADAPTER — la facturation existe, mais post-payée et à tarif unique.** `services/stripe_service.py`, `users.billed_seconds`, `users.stripe_customer_id`, `users.stripe_payment_method_id` et la table `billing_events` fonctionnent : Salon facture l'hôte après le Salon, 5 USD/h au-delà de l'essai.
> **Le changement :** quatre paliers, chacun payant le sien, et un **prépayé** qui inverse le sens du flux. L'intégration Stripe et le moyen de paiement enregistré se reprennent tels quels ; la logique de calcul, non.

As a participant,
I want ne payer que pour mon propre mode,
So that ma facture soit compréhensible. (FR40, FR41, FR42)

**Acceptance Criteria:**

**Given** un participant consomme un mode payant au-delà de son quota
**When** le Salon se déroule
**Then** il est facturé au tarif de son propre mode, au prorata de la seconde (remplace FR22)

**And Given** un participant sans moyen de paiement valide
**When** son solde est épuisé
**Then** son Salon se termine (FR55) — il n'est jamais facturé au-delà de ce qu'il a prépayé, et aucune créance n'est constituée

**And Given** un hôte active « l'hôte paie tout » à la création
**When** le Salon se déroule
**Then** l'hôte est facturé `prix_mode_b` × nombre de participants, et tous les participants sont en Mode B sans annonces

**And Given** l'option « l'hôte paie tout » est proposée
**When** l'hôte s'apprête à l'activer
**Then** le coût horaire maximal résultant lui est affiché explicitement et il doit le confirmer avant que l'option ne s'active

### Story 8.7: Solde Prépayé et Recharge Stripe

As a payeur,
I want payer d'avance et voir combien de secondes il me reste,
So that je ne reçoive jamais de facture que je n'ai pas déjà autorisée. (FR56)

**Acceptance Criteria:**

**Given** un participant souhaitant consommer un mode payant
**When** son droit est évalué
**Then** il doit disposer d'un `solde` strictement positif — `solde_offert` ou `solde_paye` — **aucun mode ne démarre à découvert**, tous les paliers étant payants

**And Given** un participant consomme un mode payant
**When** le temps s'écoule
**Then** son `solde_offert` est consommé en premier, puis son `solde_paye`, tenus **en millicents** et décrémentés chaque `intervalle_echantillonnage` (5 s) — jamais en cents entiers

**And Given** un tick de décrément produisant une valeur fractionnaire
**When** il est appliqué
**Then** le reste est **reporté au tick suivant** via un accumulateur **entier** en cent·minutes — aucun flottant n'entre jamais dans le grand livre

**And Given** un Salon de 1 h 1 min 2 s
**When** elle est facturée
**Then** **1 h 1 min 0 s** est débitée et les 2 secondes sont abandonnées — seuls les blocs de 5 secondes complétés sont facturés

**And Given** un bloc entamé mais non complété
**When** le Salon se termine
**Then** il n'est **jamais** débité : l'échantillonnage se faisant aux 5 secondes, facturer une durée non mesurée exposerait à une contestation

**And Given** un Salon de moins de cinq secondes
**When** elle se termine
**Then** rien n'est facturé — conséquence assumée de l'arrondi vers le bas

**And Given** l'arrondi de **facturation**
**When** il s'applique
**Then** il se fait **vers le bas**, en faveur du client — à ne pas confondre avec l'arrondi de **vérification** de FR63, qui se fait vers le haut par prudence

**And Given** le solde est affiché ou prélevé
**When** un montant est présenté à l'utilisateur ou envoyé à Stripe
**Then** la conversion en cents a lieu **une seule fois**, à cette frontière, par une division entière du compteur de cent·minutes

**And Given** le taux effectif change entre deux ticks
**When** le tick suivant s'applique
**Then** chaque intervalle est facturé au taux qui avait cours pendant lui, sans réévaluer rétroactivement les ticks déjà appliqués

**And Given** un payeur portant plusieurs participants
**When** son taux de consommation est calculé
**Then** il vaut la somme des tarifs de tous les participants qu'il porte, suppléments téléphoniques compris, divisée par 3600 — exprimée en cents par seconde

**And Given** un participant rejoint, quitte ou change de palier
**When** la composition du Salon change
**Then** le taux effectif du payeur est recalculé immédiatement, sans que le solde en cents n'ait à être converti

**And Given** un participant consulte son solde
**When** il est affiché ou annoncé vocalement
**Then** il est exprimé en **secondes restantes**, dérivées du taux effectif à cet instant — c'est une vue du solde en cents, recalculée à chaque changement de taux, jamais une unité de stockage

**And Given** un payeur qui n'a rien choisi
**When** son compte est créé
**Then** sa granularité de recharge est **hebdomadaire** (`periode_encaissement_defaut`), l'option mensuelle restant disponible à tout moment

**And Given** un solde devenu insuffisant
**When** une recharge est déclenchée
**Then** son montant est `weekly_budget_limit` (10 USD) ou `monthly_budget_limit` (43,33 USD) selon la granularité choisie — la recharge est déclenchée par le **besoin**, jamais par le calendrier

**And Given** une recharge est nécessaire
**When** elle est déclenchée
**Then** l'interprète **demande vocalement au participant qui paie s'il souhaite recharger**, en énonçant le montant configuré dans son `montant_recharge` — la recharge n'est jamais engagée sans un accord parlé

**And Given** le payeur accepte vocalement **et** dispose d'un moyen de paiement déjà enregistré chez Stripe
**When** son accord est reçu
**Then** le débit est exécuté immédiatement par `PaymentIntent` **hors session** sur ce moyen de paiement — aucun lien n'est envoyé, le payeur ne quitte pas la conversation

**And Given** le débit hors session réussit
**When** Stripe confirme
**Then** le solde est crédité et chacun retrouve son mode d'origine en quelques secondes — le passage en mode Base n'aura duré que le temps de la question et de la réponse

**And Given** le payeur accepte vocalement mais **ne dispose d'aucun moyen de paiement enregistré**
**When** son accord est reçu
**Then** un lien lui est envoyé **sur tous les canaux dont il dispose** — courriel, SMS, ou les deux selon les identifiants qu'il a fournis — et le moyen de paiement est enregistré à cette occasion pour toutes les recharges suivantes

**And Given** un payeur n'ayant fourni qu'un seul identifiant
**When** un lien doit lui être envoyé
**Then** il part sur ce seul canal, sans échec ni avertissement — un identifiant unique est un choix valide, jamais une configuration incomplète

**And Given** un débit hors session refusé — carte expirée, provision insuffisante, ou authentification forte exigée par la banque
**When** l'échec est reçu
**Then** le système bascule sur le chemin de repli et envoie le lien sur tous les canaux dont dispose le payeur, en l'informant vocalement que sa carte n'a pas répondu

**And Given** le chemin de repli est un repli
**When** il est emprunté
**Then** ce n'est jamais le chemin par défaut d'un payeur ayant déjà payé une fois

**And Given** le payeur refuse vocalement
**When** son refus est reçu
**Then** aucun lien n'est envoyé, il reste en mode Base pour la suite du Salon, et la question n'est pas reposée

**And Given** le payeur ne répond pas à la question
**When** l'interprète n'obtient pas de réponse
**Then** il repose la question une seule fois, puis renonce — le participant reste en mode Base

**And Given** la recharge est autorisée
**When** Stripe confirme
**Then** le `solde` est crédité, `total_cumulatif` est augmenté du montant payé, et le Salon se poursuit sans interruption

**And Given** un solde partiellement inutilisé
**When** la période s'achève
**Then** il est **reporté sans expiration** — c'est de l'argent déjà payé, il n'est jamais repris

**And Given** une recharge déclenchée par le franchissement de `seuil_alerte_solde`
**When** elle est en cours
**Then** **la conversation se poursuit normalement** dans le mode courant : le solde n'est pas encore épuisé, il n'y a ni bascule ni interruption — c'est précisément ce que l'alerte anticipée rend possible

**And Given** une recharge autorisée avant l'épuisement
**When** Stripe confirme
**Then** le solde est crédité et personne ne s'aperçoit de rien — aucun mode n'a changé, aucune annonce de bascule n'est nécessaire

**And Given** l'autorisation est refusée, ou n'arrive pas avant l'épuisement du solde
**When** le solde atteint zéro
**Then** la fin de Salon de FR55 s'applique — et la fermeture du Salon si le payeur est l'hôte

**And Given** l'autorisation n'est ni accordée ni refusée
**When** `delai_expiration_recharge` (5 min) s'écoule
**Then** la demande expire et une nouvelle pourra être émise ultérieurement, si le solde n'est pas déjà épuisé

**And Given** l'option « l'hôte paie tout » (FR42) ou un participant téléphonique (FR57)
**When** le coût est imputé
**Then** il est décrémenté du `solde` **de l'hôte seul**, les participants couverts ne consommant ni leur solde ni leur quota gratuit

**And Given** le solde ne peut jamais devenir négatif
**When** un mode payant est consommé
**Then** aucune créance n'est jamais constituée et aucun recouvrement n'est jamais nécessaire

### Story 8.13: Rabais de Recharge par Navigateur

As a exploitant de Vocaliz,
I want inciter les recharges hors application,
So that j'évite la commission des magasins plutôt que de la subir. (FR71)

**Acceptance Criteria:**

**Given** une recharge initiée depuis un **navigateur** — Chrome, Safari ou autre
**When** son montant est calculé
**Then** `rabais_recharge_web` (5 %) est appliqué : le payeur reçoit 5 % de solde en plus pour le même débit

**Given** une recharge initiée depuis l'**application mobile**
**When** son montant est calculé
**Then** aucun rabais ne s'applique

**And Given** le choix du canal de recharge
**When** il est présenté au payeur
**Then** l'écart de prix lui est **annoncé explicitement** — un rabais qu'on ne connaît pas n'oriente personne

**And Given** le taux de rabais
**When** il est configuré
**Then** il est **ventilable par plateforme, par région et par tranche de revenu annuel**, la commission de magasin évitée variant de 5 % (Android États-Unis sous un million) à 30 % (iOS hors États-Unis au-delà) — à 5 %, le rabais est couvert dans toutes les combinaisons, y compris la plus défavorable

**And Given** le franchissement du million de dollars de revenu annuel
**When** les commissions doublent
**Then** le rabais doit pouvoir être relevé **sans déploiement** : l'écart entre magasin et navigateur passe de 15 à 30 points, et le canal web devient une nécessité économique plutôt qu'une optimisation

**And Given** un rabais supérieur à la commission réellement évitée
**When** la configuration est enregistrée
**Then** elle est acceptée mais **signalée** : c'est une décision d'acquisition, elle ne doit pas être prise par inadvertance

**And Given** un rabais accordé
**When** il est enregistré
**Then** il alimente le journal comptable du solde payé (FR68) en distinguant le montant encaissé du montant crédité — l'écart est une charge commerciale, non un encaissement

**And Given** la position réglementaire, en litige devant la Cour suprême jusqu'en 2027
**When** les commissions changent
**Then** l'ajustement du rabais est une **modification de configuration**, sans déploiement (FR54)

### Story 8.8: Vérification Périodique de la Couverture du Solde

> ⚠️ **PARTIELLEMENT HÉRITÉ.** Le battement existe déjà et sert au métrage : `salons.last_heartbeat_at`, `POST /{salon_id}/heartbeat`, et `agent/tests/test_heartbeat.py`.
> **Ce qui manque :** la cadence passe à 5 secondes, et le battement porte désormais **le débit du solde et la vérification de couverture**, pas seulement la preuve de vie. La détection de worker muet, elle, se reprend telle quelle.

As a payeur,
I want que le système vérifie sans cesse que mon solde couvre la suite,
So that je sois prévenu avant l'épuisement plutôt qu'au moment où il survient. (FR63)

**Acceptance Criteria:**

**Given** un Salon actif
**When** un bloc de 5 secondes s'écoule
**Then** le même événement débite le bloc écoulé (FR56) puis évalue, **pour chaque payeur actif**, si son solde couvre **un bloc complet supplémentaire**

**And Given** le coût d'un bloc complet
**When** il est évalué pour la vérification
**Then** il est **arrondi à la hausse au cent** — jamais vers le bas ; à ce niveau de granularité, Base et Mode A exigent le même cent, ce qui est le comportement voulu, la vérification étant conservatrice :
```
Base     300 ¢/h ÷ 720 = 0,417 ¢  →  1 ¢ exigé
Mode A   750 ¢/h ÷ 720 = 1,042 ¢  →  2 ¢ exigés
Mode B  1500 ¢/h ÷ 720 = 2,083 ¢  →  3 ¢ exigés
Mode C  2250 ¢/h ÷ 720 = 3,125 ¢  →  4 ¢ exigés
max     6000 ¢/h ÷ 720 = 8,333 ¢  →  9 ¢ exigés
```

**And Given** la gigue d'ordonnancement, non négligeable à cette cadence
**When** un tick s'exécute avec du retard
**Then** le débit porte sur le **temps réellement écoulé** depuis le tick précédent, jamais sur la cadence nominale supposée

**And Given** les deux arrondis du système
**When** ils sont implémentés
**Then** ils vont en sens **opposés et délibérément** : la **facturation** arrondit vers le bas, en faveur du client ; la **vérification** arrondit vers le haut, par prudence — on ne laisse jamais commencer une minute qui pourrait ne pas être couverte

**And Given** le décrément et la vérification partagent la même cadence
**When** le tick s'exécute
**Then** l'ordre est **débiter puis vérifier** — on ne promet jamais une minute que le débit qui vient d'avoir lieu rend impossible

**And Given** une couverture insuffisante pour la minute suivante
**When** elle est constatée
**Then** l'interprète en avertit **poliment** le participant, dans sa langue, en annonçant le passage en mode Base et en nommant la cause — budget épuisé — sans reproche ni injonction

**And Given** la vérification porte sur les payeurs et non sur les participants
**When** un hôte couvre plusieurs participants (FR42, FR57)
**Then** il est évalué **une seule fois par minute**, sur son taux effectif agrégé — la couverture exigée est celle de **tous** les participants qu'il paie, pas la sienne seule

**And Given** un payeur qui couvre d'autres participants
**When** il règle son `montant_recharge`
**Then** il peut le relever au-dessus du plancher de sa granularité, sans jamais descendre en dessous ni dépasser `plafond_recharge` (500 USD)

**And Given** un montant de recharge demandé hors bornes
**When** il est enregistré
**Then** il est refusé avec un message explicite, jamais silencieusement ramené dans les bornes

**And Given** un hôte s'apprêtant à activer « l'hôte paie tout » (FR42) ou à inviter un participant téléphonique (FR57)
**When** l'engagement est confirmé
**Then** le taux effectif résultant lui est annoncé **en dollars par heure et en minutes de couverture restantes au solde actuel**, afin qu'il dimensionne sa recharge avant de commencer plutôt que d'être interrompu au bout d'un quart d'heure

**And Given** un solde manifestement insuffisant pour le taux effectif engagé
**When** l'hôte confirme malgré tout
**Then** le Salon démarre — l'avertissement informe, il n'interdit pas

**And Given** un payeur dont le solde descend sous `seuil_alerte_solde` (3 min de couverture)
**When** la vérification s'exécute
**Then** l'alerte de FR55 est émise et **une seule** recharge est déclenchée — la conversation se poursuivant normalement pendant ce temps

**And Given** une recharge déjà en attente d'autorisation pour ce payeur
**When** les vérifications suivantes s'exécutent
**Then** aucune demande supplémentaire n'est émise — un mécanisme périodique ne doit pas produire une demande tous les cinq secondes

**And Given** un payeur dont le solde ne couvre pas le bloc suivant
**When** la vérification s'exécute
**Then** son Salon se termine selon FR55, et le Salon se ferme s'il est l'hôte — sans jamais laisser le solde entamer un bloc qu'il ne couvre pas

**And Given** une recharge autorisée entre-temps
**When** la vérification suivante s'exécute
**Then** la couverture est de nouveau suffisante, l'alerte est réarmée, et aucune action n'est déclenchée

**And Given** le heartbeat de métrage existant, émis toutes les 30 secondes par le worker (Story 4.2)
**When** la vérification minutée est implémentée
**Then** elle s'appuie sur cette infrastructure plutôt que d'en créer une seconde

**And Given** un worker qui cesse d'émettre
**When** une minute passe sans signal pour un Salon actif
**Then** la consommation est arrêtée côté serveur plutôt que poursuivie à l'aveugle — un solde ne se décrémente jamais sur un Salon dont on n'a plus de nouvelles

### Story 8.9: Alerte de Solde Bas et Fin de Salon

As a participant dont le solde s'épuise,
I want être prévenu à temps plutôt que coupé sans avertissement,
So that je puisse recharger avant que ma conversation ne s'arrête. (FR55)

**Acceptance Criteria:**

**Given** un participant dont le solde couvre moins de `seuil_alerte_solde` (3 min) au taux effectif
**When** la vérification périodique de la Story 8.8 constate le franchissement
**Then** son interprète l'en avertit **poliment**, dans sa langue, en annonçant le temps restant et en proposant une recharge (FR56)

**And Given** un **hôte** dont le solde couvre moins de `seuil_alerte_hote` (5 min) au taux effectif
**When** le seuil est franchi
**Then** il est averti **plus tôt qu'un simple participant** — par politesse envers ceux qu'il reçoit, dont la conversation dépend de son solde

**And Given** l'alerte adressée à un hôte
**When** elle est formulée
**Then** elle **nomme explicitement la conséquence** : à l'épuisement, le Salon se fermera pour tous ses invités — un hôte doit pouvoir décider en connaissance de cause

**And Given** le taux effectif d'un hôte qui couvre d'autres participants (FR42, FR57)
**When** son temps restant est calculé
**Then** il l'est sur le taux **agrégé** — ce qu'il paie pour tout le monde — et non sur son seul palier

**And Given** l'alerte de l'hôte
**When** elle est émise
**Then** elle l'est **dans sa seule room** : ses invités n'en savent rien, la situation financière d'un hôte n'ayant pas à devenir audible pour ceux qu'il reçoit

**And Given** l'alerte a déjà été émise pour ce participant
**When** le solde continue de descendre
**Then** elle n'est pas répétée à chaque tick — une seule alerte, puis un dernier rappel à 60 secondes du terme

**And Given** un solde atteignant zéro
**When** l'épuisement survient
**Then** **le Salon de ce participant se termine** — il n'existe aucun palier gratuit vers lequel se replier

**And Given** la fin de Salon pour solde épuisé
**When** elle survient
**Then** l'interprète l'annonce avant de raccrocher, sans reproche, et la question de satisfaction de FR26 est posée comme pour toute fin de Salon

**And Given** la séquence de clôture — annonce de fin puis question de satisfaction
**When** elle est exécutée à solde nul
**Then** elle est **le seul usage autorisé à solde zéro** et n'est **jamais facturée**, ce qui lève la contradiction avec la règle « aucune consommation sans couverture » de FR63

**And Given** cette exonération
**When** elle s'applique
**Then** elle est **bornée à la durée de la séquence de clôture** : dès celle-ci terminée, la room se ferme et aucune parole supplémentaire n'est produite

**And Given** un participant qui tenterait de prolonger la conversation pendant la séquence de clôture
**When** il parle
**Then** son propos n'est ni ingéré ni ajouté au journal — l'exonération couvre la parole de l'interprète, jamais une reprise de la conversation

**And Given** le participant dont le solde s'épuise est **l'hôte**
**When** son Salon se termine
**Then** **le Salon se ferme pour tous les participants**, chacun étant informé vocalement par son propre interprète avant la fermeture

**And Given** la fermeture imminente d'un Salon
**When** il reste `preavis_fermeture_invites` (15 s)
**Then** chaque invité en est averti par son interprète, dans sa langue, afin qu'il ait le temps de se dire au revoir

**And Given** ce préavis
**When** il est formulé
**Then** il annonce **le fait sans la cause** — « le Salon va se fermer dans quinze secondes » — sans jamais nommer l'hôte ni évoquer son solde : la situation financière de celui qui reçoit ne devient audible pour personne

**And Given** les quinze secondes de préavis
**When** elles s'écoulent
**Then** elles relèvent de la **séquence de clôture** et ne sont donc **pas facturées**, comme le reste de la clôture

**And Given** la fermeture d'un Salon par épuisement du solde de l'hôte
**When** elle survient
**Then** les participants qui payaient leur propre expérience cessent d'être facturés à cet instant, sans perte de solde

**And Given** un participant qui recharge avant l'épuisement
**When** la recharge est créditée
**Then** aucune interruption n'a lieu : il n'a jamais quitté son mode, et l'alerte est réarmée pour le prochain franchissement du seuil

### Story 8.10: Octroi Manuel d'un Second Crédit

As a exploitant de Vocaliz,
I want pouvoir réoffrir un crédit par commande en ligne à quelqu'un qui a essayé puis dérivé,
So that le registre anti-fraude ne m'interdise pas mes propres campagnes de réactivation. (FR66)

> **Portée MVP :** commande en ligne uniquement, exécutée par l'exploitant. Aucune interface d'administration n'est à construire.

**Acceptance Criteria:**

**Given** un utilisateur dont les identifiants figurent au registre des identifiants brûlés
**When** un administrateur autorisé lui accorde un second crédit
**Then** l'octroi est accepté malgré le registre — c'est une **exception explicite**, jamais une péremption du registre

**And Given** un utilisateur dont le crédit précédent date de moins de `delai_min_second_cadeau` (90 jours)
**When** un second crédit est demandé
**Then** il est refusé — le délai minimal empêche que l'exception ne devienne une porte dérobée

**And Given** un octroi manuel sans montant précisé
**When** il est exécuté
**Then** il applique `credit_reactivation` (**3 USD**) — soit 1 h 30 en Base, 36 min en Mode A, 18 min en Mode B ou 12 min en Mode C

**And Given** un octroi manuel avec un montant précisé
**When** il est exécuté
**Then** ce montant prime sur le défaut, dans la limite de `plafond_recharge` — faire revenir quelqu'un et le faire découvrir n'ont pas la même valeur

**And Given** un octroi manuel
**When** il est enregistré
**Then** il est **journalisé** avec son auteur, son horodatage, les identifiants visés, le montant et le motif — émettre de la monnaie sans trace est le seul usage qu'un audit ne pardonne pas

**And Given** une campagne de réactivation
**When** elle vise plusieurs personnes
**Then** l'octroi peut s'appliquer à une **cohorte** en une opération, chaque bénéficiaire donnant lieu à son propre enregistrement au journal

**And Given** un crédit accordé manuellement
**When** il est crédité
**Then** il alimente `solde_offert` et hérite des mêmes règles que le crédit de bienvenue — non remboursable, consommé en premier, péremption à 30 jours, avertissement à 7 jours

**And Given** cette capacité d'émission
**When** elle est exposée
**Then** elle l'est **par une commande en ligne uniquement**, exécutée depuis l'environnement de production — aucune interface web ni mobile, aucun écran d'administration, aucun point d'entrée réseau

**And Given** le contrôle d'accès
**When** il est défini
**Then** il repose sur l'**accès à l'environnement de production** lui-même — il n'existe ni table de comptes administrateurs, ni authentification d'administrateur à construire

**And Given** l'exécution de la commande
**When** elle a lieu
**Then** elle demande une **confirmation explicite** rappelant le montant total qui sera émis et le nombre de bénéficiaires, avant d'écrire quoi que ce soit

**And Given** un octroi par commande en ligne
**When** il est exécuté
**Then** il est journalisé exactement comme tout autre octroi — l'absence d'interface ne dispense pas de la trace

### Story 8.11: Journal Comptable des Crédits Offerts

As a exploitant de Vocaliz,
I want une trace comptable de tous les crédits que j'offre,
So that je sache ce que mon acquisition me coûte réellement. (FR67)

**Acceptance Criteria:**

**Given** un crédit de bienvenue accordé automatiquement (5 USD)
**When** il est émis
**Then** une **écriture comptable** est créée : bénéficiaire, type `bienvenue`, montant émis, horodatage, auteur `système`, date de péremption

**And Given** un crédit de réactivation accordé manuellement (3 USD)
**When** il est émis
**Then** une écriture de même forme est créée, de type `réactivation`, avec l'exploitant comme auteur et le motif saisi à l'octroi

**And Given** une écriture de crédit
**When** elle est suivie
**Then** elle porte **quatre montants distincts** : `émis`, `consommé`, `périmé non consommé` et `abandonné par suppression de compte`

**And Given** une écriture close
**When** son invariant est vérifié
**Then** `émis = consommé + périmé + abandonné` — toujours, sans exception

**And Given** un compte supprimé avant la péremption de son crédit
**When** la suppression est traitée
**Then** le reliquat non consommé est inscrit en **`abandonné`** et l'écriture est close — sans ce troisième mode de clôture, tout total par période serait silencieusement faux dès la première suppression

**And Given** un débit du `solde_offert`
**When** il est appliqué
**Then** il est **attribué au crédit qui le finance**, de sorte que le montant consommé de chaque écriture soit exact même si une personne a reçu plusieurs crédits successifs

**And Given** un crédit atteignant sa date de péremption
**When** l'expiration est appliquée
**Then** le reliquat non consommé est inscrit en `périmé non consommé` et l'écriture est **close**

**And Given** la nature de la charge
**When** elle est évaluée
**Then** **seul le montant consommé constitue une charge réelle** — lui seul a engagé un coût fournisseur ; un crédit périmé sans usage ne coûte rien et ne doit pas être comptabilisé comme une dépense

**And Given** les écritures de crédit
**When** un total par période est demandé
**Then** les trois états sont restitués séparément — émis, consommé, périmé — pour la période choisie et par type de crédit

**And Given** ces écritures
**When** elles sont conservées
**Then** elles le sont **durablement**, indépendamment de la suppression éventuelle du compte bénéficiaire — une charge comptabilisée ne disparaît pas parce qu'un utilisateur s'en va

**And Given** la distinction avec le `solde_paye`
**When** les deux sont rapprochés
**Then** ils ne sont **jamais mêlés** : le crédit offert est une charge d'acquisition, le solde payé est un passif envers l'utilisateur

**And Given** le flux d'événements unique de NFR7
**When** ces écritures sont produites
**Then** elles en sont une **vue dérivée**, jamais une écriture parallèle

### Story 8.12: Journal Comptable du Solde Payé

> ⚠️ **PARTIELLEMENT HÉRITÉ.** `models/billing_event.py` enregistre déjà chaque tentative de prélèvement — montant, devise, `stripe_payment_intent_id`, statut succès ou échec, Salon concerné — *« so charges can be reconciled with Stripe »*.
> **Ce qui manque :** les quatre états du passif — encaissé, consommé, remboursé, **restant dû** — et l'isolement des soldes dormants par ancienneté.

As a exploitant de Vocaliz,
I want savoir à tout instant combien d'argent client je détiens,
So that je puisse répondre à mon comptable et provisionner correctement. (FR68)

**Acceptance Criteria:**

**Given** une recharge Stripe réussie
**When** elle est créditée
**Then** elle est inscrite en **`encaissé`** avec son horodatage, son montant et son payeur

**And Given** une consommation imputée au `solde_paye`
**When** elle est débitée
**Then** elle est inscrite en **`consommé`** — la part du prépayé effectivement transformée en service rendu

**And Given** un remboursement exécuté
**When** il est versé
**Then** il est inscrit en **`remboursé`**, distinct du consommé : de l'argent qui repart n'est pas de l'argent gagné

**And Given** une clôture de période
**When** les totaux sont produits
**Then** les quatre mouvements sont restitués séparément — **encaissé, consommé, remboursé, restant dû** — pour la période choisie

**And Given** le montant **restant dû**
**When** il est calculé
**Then** il vaut la somme des `solde_paye` de tous les utilisateurs à l'instant de clôture, et constitue le **passif envers les utilisateurs** — l'argent client détenu

**And Given** ce passif
**When** il est présenté
**Then** il n'est **jamais mêlé** aux crédits offerts de FR67 : l'un est une dette, l'autre une charge, et les additionner rendrait les deux illisibles

**And Given** un `solde_paye` reporté sans expiration
**When** un utilisateur cesse toute activité
**Then** son solde reste dû indéfiniment et continue de figurer au passif — le journal doit permettre d'**isoler les soldes dormants** par ancienneté de dernière activité

**And Given** un utilisateur inactif depuis **un an** dont le `solde_paye` est positif
**When** l'anniversaire d'inactivité est atteint
**Then** un courriel lui est envoyé, l'informant que son compte chez **Vocaliz.net** est inactif depuis un an et lui indiquant **le solde restant à son compte**

**And Given** ce courriel de relance
**When** il est expédié
**Then** il est envoyé en **copie à `s.degrandpre@vocaliz.net`**

**And Given** un utilisateur inactif dont le `solde_paye` est nul
**When** l'anniversaire est atteint
**Then** aucun courriel n'est envoyé — il n'y a rien à réclamer

**And Given** un utilisateur n'ayant fourni qu'un numéro de téléphone
**When** la relance doit être envoyée
**Then** elle part par SMS sur ce canal, conformément à la règle d'identité — un identifiant unique reste un choix valide

**And Given** une relance déjà envoyée
**When** une nouvelle année d'inactivité s'écoule sans que le solde ait bougé
**Then** la relance est **renouvelée**, chaque anniversaire donnant lieu à un envoi tant que le solde reste positif

**And Given** toute relance
**When** elle est expédiée
**Then** elle est **journalisée** — destinataire, date, montant signalé — constituant la trace des démarches entreprises pour joindre le titulaire d'un solde dormant

**And Given** une activité de l'utilisateur, connexion ou Salon
**When** elle survient
**Then** le compteur d'inactivité repart à zéro

**And Given** le flux d'événements unique de NFR7
**When** ce journal est produit
**Then** il en est une **vue dérivée**, au même titre que les écritures de FR67 et les métriques de NFR4

## Epic 9: Régie d'Annonces Géolocalisées

Les participants en Base et en Mode A entendent des annonces pertinentes pour leur région, dans leur langue, glissées entre deux messages et jamais au milieu d'une pensée.

### Story 9.1: Consentement de Géolocalisation à l'Inscription

> ⚠️ **PARTIELLEMENT HÉRITÉ — et le modèle hérité est plus prudent que la story.** `salon_events.plus_code` stocke une **cellule Open Location Code de six chiffres** (≈ 5,5 km), encodée à l'ingestion : *« the precise coordinates never reach the disk »*. Le commentaire précise pourquoi une cellule plutôt que des décimales arrondies — *« a decimal pair still reads as a point, and a point invites being treated as one »* — et pourquoi il n'y a **aucun repli par géolocalisation IP**. La demande au navigateur existe : le champ est vide quand la personne refuse.
> **Ce qui manque :** le consentement **explicite et nommé** à l'inscription, et son **retrait** à tout moment.

As a utilisateur,
I want décider si ma position sert à cibler les annonces,
So that je garde le contrôle de mes renseignements personnels. (FR50)

**Acceptance Criteria:**

**Given** une personne s'inscrit
**When** l'inscription se déroule
**Then** un écran unique lui demande explicitement son consentement à l'utilisation de sa géolocalisation à des fins publicitaires

**And Given** une personne refuse
**When** elle utilise Salon
**Then** elle reçoit des annonces génériques non ciblées et conserve l'accès complet au produit — le refus n'entraîne jamais une perte de service

**And Given** une personne a consenti
**When** elle souhaite revenir sur son choix
**Then** elle peut retirer son consentement à tout moment, avec effet immédiat

### Story 9.2: Adaptation de l'Échange Publicitaire Hérité

As a exploitant de Vocaliz,
I want conserver l'échange publicitaire de Salon et l'adapter à la topologie multi-rooms,
So that je ne remplace pas un système d'enchères par une table d'inventaire. (FR50)

> 🛑 **NE PAS RECONSTRUIRE.** Salon livre déjà un échange publicitaire complet, plus capable que ce que cette story décrivait à l'origine :
>
> ```
> ads                  sales_pitch · bid_cents · number_of_broadcasts_left · topic · spoken_language
> ads_regions          ciblage par cellules Open Location Code
> advertisers_regions  régions nommées achetées par l'annonceur
> ad_broadcasts        preuve de diffusion · amount_cents figé · facturation Stripe idempotente
> ad_auction_service   ENCHÈRE AU SECOND PRIX
> ad_billing_service · house_ads
> ```
>
> Avec des garanties inscrites dans le schéma : `ck_ad_broadcasts_billed_only_if_delivered` — **jamais de facturation pour une annonce que personne n'a entendue** — et `RESTRICT` sur la suppression, qui rend les preuves de diffusion indestructibles.
>
> **Ce qui reste à faire est une adaptation**, pas une construction.

**Acceptance Criteria:**

**Given** l'échange publicitaire hérité
**When** Vocaliz est construit
**Then** il est **conservé tel quel** dans sa mécanique d'enchère, de facturation et de preuve de diffusion — aucune de ces trois parties n'est réécrite

**And Given** la topologie multi-rooms
**When** une annonce est diffusée
**Then** elle l'est **dans la room d'un participant précis**, par son interprète, et non dans une room partagée — c'est le seul changement structurel que Vocaliz impose à ce sous-système

**And Given** le champ `ads.topic`, aujourd'hui branché sur rien
**When** son usage est envisagé
**Then** il **reste débranché** : cibler la publicité sur le contenu d'une conversation est une question de consentement d'une autre nature que la conserver pour la traduire. FR50 ne cible que la **géolocalisation** et la **langue**

**And Given** les trois mécanismes de géographie qui coexistent — `ads_regions`, `advertisers_regions`, et les JSONB `target_countries` / `target_regions` / `circle`
**When** le sous-système est repris
**Then** le troisième est **supprimé** : il n'a jamais eu de données, et nommer le pays d'une cellule exigerait un géocodage inverse qui n'existe pas ici

**And Given** la précision des Open Location Codes
**When** une annonce est appariée à un participant
**Then** les deux côtés restent à **six chiffres** — une cellule est comparée comme une chaîne, et une précision différente n'apparie silencieusement rien plutôt que d'échouer

**Acceptance Criteria complémentaires — ciblage :**

**Given** la table d'inventaire `annonces`
**When** une annonce y est enregistrée
**Then** elle porte un **créatif textuel**, un **ensemble de géolocalisations cibles**, un **ensemble de langues cibles** et une durée indicative — une même annonce s'adresse à plusieurs régions et plusieurs langues, sans duplication de ligne

**And Given** le créatif
**When** il est stocké
**Then** c'est un **texte, dans la langue où l'annonceur l'a écrit** (`spoken_language`), traduisible dans toutes les langues supportées — jamais un fichier audio pré-enregistré. C'est le même modèle que les tours de parole : un original, des traductions dérivées de lui

**And Given** un créatif textuel
**When** il est restitué à un participant
**Then** il est traduit et lu par l'interprète dans la langue de ce participant, exactement comme n'importe quel contenu du journal

**And Given** la durée d'une annonce
**When** elle est évaluée
**Then** elle est **indicative** et non contractuelle : un même texte traduit produit des durées différentes selon la langue, et c'est la durée réellement restituée qui compte dans le retard de l'interprète

**And Given** un annonceur exigeant une formulation exacte dans une langue donnée (contrainte de marque ou d'ordre légal)
**When** l'annonce est enregistrée
**Then** un texte de substitution peut être fourni **pour cette langue seulement**, les autres continuant d'être traduites depuis le créatif canonique

**And Given** un texte de substitution existe pour la langue d'un participant
**When** l'annonce lui est restituée
**Then** il est lu **mot pour mot**, sans traduction, sans reformulation et sans adaptation — c'est précisément ce que la substitution garantit

**And Given** un texte de substitution
**When** il est lu
**Then** aucun traitement d'interprétation ne s'y applique — ni nettoyage de disfluences (FR60), ni condensation (FR53), ni raccourcissement pour cause de retard

**And Given** l'ensemble des langues cibles
**When** il est interprété
**Then** il désigne les **langues parlées par les humains** à qui l'annonce sera lue — c'est un critère de ciblage, au même titre que la géolocalisation, et non une propriété du contenu

**And Given** un participant en Base ou en Mode A
**When** son interprète puise dans la table
**Then** il sélectionne une annonce dont l'ensemble des géolocalisations contient la sienne **et** dont l'ensemble des langues contient sa langue détectée

**And Given** une annonce sélectionnée
**When** elle est restituée
**Then** l'interprète la lit dans la langue de son participant, avec la voix de son propre palier — naturelle en Mode A, synthétique en Base

**And Given** la table `diffusions`
**When** une annonce est lue à un participant
**Then** la diffusion y est enregistrée (participant, annonce, horodatage) — ce qui permet de ne pas la rejouer, de faire respecter les fréquences et d'alimenter NFR4

**And Given** un participant a déjà entendu toutes les annonces correspondant à son ciblage
**When** son interprète puise à nouveau
**Then** les annonces sont **repassées**, la plus anciennement entendue en premier — l'inventaire ne s'épuise jamais et le silence publicitaire n'est jamais une issue

**And Given** un inventaire réduit et un Salon long
**When** les annonces sont repassées
**Then** la fréquence de diffusion reste celle du palier (FR33) — le cycle recommence, il ne s'accélère ni ne ralentit

**And Given** aucune annonce ne correspond au segment
**When** la sélection échoue
**Then** une annonce générique est servie, plutôt qu'un silence ou une erreur

**And Given** le modèle de diffusion
**When** il est implémenté
**Then** il fonctionne en **lecture à la demande** par l'interprète — il n'existe aucune file d'annonces poussée vers les participants

### Story 9.3: Insertion d'Annonces entre Messages

> ⚠️ **PARTIELLEMENT HÉRITÉ.** La diffusion existe : `POST /{salon_id}/ad` réserve, `POST /{salon_id}/ad/delivered` confirme, et `ad_broadcasts.delivered_at` distingue **réservé** de **réellement entendu** — *« charging an advertiser for a sentence nobody heard is the one outcome this must not produce »*.
> **Ce qui manque :** la règle de **placement** — entre deux messages, jamais au milieu d'une pensée découpée — et le rattrapage du retard après lecture.

As a participant,
I want que les annonces ne coupent jamais une pensée,
So that la conversation reste intelligible. (FR39)

**Acceptance Criteria:**

**Given** le moment de diffusion est venu pour un participant
**When** son interprète cherche un emplacement
**Then** il puise une annonce dans la table d'inventaire et l'insère entre deux messages de participants distincts

**And Given** une intervention découpée est en cours
**When** le moment de diffusion arrive
**Then** l'interprète attend la fin de l'intervention avant de puiser, sauf si le participant dépasse `plafond_monologue`

**And Given** les annonces de plusieurs participants
**When** elles sont lues
**Then** chaque interprète puise et lit à son propre rythme, sans aucune synchronisation entre les rooms

**And Given** une annonce vient d'être lue
**When** la conversation reprend
**Then** l'interprète rattrape le retard accumulé, en condensant si `seuil_condensation` est dépassé

### Story 9.4: Fréquence Différenciée entre Base et Mode A

As a exploitant,
I want moduler la charge publicitaire selon le palier,
So that la montée en gamme ait une valeur perceptible. (FR33)

**Acceptance Criteria:**

**Given** un participant en mode Base
**When** le Salon se déroule
**Then** il reçoit une annonce selon `frequence_annonces_base` (1 / 5 min)

**And Given** un participant en Mode A
**When** le Salon se déroule
**Then** il reçoit une annonce selon `frequence_annonces_mode_a` (1 / 10 min)

**And Given** un participant en Mode B, en Mode C, ou couvert par « l'hôte paie tout »
**When** le Salon se déroule
**Then** il ne reçoit aucune annonce

**And Given** un participant en Mode C
**When** son interprète est instancié
**Then** il utilise `modele_mode_c` (`grok-voice-think-fast-2.0`), là où les Modes A et B utilisent `grok-voice-think-fast-1.0` — le modèle est un paramètre d'adaptateur par palier, jamais une constante du produit (NFR6)

**And Given** les deux fréquences
**When** elles sont modifiées
**Then** elles sont persistées et ajustables indépendamment (FR54)

**And Given** que lire une annonce occupe l'interprète et fait avancer son curseur moins vite
**When** on compare les paliers à charge de conversation égale
**Then** un participant sans annonces accumule mécaniquement moins de retard qu'un participant en Mode A, lui-même moins qu'un participant en Base — il condense donc moins souvent (FR53) et sature plus rarement (FR49)

**And Given** cette conséquence
**When** elle est mesurée
**Then** le taux de condensation et le nombre de saturations sont instrumentés **par palier**, afin de vérifier que le mode Base reste utilisable et non simplement dégradé (NFR4)

## Epic 10: Inscription Légère & Accès Sans Installation

Toute personne invitée rejoint un Salon depuis son navigateur en quelques secondes avec un courriel ou un téléphone, sans installer d'application, dans la limite du plafond de participants.

### Story 10.1: Inscription par Courriel ou Téléphone

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** OTP par courriel via SES (`services/otp.py`, `routers/auth.py`), `users.email` unique et indexé, `users.phone_number` optionnel et unique. `invitation_service.link_prior_invitations` rattache même les participations antérieures d'un invité qui s'inscrit ensuite.
>
> **Ce qui reste :** le registre des identifiants brûlés et le crédit de bienvenue — traités en Story 8.2.

As a personne invitée,
I want m'inscrire en quelques secondes,
So that je rejoigne vite sans installer d'application. (FR51)

**Acceptance Criteria:**

**Given** une personne rejoint pour la première fois
**When** elle s'inscrit
**Then** elle fournit une adresse courriel, un numéro de téléphone, ou les deux

**And Given** l'identifiant fourni
**When** l'inscription est validée
**Then** il devient la clé du quota de 10 minutes à vie et empêche sa réinitialisation par recréation de Salon

**And Given** une personne déjà inscrite revient
**When** elle rejoint un nouveau Salon
**Then** son quota résiduel est retrouvé, quel que soit son rôle

**And Given** l'ancienne notion d'invité anonyme
**When** une personne rejoint
**Then** plus aucun accès sans identifiant n'est possible (rend FR27 sans objet)

### Story 10.8: Droit d'Accès et d'Effacement

As a personne dont les conversations sont conservées un an,
I want pouvoir obtenir mes données et demander leur effacement,
So that la conservation reste sous mon contrôle. (FR70)

**Acceptance Criteria:**

**Given** un utilisateur authentifié
**When** il demande une copie des données le concernant depuis l'interface web ou mobile
**Then** il obtient ses données de compte, ses soldes, l'historique de ses recharges, et **ses propres paroles** telles qu'inscrites aux journaux des Salons auxquels il a participé, dans un format lisible et exportable

**And Given** une demande d'accès ou d'effacement
**When** elle est reçue
**Then** l'identité du demandeur est **vérifiée** par l'une des voies de FR65 avant toute exécution — une demande d'effacement est aussi une arme si elle n'est pas vérifiée

**And Given** une demande vérifiée
**When** elle est traitée
**Then** elle l'est dans un **délai borné**, et le demandeur est informé de son aboutissement

**And Given** une demande d'effacement
**When** elle porte sur les journaux de Salons
**Then** seules **les paroles du demandeur** sont effacées : un journal est un enregistrement **conjoint**, et les paroles des autres participants ne lui appartiennent pas

**And Given** l'effacement des paroles d'un participant dans un journal
**When** il est exécuté
**Then** sa présence dans la conversation est **pseudonymisée** plutôt que supprimée — les échanges des autres restent intelligibles sans que le demandeur y soit identifiable

**And Given** les écritures comptables de FR67 et FR68 et le flux d'événements de NFR7
**When** un effacement est demandé
**Then** ils sont **pseudonymisés et conservés**, non supprimés : ils relèvent d'obligations comptables, et ils ne contiennent aucun contenu de conversation

**And Given** le registre des identifiants brûlés
**When** un effacement est exécuté
**Then** l'identifiant y est conservé sous forme de **condensat à sens unique** — le registre continue de faire son office sans détenir de donnée personnelle en clair, et l'effacement **ne rétablit jamais** l'éligibilité au crédit de bienvenue

**And Given** un effacement exécuté
**When** des sauvegardes antérieures existent
**Then** l'effacement leur est **réappliqué à toute restauration** — une donnée effacée ne doit jamais reparaître par le retour d'une sauvegarde

**And Given** un utilisateur dont le `solde_paye` est positif
**When** il demande l'effacement de son compte
**Then** le remboursement de ce solde lui est proposé avant exécution — effacer un compte ne doit jamais faire disparaître l'argent qu'il détenait

**And Given** un effacement exécuté
**When** il est enregistré
**Then** il est journalisé — demandeur, date, périmètre — constituant la preuve du traitement de la demande

### Story 10.7: Nom d'Utilisateur et Mot de Passe

As a utilisateur,
I want un nom d'utilisateur et un mot de passe,
So that je puisse accéder à mon compte même si je n'ai plus accès à mon courriel ni à mon téléphone. (FR65)

**Acceptance Criteria:**

**Given** une personne s'inscrit
**When** elle complète son inscription
**Then** elle choisit un **nom d'utilisateur unique** et un **mot de passe**, en plus de son ou ses identifiants

**And Given** un nom d'utilisateur déjà pris
**When** il est soumis
**Then** il est refusé avec un message explicite, la personne pouvant en proposer un autre

**And Given** un utilisateur possédant nom d'utilisateur et mot de passe
**When** il se connecte
**Then** cette voie fonctionne **sans exiger de code à usage unique** — l'authentification par identifiant reste disponible en parallèle, aucune ne remplace l'autre

**And Given** un utilisateur ayant perdu l'accès à tous ses identifiants
**When** il se connecte par nom d'utilisateur et mot de passe
**Then** il retrouve son compte, son `solde_paye` et son `solde_offert` intacts, puis peut modifier ses identifiants selon FR64

**And Given** un mot de passe oublié **et** aucun identifiant joignable
**When** un **remboursement** est demandé
**Then** la vérification par le **moyen de paiement Stripe enregistré** est recevable et permet de restituer le `solde_paye`

**And Given** une vérification par carte enregistrée
**When** elle est conduite
**Then** elle exige **plusieurs éléments concordants** — quatre derniers chiffres, date d'expiration, et le montant ou la date d'une transaction récente — jamais les seuls quatre derniers chiffres, qui se devinent en dix mille essais et figurent souvent sur des reçus

**And Given** des tentatives de vérification répétées
**When** elles échouent
**Then** elles sont limitées en nombre et journalisées — une voie de récupération est aussi une voie d'attaque

**And Given** une vérification par carte réussie
**When** elle aboutit
**Then** elle ouvre le **remboursement du `solde_paye`**, et non l'accès au compte : restituer de l'argent à son payeur légitime et rendre l'accès à une conversation sont deux décisions de nature différente

**And Given** un remboursement obtenu par cette voie
**When** il est exécuté
**Then** le `solde_offert` n'est pas remboursé, conformément à FR51, et le compte reste inaccessible tant qu'aucune autre voie d'authentification n'est rétablie

**And Given** les mots de passe stockés
**When** ils le sont
**Then** ils le sont sous forme de condensat salé, jamais en clair ni de façon réversible

### Story 10.6: Modification d'un Identifiant avec Ancre de Continuité

As a utilisateur,
I want changer mon courriel ou mon numéro sans perdre mon compte,
So that je reste joignable quand ma vie change, sans repartir de zéro. (FR64)

**Acceptance Criteria:**

**Given** un utilisateur disposant des deux identifiants
**When** il modifie son courriel depuis l'interface web ou mobile
**Then** son numéro de téléphone est conservé comme **ancre de continuité** et le changement est accepté

**And Given** le même utilisateur
**When** il modifie son numéro de téléphone
**Then** son courriel sert d'ancre et le changement est accepté

**And Given** une demande de modification des **deux** identifiants à la fois
**When** elle est soumise
**Then** elle est refusée — sans ancre conservée, plus rien ne rattache le compte à la personne d'origine

**And Given** un utilisateur ne disposant que d'un seul identifiant
**When** il veut le modifier
**Then** il doit d'abord **ajouter le second**, qui deviendra l'ancre — un compte à identifiant unique ne peut pas changer cet identifiant

**And Given** un nouvel identifiant soumis
**When** il est enregistré
**Then** il est **vérifié par code à usage unique**, comme à l'inscription, avant de prendre effet

**And Given** un nouvel identifiant appartenant déjà à un autre compte actif
**When** il est soumis
**Then** la modification est refusée avec un message explicite

**And Given** un nouvel identifiant figurant au registre des identifiants brûlés mais rattaché à aucun compte actif
**When** il est soumis
**Then** la modification est **acceptée** — le registre bloque l'attribution d'un cadeau, jamais l'usage d'un identifiant

**And Given** une modification acceptée
**When** elle prend effet
**Then** le nouvel identifiant est à son tour inscrit au registre des identifiants brûlés

**And Given** une modification acceptée
**When** les soldes sont évalués
**Then** `solde_offert` **conserve son montant courant** — il n'est ni réattribué, ni complété, ni remis à 5 USD ; `solde_paye` et `total_cumulatif` sont également inchangés

**And Given** un utilisateur ayant successivement changé ses deux identifiants, l'un après l'autre
**When** son historique est évalué
**Then** la chaîne de continuité reste intacte à chaque étape et aucun nouveau cadeau n'est jamais accordé

### Story 10.2: Plafond de Participants Configurable

> ✅ **DÉJÀ LIVRÉ PAR SALON.** `livekit_room_max_participants` est passé à `CreateRoomRequest` dans `services/livekit_service.py` — LiveKit refuse la jonction au-delà.
>
> **Ce qui reste :** déplacer le réglage des variables d'environnement vers la configuration persistée de la Story 7.1, et l'exposer à l'hôte à la création.

As a hôte,
I want fixer le nombre maximal de participants,
So that mon Salon reste à la taille voulue. (FR43)

**Acceptance Criteria:**

**Given** un hôte crée un Salon
**When** il définit le plafond
**Then** la valeur est bornée par `plafond_participants` (3 initialement)

**And Given** un Salon a atteint son plafond
**When** une personne supplémentaire tente de rejoindre
**Then** la jonction est refusée avec un message clair (remplace FR2)

**And Given** `plafond_participants` est modifié en configuration
**When** de nouveaux Salons sont créés
**Then** le nouveau plafond s'applique sans redéploiement ni modification de code

**And Given** le code de l'orchestrateur
**When** il traite les participants
**Then** il ne contient aucune hypothèse codée en dur sur leur nombre — construire pour N, configurer à 3

### Story 10.3: Liens de Jonction à Usage Unique par Invité

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `invitations.join_token` est unique **par invitation**, avec `expires_at` et un `status` qui passe à accepté. Un lien vaut donc pour une personne et une seule fois. `services/invitation_service.py` porte la logique.

As a hôte,
I want un lien distinct par invité,
So that chacun ait son propre accès traçable. (FR47)

**Acceptance Criteria:**

**Given** un hôte invite plusieurs personnes
**When** les invitations partent
**Then** un lien à usage unique distinct est généré pour chacune (étend FR5)

**And Given** un lien a déjà été utilisé
**When** quelqu'un tente de le réutiliser
**Then** l'accès est refusé

**And Given** un lien n'a jamais été utilisé
**When** le Salon se termine
**Then** le lien devient inopérant

### Story 10.4: Jonction Web Sans Installation

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `routers/guest_web.py` sert la page de jonction ; l'invité rejoint depuis son navigateur sans rien installer.
>
> **Ce qui reste :** l'inscription légère remplace l'accès anonyme, et l'écran de jonction gagne les trois options de la Story 8.4.

As a personne invitée,
I want rejoindre depuis mon navigateur,
So that je participe sans rien télécharger. (FR4)

**Acceptance Criteria:**

**Given** une personne clique son lien de jonction
**When** la page se charge sur mobile ou desktop
**Then** elle affiche le badge « Sans Installation », s'adapte aux deux formats et respecte le contraste WCAG AA (UX-DR5, UX-DR7, UX-DR8)

**And Given** la personne s'inscrit et choisit son mode
**When** elle valide
**Then** sa room est provisionnée et elle entre dans le Salon depuis le navigateur, sans application native

**And Given** le Salon est complet ou déjà terminé
**When** elle tente de rejoindre
**Then** elle reçoit un message vocal et visuel expliquant le refus, plutôt qu'un échec silencieux (NFR3)

### Story 10.5: Invitation Vocale d'un Numéro de Téléphone

> ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `invitations.phone_pin` à six chiffres, avec un index unique **partiel** sur les invitations en attente (`uq_invitations_phone_pin_pending`) : deux invitations ouvertes ne peuvent jamais partager un code, et le code redevient réutilisable une fois l'invitation close. LiveKit collecte les chiffres au clavier et place l'appelant dans la bonne room. `services/sms_service.py` porte la livraison.
>
> Le commentaire du modèle explique pourquoi le code est **par invitation** et non par Salon : un code partagé laisserait l'appelant anonyme, et `salon_events` exige une identité.
>
> **Ce qui reste :** la confirmation vocale du numéro reconnu, le choix du palier par l'hôte, et le supplément de 7,50 USD/h.

As a hôte,
I want inviter un numéro de téléphone à voix haute,
So that quelqu'un puisse participer sans application, sans navigateur et sans compte. (FR57)

**Acceptance Criteria:**

**Given** un hôte dans un Salon actif
**When** il prononce une invitation contenant un numéro de téléphone
**Then** l'agent lui répète le numéro reconnu et attend une confirmation vocale explicite avant de composer

**And Given** le numéro reconnu est erroné
**When** l'hôte infirme
**Then** aucun appel n'est composé et l'agent redemande poliment

**And Given** l'hôte prononce l'invitation
**When** il précise le palier dans la même commande vocale (« invite le 514… en Mode C »)
**Then** ce palier est appliqué au participant téléphonique ; à défaut, `mode_telephonique_par_defaut` (Mode B) s'applique

**And Given** les paliers offerts par téléphone
**When** l'hôte en demande un
**Then** seuls **A, B et C** sont acceptés — le mode Base n'est pas offert par téléphone, l'hôte payant de toute façon le supplément et le coût de l'interprète sans contrepartie

**And Given** l'hôte confirme le numéro
**When** l'appel s'apprête à être composé
**Then** le système vérifie qu'un moyen de paiement valide est enregistré — **indépendamment de l'option « l'hôte paie tout » de FR42**, qui n'a pas à être active : un participant téléphonique est toujours à la charge de l'hôte

**And Given** un participant téléphonique en Salon
**When** son coût est calculé
**Then** l'hôte est facturé le tarif du palier choisi **plus** `supplement_telephonique` (1 USD/h), au prorata de la seconde

**And Given** le Salon a déjà atteint `plafond_participants`
**When** l'hôte tente d'inviter un numéro
**Then** l'appel est refusé et l'hôte en est informé vocalement

**And Given** l'appelé décroche
**When** la connexion s'établit
**Then** une room LiveKit SIP lui est provisionnée avec son propre interprète IA, exactement comme tout autre participant

**And Given** l'appelé vient de décrocher
**When** son interprète prend la parole
**Then** il se présente, nomme l'hôte qui l'invite, et explique en une phrase ce qui va se passer — l'appelé ne doit jamais se demander qui l'appelle

**And Given** l'appelé parle
**When** ses premiers mots sont captés
**Then** sa langue est détectée automatiquement et la conversation se déroule dans sa langue, sans aucune configuration de sa part (FR12, FR14)

**And Given** un participant téléphonique
**When** son palier est appliqué
**Then** il en bénéficie sans inscription, sans choix de sa part et **sans consommer son propre quota gratuit** — il n'a rien décidé, il ne doit rien dépenser

**And Given** un participant téléphonique
**When** le coût est calculé
**Then** l'interprète, les minutes SIP, la terminaison PSTN et le supplément sont intégralement portés par l'hôte, et alimentent son `budget_courant` au titre de FR56

**And Given** l'appelé ne décroche pas, raccroche ou refuse
**When** l'appel se termine
**Then** l'hôte en est informé vocalement et le Salon se poursuit normalement

**And Given** un participant téléphonique en Salon
**When** il raccroche
**Then** il quitte le Salon proprement et sa room est libérée (FR25)

**And Given** un participant téléphonique
**When** du contenu visuel serait normalement présenté
**Then** aucun affichage n'est requis — l'expérience est intégralement vocale et FR13 ne s'applique pas à lui
