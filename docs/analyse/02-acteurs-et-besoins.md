# 02 — Analyse des acteurs & besoins fonctionnels

## 1. Personas

### 👤 Client (acheteur) — « Amina, 28 ans »
Achat en ligne régulier sur mobile. Veut : confiance (avis, retours), paiement sécurisé, suivi de commande, un seul compte pour acheter chez plusieurs vendeurs.

### 🏪 Vendeur — « Karim, petit entrepreneur »
Vend artisanat/vêtements. Non technique. Veut : créer une boutique vite, gérer ses produits et commandes, être payé rapidement, connaître ses statistiques, coûts prévisibles.

### 🛡️ Admin SaaS — « Sophie, équipe plateforme »
Veut : contrôler la qualité (modération), piloter le business (MRR, GMV), gérer litiges/impayés, paramétrer commissions et plans, conformité légale.

## 2. Besoins fonctionnels par acteur

Notation : **P0** = MVP obligatoire · **P1** = MVP important · **P2** = après MVP

### 2.1 Client
| ID | Besoin | Priorité |
|---|---|---|
| C-01 | S'inscrire / se connecter (email, OAuth Google) | P0 |
| C-02 | Parcourir le catalogue (recherche, filtres, catégories) | P0 |
| C-03 | Voir la fiche produit (photos, variantes, stock, vendeur, avis) | P0 |
| C-04 | Consulter la vitrine d'une boutique | P0 |
| C-05 | Gérer un panier multi-vendeurs | P0 |
| C-06 | Passer commande + adresse de livraison (+ facturation) | P0 |
| C-07 | Payer en ligne (carte, Apple/Google Pay via Stripe) | P0 |
| C-08 | Suivre le statut de ses commandes (confirmée→expédiée→livrée) | P0 |
| C-09 | Laisser un avis/note sur un produit acheté | P1 |
| C-10 | Liste d'envies / favoris | P1 |
| C-11 | Demander un retour/remboursement | P1 |
| C-12 | Gérer son profil, adresses, moyen de paiement enregistré | P1 |
| C-13 | Notifications email (confirmation, expédition) | P1 |

### 2.2 Vendeur
| ID | Besoin | Priorité |
|---|---|---|
| V-01 | S'inscrire comme vendeur + ouvrir sa boutique (nom, logo, bannière, description) | P0 |
| V-02 | Choisir/monter en plan d'abonnement (Free/Pro/Business) | P0 |
| V-03 | CRUD produits : titre, description, prix, images, catégorie, stock | P0 |
| V-04 | Variantes (taille, couleur…) avec prix/stock par variante | P1 |
| V-05 | Statut produit (brouillon, actif, en pause, sold out) | P0 |
| V-06 | Recevoir les commandes de sa boutique et les traiter | P0 |
| V-07 | Transition d'états : nouvelle → confirmée → expédiée → livrée / annulée | P0 |
| V-08 | Saisir transporteur + numéro de suivi | P0 |
| V-09 | Tableau de bord : CA, commandes, produits phares | P1 |
| V-10 | Connecter son compte Stripe (retraits/payouts) | P0 |
| V-11 | Gérer les demandes de retour et rembourser | P1 |
| V-12 | Promotions (réduction %, code promo) | P2 |
| V-13 | Personnaliser sa vitrine (thème, sections) | P2 |
| V-14 | Import/export produits (CSV) | P2 |

### 2.3 Admin SaaS
| ID | Besoin | Priorité |
|---|---|---|
| A-01 | Dashboard global : MRR, GMV, nb vendeurs/commandes/litiges | P0 |
| A-02 | Valider/suspendre/rejeter les comptes vendeurs (KYC léger) | P0 |
| A-03 | Modérer les produits (signalement, retrait pour contenu interdit) | P0 |
| A-04 | Gérer les catégories (arborescence) et attributs | P0 |
| A-05 | Gérer les utilisateurs (client/vendeur/admin), recherche, blocage | P0 |
| A-06 | Définir les plans d'abonnement et tarifs (Stripe Billing) | P0 |
| A-07 | Paramétrer le taux de commission (global + override par vendeur/plan) | P0 |
| A-08 | Superviser toutes les commandes et litiges, arbitrer remboursements | P1 |
| A-09 | Gérer les avis (signalements, suppression) | P1 |
| A-10 | Rapports financiers (commissions facturées/perçues, payouts) | P1 |
| A-11 | CMS : pages légales, CGU/CGV, emails transactionnels | P2 |
| A-12 | Journal d'audit des actions admin | P2 |
| A-13 | Support/tickets centralisés | P2 |

## 3. Besoins transverses (plateforme)
- **Rôles & permissions** : un utilisateur peut être client ET vendeur ; séparation stricte des accès (`client`, `vendor`, `admin`).
- **Paiements récurrents** : abonnements vendeur (Stripe Billing), grace period à l'expiration du plan → boutique désactivée.
- **Commissions** : prélevées automatiquement à chaque vente (`application_fee_amount` Stripe Connect).
- **Notifications** : email (Resend/SES) — base ; push/in-app plus tard.
- **SEO & partage** : pages boutiques/produits indexables (SSR).
- **Multi-tenancy** : isolation des données par boutique (chaque vendeur ne voit que ses produits/commandes).

## 4. Besoins non fonctionnels (rappel, détail dans doc 04)
Sécurité, performance (<2 s page produit), disponibilité 99,5 %, RGPD/PCI-DSS (délégué au PSP), scalabilité, observabilité, sauvegardes.
