# VoltStop partner onboarding and corridor launch plan

**Updated:** 19 October 2026
**Product model:** Manually verified NH-16 partner directory and booking marketplace. Live charge-point telemetry is not a launch dependency.

## Customer promise and data limits

VoltStop can launch a useful corridor product with participating businesses even without a charge-point operator API. The app may show verified business listings, services, opening hours, partner-entered charging slots, food, and stays. It must label partner-entered information as such and must not call a charger “live,” “available now,” or “reserved” unless that state is confirmed by an integrated charger provider.

Suggested customer wording for a charging listing:

- **Partner-listed charging stop** when the business advertises charging but there is no provider telemetry.
- Show the partner's posted details and the time those details were last confirmed, when available.
- Tell drivers to contact the business to confirm that the charger is working and suitable for their vehicle.
- Keep route energy, arrival state of charge, and distances labelled as estimates.

Do not imply VoltStop starts/stops charging or measures charger session energy until a charger provider integration supports those actions.

## Partner application lifecycle

1. A business owner creates an email account and confirms it through Supabase Auth, if confirmation is enabled.
2. The owner submits one business profile: business name/type, contact details, address, map pin, operating hours, and description.
3. The API creates a `public.vendors` row with inactive/unverified defaults. The database trigger creates a `public.vendor_onboarding` application in `pending` state.
4. The owner adds accurate services, prices, and availability. These are partner-submitted details and remain unpublished while the business is pending.
5. An authorized admin reviews the application in **Admin → Vendor Onboarding** and records a reason with one of: approve, request changes, reject, or begin review.
6. Approval sets the vendor verified and active. Public discovery queries include only active, verified vendors. A later suspension hides the listing without deleting the application history.
7. The owner sees the decision/state in the portal, fixes requested details, and contacts VoltStop support if the business or owner account is wrong.

The current repository already implements the core profile creation, pending onboarding record, admin actions, server-side permission checks, decision reasons/audit trail, and active-plus-verified public discovery filter. The vendor profile now shows the review state and a change-request note; saving an edited profile after a change request returns the application to `under_review`. Do not build a parallel approval subsystem.

## Admin review checklist

Before approval, an operations reviewer should confirm:

- The owner email is verified and linked to the intended business account.
- Required name, type, contact, address, and map pin are present and plausible.
- The owner can be reached to confirm they control or represent the business.
- Opening hours, services, prices, slot capacity, and booking rules are understandable and not misleading.
- Charging listings describe what the partner actually provides (connector/power details only when confirmed) and are not represented as provider-verified live availability.
- The listing has useful customer-facing information and no broken or misleading image/location links.
- The decision reason is specific enough for the owner to act on; sensitive identity material is not copied into free-text notes.

Use a separate, access-controlled KYC/document process if VoltStop later needs identity or business documents. Do not collect sensitive documents in an unprotected notes field.

## Rollout and commercial plan

### Stage 0 — verify the workflow in staging

- Apply/reconcile the existing vendor-onboarding migration in the intended database after a verified backup and staging rehearsal.
- Register a new partner test account, confirm Auth behavior, submit its profile, and verify it appears once in Admin → Vendor Onboarding with the correct owner email.
- Exercise request-changes, resubmission, approval, rejection, suspension, and reactivation with role-appropriate accounts.
- Confirm pending/rejected/suspended listings do not appear in driver discovery, and only approved active businesses do.
- Confirm the decision and actor are present in the audit log.

### Stage 1 — curated NH-16 pilot

- Start with a small number of manually contacted partners in the Srikakulam–Vijayawada corridor.
- Keep applications reviewed by an admin and listings maintained by partner owners.
- Publish clear partner-reported labels and a way to contact the business before a driver detours.
- Track application completion, approval time, listing freshness, booking completion, cancellations, complaints, and failed-contact reports.
- Do not promise nationwide coverage, live charger uptime, automatic charger booking, or automated partner payouts.

### Stage 2 — settle the commercial terms before collecting fees

- Decide whether the pilot is free, subscription-based, commission-based, or a combination before exposing a paid plan in the portal.
- Publish the terms, settlement timing, cancellation/refund rules, tax handling, and support responsibilities before taking partner money.
- The current repository reports that vendor transfers and a payout ledger are not implemented. Keep actual payouts disabled until the ledger, reconciliation, failure handling, and audit trail are complete.
- Keep the existing 5% calculation informational unless its applicable booking base, refund treatment, partner agreement, and actual settlement behavior have been verified and disclosed.

### Stage 3 — provider integration and expansion

- Add live connector status only after a provider's API contract, credentials, rate limits, and operational support are verified.
- Then add freshness-aware status, vehicle/connector compatibility, provider-backed session start/stop, payment reconciliation, and customer support for session failures.
- Expand to additional corridors only when partner supply, data accuracy, and operations can support them.

## Current release blockers

- The repository contains the approval workflow, but the current production database migration state and deployed API commit have not been verified for this workflow.
- Historical reports noted that auth-only accounts have no `vendors` row until the business profile is submitted. Admin approval cannot show an auth user that has not submitted a profile.
- A live charger API is unavailable to VoltStop at present; use partner-reported listing semantics until one is contracted and integrated.
- A commercial subscription plan has not been specified or implemented. Do not create a paid tier or charge a vendor without an approved pricing/settlement policy.
