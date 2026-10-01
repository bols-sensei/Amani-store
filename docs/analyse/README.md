# Analyse — SaaS E-commerce Multi-vendeurs

Dossier d'analyse produit (3 espaces : **Client**, **Vendeur**, **Admin SaaS**).

## Table des matières

| Doc | Contenu | À lire si… |
|---|---|---|
| [01 — Vision & Périmètre](01-vision-et-perimetre.md) | Positionnement, modèle économique (abonnements + commission), périmètre MVP/V2/V3, KPIs | tu veux valider la direction produit |
| [02 — Acteurs & Besoins](02-acteurs-et-besoins.md) | Personas + backlog fonctionnel priorisé (P0/P1/P2) par acteur | tu définis le scope du MVP |
| [03 — Parcours utilisateurs](03-parcours-utilisateurs.md) | User flows détaillés, machines à états commande & boutique | tu conçois les écrans et la logique métier |
| [04 — Modèle de données](04-modele-donnees.md) | MCD Mermaid + dictionnaire de données (users, stores, products, orders/suborders, payments, ledger commissions…) | tu prépares le schéma Prisma/SQL |
| [05 — Architecture & Stack](05-architecture-stack.md) | Monolithe modulaire NestJS + Next.js SSR, Stripe Connect, points critiques (stock, webhooks, multi-tenant) | tu choisis la techno |
| [06 — Spécification API](06-specification-api.md) | Contrat REST complet par domaine + exemples | tu développes front/back en parallèle |
| [07 — Exigences non fonctionnelles](07-exigences-non-fonctionnelles.md) | Perf, sécurité, RGPD/conformité marketplace, tests | tu prépares le go-live |
| [08 — Roadmap & Risques](08-roadmap-risques.md) | 8 sprints (~12 sem.), matrice de risques, questions ouvertes au fondateur | tu planifies le chantier |

## Synthèse en 60 secondes

1. **Produit** : marketplace SaaS où chaque vendeur ouvre sa boutique (abonnement Free/Pro/Business), la plateforme prélève une commission à chaque vente via **Stripe Connect**.
2. **3 espaces** : client (acheter, suivre, noter) · vendeur (boutique, catalogue, commandes, payouts) · admin (KYC vendeurs, modération, plans, commissions, litiges, reporting).
3. **Modèle clé** : `Order` (logique, côté client) → se divise en `SubOrder` (une par vendeur) — c'est l'unité de traitement, de commission et de remboursement.
4. **Risque n°1** : complexité du paiement multi-vendeurs → **spike Stripe Connect en sprint 1** avant tout autre développement lourd.
5. **MVP** : ~10–12 semaines de dev pour boucle complète *vendeur publie → client achète paye → vendeur expédie → admin encaisse la commission*.
