SNAYW V1
========

Lancement sous Windows : double-clique sur « Lancer Snayw Tools.bat ».
Python 3 avec Tkinter doit être installé. L’application s’ouvre dans une fenêtre
graphique gris-noir, translucide, avec curseur rond et effets animés.

Réglages et fluidité
--------------------
- Active ou coupe les animations et le curseur animé.
- Ajuste l’opacité, l’objectif d’animation (jusqu’à 360), la densité des
  particules et leur rayon d’interaction ; les réglages sont conservés sur le PC.
- La fréquence affichée dépend de Windows, de Tkinter, de la charge du PC et de
  l’écran : 360 est un objectif, pas une garantie de 360 images/s.
- Le curseur noir et blanc est fourni dans snayw_cursor.cur.

Outils
------
- Réseau : résout les domaines, URL complètes et adresses IP ; classification
  publique/privée/réservée et test de ping.
- Pseudos : ouvre un profil public exact sur une plateforme choisie et génère
  des idées de pseudos. L’outil ne relie pas l’identité d’une personne entre sites.
- Générateurs : mot de passe cryptographiquement aléatoire configurable (8 à
  128 caractères), numéro de démonstration, code fictif à 4 chiffres et adresse
  e-mail non distribuable sous example.invalid.
- E-mail & sécurité : vérifie localement le format d’une adresse, estime à titre
  indicatif la robustesse d’un mot de passe, recherche facultativement un mot de
  passe compromis via Have I Been Pwned (k-anonymat) et ouvre Mozilla Monitor
  pour les fuites d’adresse e-mail.
- Discord : prépare et exporte un plan de serveur (salons, rôles et conseils),
  puis ouvre Discord pour finir la création depuis ton compte.
- PC : aperçu et nettoyage confirmé des anciens fichiers directement dans
  %TEMP%, raccourcis vers les réglages Jeu/alimentation et diagnostic des
  composants et statistiques exposés par Windows.
- Personnalisation Windows, Base64 et empreintes SHA-256.

Confidentialité et limites
--------------------------
L’analyse locale des mots de passe et les adresses fictives restent sur le PC.
Si tu cliques sur la recherche de fuite de mot de passe, Snayw calcule son hash
localement et envoie uniquement un préfixe de 5 caractères à Have I Been Pwned,
avec réponse complétée par du remplissage de confidentialité ; le mot de passe
complet n’est pas envoyé. La vérification d’une fuite d’adresse demande de saisir
l’adresse directement dans Mozilla Monitor ouvert par l’application.
La connexion Discord se fait dans Discord : Snayw Tools ne demande jamais ton
mot de passe. Le nettoyage %TEMP% demande confirmation et ignore les dossiers,
liens et fichiers utilisés. Aucun outil ne promet un gain artificiel de FPS ou
de ping.
