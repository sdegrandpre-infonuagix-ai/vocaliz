# Ralph Fix Plan

## Stories to Implement

### Inscription & Identité
> Goal: Un nouvel utilisateur peut créer un compte Salon en vérifiant son numéro de téléphone — condition préalable à toute utilisation du produit en tant qu'hôte.

- [x] Story 1.1: Initialisation des Projets
- [x] Story 1.2: Vérification Téléphone par OTP
- [x] Story 1.3: Écran d'Inscription
### Session de Discussion Vocale
> Goal: Un hôte inscrit peut créer une session à partir d'un document ou d'une actualité, inviter un ami ou contact par simple commande vocale, et vivre une conversation complète animée et traduite par l'agent xAI, jusqu'à la question de satisfaction de fin de session.

- [x] Story 2.1: Création de Session avec Document/URL
- [x] Story 2.2: Invitation Vocale d'un Ami ou Contact
- [x] Story 2.3: Ajout de Source en Cours de Session
- [x] Story 2.4: Lecture à Voix Haute et Facilitation Sans Lecture Préalable
  > As a participant
  > I want que l'agent lise et anime le contenu à voix haute
  > So that je peux discuter d'un document sans l'avoir lu au préalable.
  > AC: Given une session démarrée avec une source de contenu, When les participants rejoignent, Then l'agent lit le contenu à voix haute et pose des questions pour engager la discussion, And Given un participant n'a pas consulté le document au préalable, When il participe à la discussion, Then il peut suivre et contribuer normalement grâce à la lecture de l'agent
  > Spec: specs/planning-artifacts/epics.md#story-2-4
- [ ] Story 2.5: Contraste avec d'Autres Sources
  > As a participant
  > I want que l'agent introduise des informations contrastantes d'autres sources
  > So that la discussion gagne en profondeur.
  > AC: Given une discussion en cours sur un sujet donné, When l'agent identifie une occasion de contraste pertinent, Then il introduit l'information contrastante à voix haute, en citant sa source
  > Spec: specs/planning-artifacts/epics.md#story-2-5
- [ ] Story 2.6: Conversation Naturelle Sans Mot-Clé de Réveil
  > As a participant
  > I want parler naturellement sans mot-clé de réveil ni mécanisme formel de demande de parole
  > So that la conversation reste fluide comme entre humains.
  > AC: Given une session active, When un participant commence à parler, Then l'agent le comprend sans qu'un mot-clé de réveil soit prononcé, And Given deux participants parlent en alternance, When une pause naturelle survient, Then l'agent ou l'autre participant peut prendre la parole sans mécanisme explicite de demande
  > Spec: specs/planning-artifacts/epics.md#story-2-6
- [ ] Story 2.7: Ajustement Vocal de la Fréquence d'Intervention
  > As a participant
  > I want ajuster à voix haute la fréquence d'intervention de l'agent
  > So that je garde le contrôle du rythme de la conversation.
  > AC: Given une session avec des participants de même langue, When aucun ajustement n'est demandé, Then l'agent intervient au maximum une fois par minute, de façon succincte, And Given un participant dit "parle moins souvent" ou "interviens plus", When la demande est reçue, Then l'agent ajuste sa fréquence d'intervention en conséquence pour le reste de la session
  > Spec: specs/planning-artifacts/epics.md#story-2-7
- [ ] Story 2.8: Détection de Langue et Expression Multilingue
  > As a participant
  > I want m'exprimer dans ma propre langue sans configuration
  > So that la barrière linguistique ne limite jamais la conversation.
  > AC: Given un participant rejoint une session, When il commence à parler, Then le système détecte automatiquement sa langue sans sélection manuelle, And Given la langue est détectée, When le participant continue de parler, Then il peut s'exprimer entièrement dans cette langue tout au long de la session
  > Spec: specs/planning-artifacts/epics.md#story-2-8
- [ ] Story 2.9: Affichage Visuel dans la Langue Détectée
  > As a utilisateur
  > I want que les écrans de l'application s'affichent dans ma langue vocale détectée
  > So that je n'aie jamais besoin de configurer manuellement une langue d'interface.
  > AC: Given la langue vocale d'un utilisateur est détectée, When un écran de l'application s'affiche, Then le texte visuel est présenté dans cette langue
  > Spec: specs/planning-artifacts/epics.md#story-2-9
- [ ] Story 2.10: Traduction Simultanée en Direct Sans Écho
  > As a participant
  > I want entendre une traduction en direct dans ma langue pendant que l'autre continue de parler
  > So that la conversation reste fluide malgré la barrière linguistique.
  > AC: Given deux participants parlant des langues différentes, When l'un d'eux parle, Then son discours est traduit et lu à voix haute au destinataire dans sa propre langue, And Given la traduction est en cours de lecture pour un destinataire, When l'interlocuteur d'origine continue de parler, Then la traduction ne l'interrompt pas et le microphone du destinataire est temporairement coupé pour éviter tout écho sur le flux partagé
  > Spec: specs/planning-artifacts/epics.md#story-2-10
- [ ] Story 2.11: Sortie Vocale de Session
  > As a participant
  > I want quitter une session en disant "Je quitte le Salon" dans ma propre langue
  > So that je peux terminer proprement sans manipuler l'écran.
  > AC: Given une session active, When un participant prononce la commande de sortie dans sa langue, Then la session se termine pour ce participant
  > Spec: specs/planning-artifacts/epics.md#story-2-11
- [ ] Story 2.12: Question de Satisfaction de Fin de Session
  > As a participant
  > I want qu'on me demande vocalement si la conversation a été agréable
  > So that mon ressenti soit capturé sans effort.
  > AC: Given un participant vient de prononcer la commande de sortie, When la session se termine pour lui, Then l'agent lui pose immédiatement, à voix haute, la question "Est-ce que votre conversation dans Salon a été une belle expérience ?"
  > Spec: specs/planning-artifacts/epics.md#story-2-12
### Accès Invité Sans Installation
> Goal: Un contact téléphone sans l'application peut rejoindre une session Salon anonymement depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.

- [ ] Story 3.1: Jonction Web Anonyme via Lien à Usage Unique
  > As a contact téléphone invité sans l'application
  > I want rejoindre une session directement depuis mon navigateur
  > So that je peux participer sans créer de compte ni installer quoi que ce soit.
  > AC: Given un hôte invite un contact téléphone sans l'application Salon, When le contact reçoit le SMS et clique le lien, Then il rejoint la session anonymement depuis son navigateur, sans créer de compte, And Given un lien de session a déjà été utilisé une fois, When quelqu'un tente de le réutiliser, Then l'accès est refusé, And Given la page de jonction s'affiche, When elle se charge sur mobile ou desktop, Then elle affiche le badge "Sans Installation" et s'adapte correctement aux deux formats
  > Spec: specs/planning-artifacts/epics.md#story-3-1
- [ ] Story 3.2: Sortie de Session par Fermeture
  > As a invité anonyme
  > I want pouvoir simplement fermer mon navigateur pour quitter
  > So that je n'aie pas besoin de connaître une commande vocale spécifique.
  > AC: Given un invité anonyme dans une session active, When il ferme l'application ou l'onglet du navigateur, Then il quitte la session proprement
  > Spec: specs/planning-artifacts/epics.md#story-3-2
- [ ] Story 3.3: Question de Satisfaction pour Invité Anonyme
  > As a invité anonyme
  > I want répondre à la question de satisfaction sans avoir de compte
  > So that mon ressenti compte même sans inscription.
  > AC: Given un invité anonyme quitte une session, When l'agent pose la question de satisfaction, Then l'invité peut y répondre vocalement sans que la réponse soit liée à un profil persistant
  > Spec: specs/planning-artifacts/epics.md#story-3-3
- [ ] Story 3.4: SMS de Suivi avec Lien d'Installation
  > As a invité anonyme
  > I want recevoir un SMS avec un lien d'installation après ma session
  > So that je puisse facilement installer l'application si l'expérience m'a plu.
  > AC: Given un invité anonyme termine sa première session, When la session se termine, Then il reçoit automatiquement un SMS avec un lien d'installation de l'application
  > Spec: specs/planning-artifacts/epics.md#story-3-4
- [ ] Story 3.5: Conversion en Utilisateur Inscrit
  > As a invité anonyme ayant reçu le lien d'installation
  > I want installer l'application et continuer à utiliser Salon en tant qu'utilisateur inscrit
  > So that je conserve mon historique pour mes futures sessions.
  > AC: Given un invité anonyme a reçu le SMS d'installation, When il installe l'application et complète la vérification téléphone, Then il devient un utilisateur inscrit à part entière
  > Spec: specs/planning-artifacts/epics.md#story-3-5
### Essai Gratuit & Facturation
> Goal: Un hôte bénéficie d'une heure d'essai gratuite à vie, mesurée précisément, puis est facturé à l'heure via Stripe une fois cet essai épuisé — l'invité, lui, ne paie jamais.

- [ ] Story 4.1: Heure d'Essai Gratuite à Vie par Hôte
  > As a hôte
  > I want bénéficier d'une heure d'essai gratuite cumulée sur toutes mes sessions
  > So that je peux essayer Salon avant de payer.
  > AC: Given un hôte utilise Salon pour la première fois, When il démarre des sessions, Then son temps cumulé en tant qu'hôte est suivi contre un plafond d'une heure à vie, And Given un invité participe à une session, When le temps est comptabilisé, Then son temps à lui n'est jamais compté contre l'essai gratuit de qui que ce soit (FR23)
  > Spec: specs/planning-artifacts/epics.md#story-4-1
- [ ] Story 4.2: Métrage Précis du Temps de Conversation
  > As a système
  > I want comptabiliser le temps de conversation à la minute et à la seconde près
  > So that l'essai gratuit et la facturation soient exacts.
  > AC: Given une session active avec un hôte, When la conversation se déroule, Then le worker d'agent envoie un heartbeat de métrage toutes les 30 secondes à l'API, And Given une déconnexion brutale survient, When la session se termine de façon inattendue, Then le métrage déjà transmis via heartbeat n'est pas perdu
  > Spec: specs/planning-artifacts/epics.md#story-4-2
- [ ] Story 4.3: Ajout de Méthode de Paiement Stripe
  > As a hôte dont l'heure gratuite est épuisée
  > I want ajouter une méthode de paiement
  > So that je peux continuer à utiliser Salon en tant qu'hôte.
  > AC: Given un hôte a épuisé son heure d'essai gratuite, When il tente de démarrer une nouvelle session en tant qu'hôte, Then il doit ajouter une méthode de paiement via Stripe avant de continuer
  > Spec: specs/planning-artifacts/epics.md#story-4-3
- [ ] Story 4.4: Facturation à l'Heure Après l'Essai Gratuit
  > As a hôte avec une méthode de paiement enregistrée
  > I want être facturé au prorata de mon temps d'utilisation au-delà de l'essai gratuit
  > So that je paie seulement ce que j'utilise.
  > AC: Given un hôte a dépassé son heure gratuite et a une méthode de paiement, When il utilise Salon en tant qu'hôte, Then il est facturé 5 USD par heure, au prorata de la seconde, And Given un invité participe à une session facturée, When la facturation est calculée, Then l'invité n'est jamais facturé, peu importe la durée
  > Spec: specs/planning-artifacts/epics.md#story-4-4
### Historique & Reconnexion
> Goal: Un utilisateur inscrit peut consulter ses sessions passées et démarrer rapidement une nouvelle session avec un partenaire déjà connu.

- [ ] Story 5.1: Consultation de l'Historique de Sessions
  > As a utilisateur inscrit
  > I want consulter mes sessions passées et mes partenaires de discussion
  > So that je peux me souvenir de mes conversations précédentes.
  > AC: Given un utilisateur inscrit avec au moins une session passée, When il consulte son historique, Then il voit une liste simple de ses sessions passées et partenaires, sans fil de messages détaillé
  > Spec: specs/planning-artifacts/epics.md#story-5-1
- [ ] Story 5.2: Nouvelle Session avec un Partenaire Précédent
  > As a utilisateur inscrit
  > I want démarrer rapidement une nouvelle session avec un partenaire déjà connu
  > So that je n'aie pas à répéter le processus d'invitation complet.
  > AC: Given un utilisateur consulte son historique, When il sélectionne un partenaire précédent pour une nouvelle session, Then une nouvelle session démarre avec ce partenaire déjà identifié
  > Spec: specs/planning-artifacts/epics.md#story-5-2

## Completed

## Notes
- Follow TDD methodology (red-green-refactor)
- One story per Ralph loop iteration
- Update this file after completing each story
