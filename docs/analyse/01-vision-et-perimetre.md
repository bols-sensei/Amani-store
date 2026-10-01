# 01 — Vision & Périmètre du produit

## 1. Vision

Créer une plateforme SaaS e-commerce **multi-vendeurs** (type Shopify + marketplace) permettant à des vendeurs d'ouvrir leur boutique en ligne sans compétences techniques, à des clients d'acheter chez plusieurs vendeurs, et à une équipe de piloter la plateforme (abonnements, modération, commission).

**Proposition de valeur :**
- **Vendeur** : lancer une boutique pro en < 10 min (produits, paiement, livraison) sans coder ; audience mutualisée de la marketplace.
- **Client** : acheter sur une place de marché unique avec panier multi-vendeurs, paiement sécurisé et suivi de commandes.
- **Admin SaaS** : revenus récurrents (abonnements) + commissions sur ventes, avec gouvernance (vérification vendeurs, litiges, conformité).

## 2. Positionnement / modèle économique

| Source de revenu | Description | Priorité |
|---|---|---|
| Abonnement vendeur | Plans Free / Pro / Business (mensuel/annuel) | MVP |
| Commission sur ventes | % prélevé par transaction selon le plan | MVP |
| Options payantes | Thèmes premium, modules expédition, marketing | V2 |
| Mise en avant | Produits sponsorisés dans la recherche | V3 |

## 3. Périmètre MVP vs suites

### MVP (Version 1)
- Authentification à 3 rôles (client, vendeur, admin)
- Boutique vendeur (vitrine publique), gestion produits (CRUD, variantes, stock)
- Recherche + navigation par catégories
- Panier multi-vendeurs, commande, paiement (Stripe test), webhooks
- Espace client : historique, statut de commande, avis
- Espace vendeur : commandes entrantes, préparation/expédition, tableau de bord
- Back-office admin : validation vendeurs, produits, catégories, plans, commissions, support

### V2
- Promotions/coupons, ventes flash
- Chat acheteur ↔ vendeur, notifications avancées
- Étiquettes transporteurs, tracking automatique
- Statistiques avancées vendeur, export comptable
- Fidélité, parrainage

### V3
- API publique, applications/modules tiers, webhooks développeurs
- Multilingue, multi-devises, TVA multi-pays (Stripe Tax)
- Sous-domaines par boutique (`boutique.plateforme.com`), SEO avancé
- IA : descriptions produits, recommandations, détection de fraude

## 4. Hors périmètre (à ce stade)
- Logistique physique (entreposage, flotte) → intégration transporteurs uniquement
- Paiement natif → on délègue à un PSP (Stripe Connect / PayPal)
- Conformité fiscale internationale complète (V2+)

## 5. Hypothèses clés à valider
1. Les vendeurs acceptent un modèle abonnement + commission.
2. Le panier multi-vendeurs et la répartition des paiements sont gérés par **Stripe Connect** (comptes connectés + `application_fee`).
3. La confiance repose sur la vérification des vendeurs (KYC léger) et les avis clients.
4. Volume MVP attendu : < 1 000 vendeurs actifs, < 10 000 commandes/mois → architecture monolithique modulaire suffisante.

## 6. Indicateurs de succès (KPIs)
- **Acquisition** : nb boutiques créées, taux d'activation (1re vente < 30 j)
- **Rétention vendeur** : churn mensuel, ARPU
- **Marketplace** : GMV, taux de conversion, panier moyen, taux de litige < 1 %
- **Plateforme** : MRR, take rate effectif, NPS
