# 07 — Exigences non fonctionnelles, sécurité & conformité

## 1. Performance
| Objectif | Cible | Moyens |
|---|---|---|
| TTFB pages catalogue/produit (SSR) | < 400 ms p95 | cache Redis, index DB, CDN images |
| LCP page produit | < 2,5 s mobile | next/image, lazy gallery |
| API checkout (POST /checkout) | < 800 ms p95 | transaction optimisée, Stripe async |
| Webhooks Stripe traités | < 5 s | file BullMQ + workers dédiés |

## 2. Disponibilité & continuité
- SLO MVP : **99,5 %** marketplace ; checkout prioritaire (alerte si taux d'erreur paiement > 1 %).
- Sauvegardes Postgres : PITR/daily, rétention 30 j, restauration testée trimestriellement.
- Plan de dégradation : Stripe indisponible → panier sauvegardé, message clair, relance auto.

## 3. Sécurité
- **Authentification** : bcrypt/argon2 (cost ≥ 12), refresh tokens rotatifs stockés hashés, révocation, verrouillage après 5 échecs, 2FA pour admins (TOTP) — P1 vendeurs à fort volume.
- **Autorisation** : RBAC rôles cumulables + checks d'ownership systématiques ; tests automatiques de matrice d'accès (chaque endpoint × chaque rôle).
- **Données de carte** : jamais touchées (Stripe Elements) → hors scope PCI SAQ-A.
- **Webhooks** : vérification signature `Stripe-Signature` + tolérance de rejeu 5 min + idempotence.
- **Uploads** : presigned URLs, taille/type validés, antivirus/scan images (V2), recadrage CDN.
- **Injection/XSS** : ORM paramétré, CSP stricte, sanitisation description produits (DOMPurify côté rendu).
- **Rate limiting** : login 10/min/IP, checkout 5/min/user, upload 60/min/store.
- **Secrets** : vault env, rotation, aucun secret en repo (scan GH Actions).
- **Dépendances** : Dependabot + `npm audit` en CI.

## 4. Conformité & légal
- **RGPD** : registre des traitements, consentement CGU, droit à l'effacement (anonymisation commandes vs obligation comptable 10 ans → base légale "obligation légale"), export données utilisateur, DPA hébergeurs UE.
- **CGU/CGV marketplace** : rôle d'intermédiaire (hébergeur), médiation consommation, délai rétractation 14 j (loi française/e-commerce) → impact direct sur la feature retours.
- **Facturation** : numéro commande + email facture PDF (V2 : facturation via Stripe Invoicing).
- **LCI/PCI** : aucune donnée sensible en local.
- **Modération** : points de contact signalement (DCA), politique produits interdits documentée.

## 5. Observabilité
- Logs structurés JSON corrélés (`request_id`, `order_id`).
- Metrics : taux conversion tunnel, latences endpoints, file webhooks lag, erreurs Stripe.
- Alerting Sentry (checkout, webhooks) + uptime ping.

## 6. Qualité & tests
- Unit : pricing/commissions/machine à états (property-based sur les montants — arrondis en centimes entiers uniquement).
- Intégration : parcours complet avec Stripe Test Clock ; contrats d'idempotence webhooks.
- E2E (Playwright) : inscription vendeur → publication produit → achat client → expédition → avis.
- Chargement smoke (k6) : 200 users concurrents sur catalogue+checkout.

## 7. Évolutivité (garde-fous)
- Découpage modulaire = extraction future possible (search → Meilisearch, media worker séparé).
- Événements internes loggés (`DomainEvent`) pour brancher plus tard Kafka/SQS sans casser.
- Montants stockés en **centimes entiers**, jamais en float.
