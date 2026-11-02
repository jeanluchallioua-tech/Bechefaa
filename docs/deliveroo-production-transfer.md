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
- Requested acceptance policy: BECHEFAA_DELIVEROO_ACCEPTANCE_MODE=auto_hours, with BECHEFAA_DELIVEROO_CONFIRM_WORKER_ENABLED=1. The persistent worker uses existing saved hours, Deliveroo closures, and the religious calendar. Missing calendar coverage blocks decisions rather than guessing. Future scheduled orders may be accepted while currently closed when their future preparation slot is open; confirmation waits for confirm_at and kitchen visibility waits for start_preparing_at.
- Durable jobs record each PATCH attempt before transmission. Ambiguous outcomes await signed webhook evidence; local import repair after HTTP 204 does not resend acceptance. Retryable provider errors use delayed retries.
- Actual production catalog PLUs, modifier ownership, and names are checked before automatic acceptance; sandbox menu fixtures are not used.
- BECHEFAA_DELIVEROO_PRODUCTION_ENABLED remains unset/0 until reviewed and explicitly approved.

## Validation and outstanding review

The isolated validation suite contains 69 Python tests: 20 production unit tests, 6 automatic-hours policy tests, 34 real PostgreSQL order/automation tests, and 9 tests of the shared hours/calendar engine. A separate Node suite checks 12 notification behaviors. GitHub Actions uses a disposable PostgreSQL database and synthetic payloads; outbound Deliveroo requests are mocked. No production database, real order, webhook POST, charge, or refund is used.

The first automation run passed the first 60 Python tests but failed one of the 9 shared-calendar tests because its synthetic calendar omitted the following week. The fixture was extended without weakening calendar validation; the corrected run 41432707557 passed all checks on commit 7a2a6f94f097a5016d99169c9ffd16c73d74f273.

This is preparation for review, not production go-live signoff. Remaining live checks require production IDs and credentials installed directly in hosting, current calendar coverage and hours, actual production HMAC/API authorization, and device-level sound/display checks. Existing tax/fiscal conventions are reused; meal-card and partner payment metadata do not cause another local collection. Source templates, font sizes and receipt layouts are unchanged.

Portal Orders test mode routes real orders to the test endpoint. The merchant is currently inactive; coordinate that setting with activation and do not treat saved URLs as proof that live processing is enabled.

Deploying this branch with feature enabled, changing production secrets/hosts, and enabling live orders require explicit user authorization. Never change phase4-encaissement merely to publish this review draft.
