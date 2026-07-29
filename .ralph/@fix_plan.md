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
- [x] Story 2.5: Contraste avec d'Autres Sources
- [x] Story 2.6: Conversation Naturelle Sans Mot-Clé de Réveil
- [x] Story 2.7: Ajustement Vocal de la Fréquence d'Intervention
- [x] Story 2.8: Détection de Langue et Expression Multilingue
- [x] Story 2.9: Affichage Visuel dans la Langue Détectée
- [x] Story 2.10: Traduction Simultanée en Direct Sans Écho
- [x] Story 2.11: Sortie Vocale de Session
- [x] Story 2.12: Question de Satisfaction de Fin de Session
### Accès Invité Sans Installation
> Goal: Un contact téléphone sans l'application peut rejoindre une session Salon anonymement depuis son navigateur, vivre l'expérience complète, et être invité à installer l'application après coup.

- [x] Story 3.1: Jonction Web Anonyme via Lien à Usage Unique
- [x] Story 3.2: Sortie de Session par Fermeture
- [x] Story 3.3: Question de Satisfaction pour Invité Anonyme
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
