# 08 — Roadmap MVP, risques & prochaines étapes

## 1. Découpage en sprints (équipe type : 1–2 devs fullstack TS)

| Sprint | Durée | Livrables | Critère d'acceptation |
|---|---|---|---|
| **S0 — Fondations** | 1 sem | Repo monorepo (apps/web, apps/api), Docker compose (PG/Redis), CI, Prisma schema v1, auth JWT + rôles | login/register fonctionnel, e2e pipeline vert |
| **S1 — Spike Stripe Connect** ⚠️ | 1 sem | POC paiement multi-vendeurs en test : checkout 2 vendeurs + commission + remboursement | décision documentée : Direct Charges vs Separate Charges & Transfers |
| **S2 — Catalogue** | 2 sem | Catégories admin, CRUD produits/variantes/images vendeur, pages publiques SSR (recherche, fiche produit, vitrine boutique) | un vendeur publie, un visiteur trouve et voit |
| **S3 — Vendeur onboarding** | 1 sem | Création boutique, plan Free/payant (Stripe Billing), soumission + validation admin, Connect onboarding | cycle pending→active complet |
| **S4 — Panier & commande** | 2 sem | Panier anonyme/auth, fusion, checkout + PaymentIntent, webhooks idempotents, machine à états, emails transactionnels | achat bout-en-bout en test + remboursement ligne |
| **S5 — Espace vendeur commandes** | 1 sem | File de commandes, confirmer/expédier/annuler, dashboard KPIs minimaux | flux expédition + tracking visible client |
| **S6 — Admin back-office** | 1 sem | Dashboard GMV/MRR, KYC queue, modération produits, settings plans/commissions, audit log | l'équipe opère sans SQL manuel |
| **S7 — Avis & beta privée** | 1 sem | Reviews achat vérifié, retours/remboursements côté client, seeds + onboarding docs, tests E2E Playwright | 5 boutiques pilotes réelles |

**Total ≈ 10 semaines de développement MVP** (+ marge 20 % → ~12 semaines avant beta publique).

### Ordre des jalons
```
S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → BÊTA → itérations V2
```

## 2. Matrice des risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Complexe de Stripe Connect multi-vendeurs mal dimensionnée | Haute | Élevé | Spike dédié S1 AVANT tout le reste ; choix documenté ADR ; mode "1 seul vendeur par commande" en fallback |
| Œuf de poule marketplace (pas de vendeurs → pas d'acheteurs) | Haute | Élevé | Recruter 10–20 boutiques pilotes manuellement avant pub ; catalogue seed ; focus niche verticale au lancement |
| Fraude achats / chargebacks | Moyenne | Élevé | Stripe Radar, seuils litiges, suspension auto > 2 %, KYC admin |
| Concurrence (Shopify, Etsy, WooCommerce) | Haute | Moyen | Différenciation : accompagnement francophone, niche, frais transparents, panier multi-vendeurs |
| Dérive de périmètre ("feature creep") | Haute | Moyen | Backlog priorisé P0/P1/P2 (doc 02), gate MVP strict |
| Cohérence stock sous concurrence | Moyenne | Moyen | UPDATE conditionnel atomique + tests de charge sur checkout |
| Conformité RGPD/CGU négligée | Moyenne | Élevé | Check-list legal avant go-live (doc 07 §4), modèles existants |
| Sous-estimation temps d'onboarding vendeur | Moyenne | Moyen | Objectif < 24 h première mise en vente, tunnel guidé avec checklist |

## 3. Questions ouvertes à trancher avec le fondateur
1. **Niche ou généraliste ?** (recommandé : démarrer vertical — artisanat/local/fashion — pour la beta)
2. **Zone géographique & devise(s)** de lancement ? (impact TVA, transporteurs, langue)
3. **Taux de commission initial** et structure de plans (Free avec commission haute vs payant commission basse) ?
4. Les vendeurs ont-ils besoin d'un **site autonome** (sous-domaine propre) dès le MVP ? (coût : routing DNS wildcard)
5. **Payouts** : fréquence souhaitée (Stripe default weekly vs daily) et trésorerie minimale ?
6. Volume de catalogue attendu au lancement (dimensionne search infra) ?
7. Prévoyez-vous une app mobile à terme ? (influence : API-first déjà prévu ✅)

## 4. Prochaines étapes immédiates
- [ ] Valider/corriger les docs 01→07 (atelier fondateur)
- [ ] Trancher les questions §3
- [ ] Choisir la stack définitive (doc 05) — si accord Next.js + NestJS + Postgres + Stripe
- [ ] Réaliser le spike S1 (Stripe Connect) et rédiger l'ADR
- [ ] Maquettes wireframes : accueil, fiche produit, checkout, dashboards vendeur/admin
- [ ] Initialiser le monorepo (S0)

## 5. Estimation budgétaire grossière MVP
| Poste | Estimation |
|---|---|
| Développement (~12 sem × 1–2 devs) | cœur du budget |
| Infra (12 premiers mois) | 60–150 €/mois |
| Stripe | 1,5–2,5 % + 0,25 €/transaction (Connect fees séparées selon pays) |
| Emails (Resend/SES) | < 50 €/mois au début |
| Légal (CGU/CGV marché) | forfait avocat ponctuel |
