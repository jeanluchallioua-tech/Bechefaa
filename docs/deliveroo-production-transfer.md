# Deliveroo production transfer — review draft, 2 November 2026

Prepared from production commit 3db9f7c8239455da33dd96363bc629cd048b85d3 and sandbox commit 27e7c4eb241cd63935f6b7d8af08c7e16f6ed43f. This branch is for review; do not merge/deploy/activate automatically.

## Confirmed current deployment

The public production webhook paths exist (HEAD 405, Allow POST/OPTIONS). Its diagnostic currently reports OAuth/API sandbox hosts, present credentials/secret, and a successfully obtained sandbox token. Secret values were neither retrieved nor printed. Current production source records order events without inserting POS orders. Deliveroo has confirmed certification completion and requested production webhook URLs.

Registering webhook URLs is a portal setup step. It is not proof that production credentials, signatures, POS import, or go-live are ready. Tell Deliveroo not to activate real orders before technical readiness is confirmed.

## Scope of this draft

- Separate production receiver, disabled unless explicitly configured; existing sandbox receiver and test tools retained.
- Production app, HTTPS API/auth hosts, non-sandbox site/brand allowlists and explicit enable flag required. Production identities must be supplied from Deliveroo; never infer them from sandbox IDs.
- HMAC checked on exact GUID + space + raw body before accepting an event.
- Accepted-order import adapted from validated sandbox code: deterministic order IDs, terminal-state protection, cent-exact discounts, modifiers, contact/address fields, and cancellation/rejection handling.
- Payment label **PAYÉ DELIVEROO**, internal payment status PAYÉE, payment method/provider DELIVEROO. No local cash/card collection or refund is initiated.
- Only explicitly prepaid EUR orders supported by this draft. Unknown payment state or nonzero cash_due is rejected for retry/manual investigation, never marked paid.
- Production event/metadata tables separated from old sandbox diagnostic data. Existing tables and records are not deleted.
- Scheduled orders held out of kitchen until confirmed and start_preparing_at reached. Explicit remake links suppress preparation of the imported parent when its imported replacement exists.
- Per-order sync throttling and same-state deduplication. Transport/auth failures keep webhook retryable, without blind internal retries.
- Persistent turquoise notice uses existing configured POS sound and does not print automatically. Site notification timing and ticket layout unchanged.
- English test-menu PLU/name fixtures, certification buttons, stock/menu uploads, and manual test accept/prep endpoints are not activated by this production module.

## Configuration still required before activation

No secret values belong in this document or in chat.

- BECHEFAA_DELIVEROO_API_URL=https://api.developers.deliveroo.com
- BECHEFAA_DELIVEROO_AUTH_URL=https://auth.developers.deliveroo.com
- Production values for BECHEFAA_DELIVEROO_CLIENT_ID, BECHEFAA_DELIVEROO_CLIENT_SECRET, BECHEFAA_DELIVEROO_WEBHOOK_SECRET (set directly in hosting environment).
- BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID and BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID.
- Acceptance mode: this draft requires BECHEFAA_DELIVEROO_ACCEPTANCE_MODE=deliveroo_tablet and is_tabletless=false. Tabletless/automatic acceptance, including opening hours and religious-calendar policy, remains unimplemented and must not be enabled implicitly.
- BECHEFAA_DELIVEROO_PRODUCTION_ENABLED remains unset/0 until reviewed and explicitly approved.

## Validation and outstanding review

18 mocked/local tests verify default-off configuration, sandbox isolation, HMAC, context checks, prepaid amounts, discounts, external payment label/provider, duplicate/terminal protection, schedules, cancellation, and acknowledgement throttle/deduplication. Python compilation and JavaScript syntax checks pass. No production webhook POST or real order has been sent.

This is NOT a production go-live signoff. Before deployment/activation: review code against current production head; verify actual catalog PLUs and modifiers rather than fixture names; verify site/tablet acceptance mode; exercise PostgreSQL transactions and concurrent/retried webhooks on isolated data; verify future/confirmed/remake display, cashier sound, meal-card accounting, VAT/fiscal exports, delivery instructions and history/preview on the current production UI. Source templates, font sizes and receipt layouts are not changed in this draft. Initial implementation covers backend drafts and requires these integration checks.

Deploying this branch with feature enabled, changing production secrets/hosts, and enabling live orders require explicit user authorization. Never change phase4-encaissement merely to publish this review draft.
