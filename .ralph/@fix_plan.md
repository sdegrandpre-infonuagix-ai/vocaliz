# Ralph Fix Plan

## Stories to Implement

### Inscription & Identité
> Goal: Un nouvel utilisateur peut créer un compte Salon en vérifiant son adresse courriel — condition préalable à toute utilisation du produit en tant qu'hôte.

- [x] Story 1.1: Initialisation des Projets
- [x] Story 1.2: Vérification Courriel par OTP
- [x] Story 1.3: Écran d'Inscription
### Salon de Discussion Vocale
> Goal: Un hôte inscrit peut créer un Salon à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de Salon.

- [x] Story 2.1: Création de Salon avec Document/URL
- [x] Story 2.2: Invitation Vocale d'un Ami ou Contact
- [x] Story 2.3: Ajout de Source en Cours de Salon
- [x] Story 2.4: Lecture à Voix Haute et Facilitation Sans Lecture Préalable
- [x] Story 2.5: Contraste avec d'Autres Sources
- [x] Story 2.6: Conversation Naturelle Sans Mot-Clé de Réveil
- [x] Story 2.7: Ajustement Vocal de la Fréquence d'Intervention
- [x] Story 2.8: Détection de Langue et Expression Multilingue
- [x] Story 2.9: Affichage Visuel dans la Langue Détectée
- [x] Story 2.10: Traduction Simultanée en Direct Sans Écho
- [x] Story 2.11: Sortie Vocale de Salon
- [x] Story 2.12: Question de Satisfaction de Fin de Salon
### Accès Invité Sans Installation
> Goal: Un contact sans l'application peut rejoindre un Salon Salon depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup. > **⚠ Superseded par l'Epic 10 (2026-08-08).** Les stories 3.1 à 3.5 ci-dessous sont livrées et conservées comme trace de l'existant, mais la notion d'« invité anonyme » n'existe plus : FR51 impose désormais une inscription légère (courriel ou téléphone) à toute personne. La promesse retenue est « sans installation », pas « sans compte ». En cas de contradiction, l'Epic 10 fait autorité.

- [x] Story 3.1: Jonction Web Anonyme via Lien à Usage Unique
- [x] Story 3.2: Sortie de Salon par Fermeture
- [x] Story 3.3: Question de Satisfaction pour Invité Anonyme
- [x] Story 3.4: Courriel de Suivi avec Lien d'Installation
- [x] Story 3.5: Conversion en Utilisateur Inscrit
### Essai Gratuit & Facturation
> Goal: Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.

- [x] Story 4.1: Heure d'Essai Gratuite à Vie par Hôte
- [x] Story 4.2: Métrage Précis du Temps de Conversation
- [x] Story 4.3: Ajout de Méthode de Paiement Stripe
- [x] Story 4.4: Facturation à l'Heure Après l'Essai Gratuit
### Historique & Reconnexion
> Goal: Un utilisateur inscrit peut consulter ses Salons passés et démarrer rapidement un nouveau Salon avec un partenaire déjà connu.

- [x] Story 5.1: Consultation de l'Historique de Salons
- [x] Story 5.2: Nouveau Salon avec un Partenaire Précédent
### Socle Conversationnel Multi-Rooms
> Goal: Une conversation Salon se déroule à travers un orchestrateur central et un interprète dédié par participant : chacun parle sa langue dans sa propre room et reçoit celle des autres, sans audio partagé et donc sans écho possible.

- [x] Story 6.1: Initialisation du Composant Orchestrateur
- [x] Story 6.2: Port Interprète et Adaptateur Speech-to-Speech
- [x] Story 6.3: Orchestrateur de Salon, Journal et Curseurs
- [x] Story 6.4: Une Room LiveKit par Participant
- [x] Story 6.5: Découpage des Interventions à 500 Caractères
- [x] Story 6.6: Restitution Premier Arrivé Premier Servi
- [x] Story 6.7: Adaptateur Base en Transcription et Synthèse
- [x] Story 6.8: Coupure de Micro par l'Hôte
- [x] Story 6.9: Présentation des Participants et de Leur Langue
- [x] Story 6.10: Accès à l'Historique pour un Arrivant Tardif
- [x] Story 6.11: Nettoyage des Disfluences et Métadonnée de Pause
- [x] Story 6.12: Chiffrement au Repos
- [x] Story 6.13: Vidéo Muette en Direct
- [x] Story 6.14: Sous-Titres Traduits en Direct
- [x] Story 6.15: Voyant de Parole par Paire
- [x] Story 6.16: Mode Conduite — Écran Noir, Vocal Uniquement
- [x] Story 6.17: Activation Automatique du Mode Conduite
- [x] Story 7.1: Configuration Persistée des Paramètres du Salon
- [x] Story 7.2: Condensation par l'Interprète en Retard
- [x] Story 7.3: Signal de Saturation et Blocage d'Entrée
- [x] Story 7.4: Plafond de Monologue
- [x] Story 7.5: Interprète Simulé et Infrastructure de Test de Charge
- [x] Story 7.6: Ordre d'Émission de la Méta-Parole
### Modes d'Expérience & Paliers Tarifaires
> Goal: Chaque participant choisit son propre mode parmi quatre paliers payants, dispose d'un crédit de bienvenue de 5 USD, est prévenu avant que son solde ne s'épuise, et n'est facturé que pour son propre mode.

- [x] Story 8.1: Flux d'Événements Comptables
- [x] Story 8.2: Crédit Offert de 5 USD à Vie
- [x] Story 8.3: Configuration des Trois Options par l'Hôte à la Création
- [x] Story 8.4: Configuration des Trois Options par le Participant à la Jonction
- [x] Story 8.5: Salon Mixte et Persistance du Mode
- [x] Story 8.6: Facturation par Mode et Option « L'Hôte Paie Tout »
- [x] Story 8.7: Solde Prépayé et Recharge Stripe
- [x] Story 8.8: Vérification Périodique de la Couverture du Solde
- [x] Story 8.9: Alerte de Solde Bas et Fin de Salon
- [x] Story 8.10: Octroi Manuel d'un Second Crédit
- [x] Story 8.11: Journal Comptable des Crédits Offerts
- [x] Story 8.12: Journal Comptable du Solde Payé
- [x] Story 8.13: Rabais de Recharge par Navigateur
### Régie d'Annonces Géolocalisées
> Goal: Les participants en Base et en Mode A entendent des annonces pertinentes pour leur région, dans leur langue, glissées entre deux messages et jamais au milieu d'une pensée.

- [x] Story 9.1: Consentement de Géolocalisation à l'Inscription
- [x] Story 9.2: Adaptation de l'Échange Publicitaire Hérité
- [x] Story 9.3: Insertion d'Annonces entre Messages
- [x] Story 9.4: Fréquence Différenciée entre Base et Mode A
### Inscription Légère & Accès Sans Installation
> Goal: Toute personne invitée rejoint un Salon depuis son navigateur en quelques secondes avec un courriel ou un téléphone, sans installer d'application, dans la limite du plafond de participants.

- [x] Story 10.1: Inscription par Courriel ou Téléphone
- [x] Story 10.2: Plafond de Participants Configurable
- [x] Story 10.3: Liens de Jonction à Usage Unique par Invité
  > > ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `invitations.join_token` est unique **par invitation**, avec `expires_at` et un `status` qui passe à accepté.
  > Un lien vaut donc pour une personne et une seule fois.
  > `services/invitation_service.py` porte la logique.
  > AC: Given un hôte invite plusieurs personnes, When les invitations partent, Then un lien à usage unique distinct est généré pour chacune (étend FR5), And Given un lien a déjà été utilisé, When quelqu'un tente de le réutiliser, Then l'accès est refusé, And Given un lien n'a jamais été utilisé, When le Salon se termine, Then le lien devient inopérant
  > Spec: specs/planning-artifacts/epics.md#story-10-3
- [ ] Story 10.4: Jonction Web Sans Installation
  > > ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `routers/guest_web.py` sert la page de jonction ; l'invité rejoint depuis son navigateur sans rien installer.
  > > > **Ce qui reste :** l'inscription légère remplace l'accès anonyme, et l'écran de jonction gagne les trois options de la Story 8.4.
  > As a personne invitée
  > AC: Given une personne clique son lien de jonction, When la page se charge sur mobile ou desktop, Then elle affiche le badge « Sans Installation », s'adapte aux deux formats et respecte le contraste WCAG AA (UX-DR5, UX-DR7, UX-DR8), And Given la personne s'inscrit et choisit son mode, When elle valide, Then sa room est provisionnée et elle entre dans le Salon depuis le navigateur, sans application native, And Given le Salon est complet ou déjà terminé, When elle tente de rejoindre, Then elle reçoit un message vocal et visuel expliquant le refus, plutôt qu'un échec silencieux (NFR3)
  > Spec: specs/planning-artifacts/epics.md#story-10-4
- [ ] Story 10.5: Invitation Vocale d'un Numéro de Téléphone
  > > ✅ **DÉJÀ LIVRÉ PAR SALON — ne pas reconstruire.** `invitations.phone_pin` à six chiffres, avec un index unique **partiel** sur les invitations en attente (`uq_invitations_phone_pin_pending`) : deux invitations ouvertes ne peuvent jamais partager un code, et le code redevient réutilisable une fois l'invitation close.
  > LiveKit collecte les chiffres au clavier et place l'appelant dans la bonne room.
  > `services/sms_service.py` porte la livraison.
  > AC: Given un hôte dans un Salon actif, When il prononce une invitation contenant un numéro de téléphone, Then l'agent lui répète le numéro reconnu et attend une confirmation vocale explicite avant de composer, And Given le numéro reconnu est erroné, When l'hôte infirme, Then aucun appel n'est composé et l'agent redemande poliment, And Given l'hôte prononce l'invitation, When il précise le palier dans la même commande vocale (« invite le 514… en Mode C »), Then ce palier est appliqué au participant téléphonique ; à défaut, `mode_telephonique_par_defaut` (Mode B) s'applique, And Given les paliers offerts par téléphone, When l'hôte en demande un, Then seuls A, B et C sont acceptés — le mode Base n'est pas offert par téléphone, l'hôte payant de toute façon le supplément et le coût de l'interprète sans contrepartie, And Given l'hôte confirme le numéro, When l'appel s'apprête à être composé, Then le système vérifie qu'un moyen de paiement valide est enregistré — indépendamment de l'option « l'hôte paie tout » de FR42, qui n'a pas à être active : un participant téléphonique est toujours à la charge de l'hôte, And Given un participant téléphonique en Salon, When son coût est calculé, Then l'hôte est facturé le tarif du palier choisi plus `supplement_telephonique` (1 USD/h), au prorata de la seconde, And Given le Salon a déjà atteint `plafond_participants`, When l'hôte tente d'inviter un numéro, Then l'appel est refusé et l'hôte en est informé vocalement, And Given l'appelé décroche, When la connexion s'établit, Then une room LiveKit SIP lui est provisionnée avec son propre interprète IA, exactement comme tout autre participant, And Given l'appelé vient de décrocher, When son interprète prend la parole, Then il se présente, nomme l'hôte qui l'invite, et explique en une phrase ce qui va se passer — l'appelé ne doit jamais se demander qui l'appelle, And Given l'appelé parle, When ses premiers mots sont captés, Then sa langue est détectée automatiquement et la conversation se déroule dans sa langue, sans aucune configuration de sa part (FR12, FR14), And Given un participant téléphonique, When son palier est appliqué, Then il en bénéficie sans inscription, sans choix de sa part et sans consommer son propre quota gratuit — il n'a rien décidé, il ne doit rien dépenser, And Given un participant téléphonique, When le coût est calculé, Then l'interprète, les minutes SIP, la terminaison PSTN et le supplément sont intégralement portés par l'hôte, et alimentent son `budget_courant` au titre de FR56, And Given l'appelé ne décroche pas, raccroche ou refuse, When l'appel se termine, Then l'hôte en est informé vocalement et le Salon se poursuit normalement, And Given un participant téléphonique en Salon, When il raccroche, Then il quitte le Salon proprement et sa room est libérée (FR25), And Given un participant téléphonique, When du contenu visuel serait normalement présenté, Then aucun affichage n'est requis — l'expérience est intégralement vocale et FR13 ne s'applique pas à lui
  > Spec: specs/planning-artifacts/epics.md#story-10-5
- [ ] Story 10.6: Modification d'un Identifiant avec Ancre de Continuité
  > As a utilisateur
  > I want changer mon courriel ou mon numéro sans perdre mon compte
  > So that je reste joignable quand ma vie change, sans repartir de zéro.
  > AC: Given un utilisateur disposant des deux identifiants, When il modifie son courriel depuis l'interface web ou mobile, Then son numéro de téléphone est conservé comme ancre de continuité et le changement est accepté, And Given le même utilisateur, When il modifie son numéro de téléphone, Then son courriel sert d'ancre et le changement est accepté, And Given une demande de modification des deux identifiants à la fois, When elle est soumise, Then elle est refusée — sans ancre conservée, plus rien ne rattache le compte à la personne d'origine, And Given un utilisateur ne disposant que d'un seul identifiant, When il veut le modifier, Then il doit d'abord ajouter le second, qui deviendra l'ancre — un compte à identifiant unique ne peut pas changer cet identifiant, And Given un nouvel identifiant soumis, When il est enregistré, Then il est vérifié par code à usage unique, comme à l'inscription, avant de prendre effet, And Given un nouvel identifiant appartenant déjà à un autre compte actif, When il est soumis, Then la modification est refusée avec un message explicite, And Given un nouvel identifiant figurant au registre des identifiants brûlés mais rattaché à aucun compte actif, When il est soumis, Then la modification est acceptée — le registre bloque l'attribution d'un cadeau, jamais l'usage d'un identifiant, And Given une modification acceptée, When elle prend effet, Then le nouvel identifiant est à son tour inscrit au registre des identifiants brûlés, And Given une modification acceptée, When les soldes sont évalués, Then `solde_offert` conserve son montant courant — il n'est ni réattribué, ni complété, ni remis à 5 USD ; `solde_paye` et `total_cumulatif` sont également inchangés, And Given un utilisateur ayant successivement changé ses deux identifiants, l'un après l'autre, When son historique est évalué, Then la chaîne de continuité reste intacte à chaque étape et aucun nouveau cadeau n'est jamais accordé
  > Spec: specs/planning-artifacts/epics.md#story-10-6
- [ ] Story 10.7: Nom d'Utilisateur et Mot de Passe
  > As a utilisateur
  > I want un nom d'utilisateur et un mot de passe
  > So that je puisse accéder à mon compte même si je n'ai plus accès à mon courriel ni à mon téléphone.
  > AC: Given une personne s'inscrit, When elle complète son inscription, Then elle choisit un nom d'utilisateur unique et un mot de passe, en plus de son ou ses identifiants, And Given un nom d'utilisateur déjà pris, When il est soumis, Then il est refusé avec un message explicite, la personne pouvant en proposer un autre, And Given un utilisateur possédant nom d'utilisateur et mot de passe, When il se connecte, Then cette voie fonctionne sans exiger de code à usage unique — l'authentification par identifiant reste disponible en parallèle, aucune ne remplace l'autre, And Given un utilisateur ayant perdu l'accès à tous ses identifiants, When il se connecte par nom d'utilisateur et mot de passe, Then il retrouve son compte, son `solde_paye` et son `solde_offert` intacts, puis peut modifier ses identifiants selon FR64, And Given un mot de passe oublié et aucun identifiant joignable, When un remboursement est demandé, Then la vérification par le moyen de paiement Stripe enregistré est recevable et permet de restituer le `solde_paye`, And Given une vérification par carte enregistrée, When elle est conduite, Then elle exige plusieurs éléments concordants — quatre derniers chiffres, date d'expiration, et le montant ou la date d'une transaction récente — jamais les seuls quatre derniers chiffres, qui se devinent en dix mille essais et figurent souvent sur des reçus, And Given des tentatives de vérification répétées, When elles échouent, Then elles sont limitées en nombre et journalisées — une voie de récupération est aussi une voie d'attaque, And Given une vérification par carte réussie, When elle aboutit, Then elle ouvre le remboursement du `solde_paye`, et non l'accès au compte : restituer de l'argent à son payeur légitime et rendre l'accès à une conversation sont deux décisions de nature différente, And Given un remboursement obtenu par cette voie, When il est exécuté, Then le `solde_offert` n'est pas remboursé, conformément à FR51, et le compte reste inaccessible tant qu'aucune autre voie d'authentification n'est rétablie, And Given les mots de passe stockés, When ils le sont, Then ils le sont sous forme de condensat salé, jamais en clair ni de façon réversible
  > Spec: specs/planning-artifacts/epics.md#story-10-7
- [ ] Story 10.8: Droit d'Accès et d'Effacement
  > As a personne dont les conversations sont conservées un an
  > I want pouvoir obtenir mes données et demander leur effacement
  > So that la conservation reste sous mon contrôle.
  > AC: Given un utilisateur authentifié, When il demande une copie des données le concernant depuis l'interface web ou mobile, Then il obtient ses données de compte, ses soldes, l'historique de ses recharges, et ses propres paroles telles qu'inscrites aux journaux des Salons auxquels il a participé, dans un format lisible et exportable, And Given une demande d'accès ou d'effacement, When elle est reçue, Then l'identité du demandeur est vérifiée par l'une des voies de FR65 avant toute exécution — une demande d'effacement est aussi une arme si elle n'est pas vérifiée, And Given une demande vérifiée, When elle est traitée, Then elle l'est dans un délai borné, et le demandeur est informé de son aboutissement, And Given une demande d'effacement, When elle porte sur les journaux de Salons, Then seules les paroles du demandeur sont effacées : un journal est un enregistrement conjoint, et les paroles des autres participants ne lui appartiennent pas, And Given l'effacement des paroles d'un participant dans un journal, When il est exécuté, Then sa présence dans la conversation est pseudonymisée plutôt que supprimée — les échanges des autres restent intelligibles sans que le demandeur y soit identifiable, And Given les écritures comptables de FR67 et FR68 et le flux d'événements de NFR7, When un effacement est demandé, Then ils sont pseudonymisés et conservés, non supprimés : ils relèvent d'obligations comptables, et ils ne contiennent aucun contenu de conversation, And Given le registre des identifiants brûlés, When un effacement est exécuté, Then l'identifiant y est conservé sous forme de condensat à sens unique — le registre continue de faire son office sans détenir de donnée personnelle en clair, et l'effacement ne rétablit jamais l'éligibilité au crédit de bienvenue, And Given un effacement exécuté, When des sauvegardes antérieures existent, Then l'effacement leur est réappliqué à toute restauration — une donnée effacée ne doit jamais reparaître par le retour d'une sauvegarde, And Given un utilisateur dont le `solde_paye` est positif, When il demande l'effacement de son compte, Then le remboursement de ce solde lui est proposé avant exécution — effacer un compte ne doit jamais faire disparaître l'argent qu'il détenait, And Given un effacement exécuté, When il est enregistré, Then il est journalisé — demandeur, date, périmètre — constituant la preuve du traitement de la demande
  > Spec: specs/planning-artifacts/epics.md#story-10-8

## Completed

## Notes
- Follow TDD methodology (red-green-refactor)
- One story per Ralph loop iteration
- Update this file after completing each story
