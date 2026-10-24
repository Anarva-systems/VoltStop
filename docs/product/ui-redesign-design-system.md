# VoltStop Unified Design System (PART 2)

Date: 2026-10-23 · Applies to: `apps/mobile` (Flutter) + `apps/vendor-web` (Next.js) · Brand basis: existing VoltStop forest/lime identity (inspected, preserved)

## 1. Visual identity

Premium EV corridor product. Light, calm, outdoorsy: cream canvas, deep forest surfaces, lime as the charge accent. Serif display headlines paired with sans body text — editorial + engineering feel. Generous whitespace, rounded geometry, hairline borders, soft diffused shadows.

## 2. Canonical color tokens

| Token | Hex | Use |
|---|---|---|
| `canvas` | `#F4F3EC` | App/portal background |
| `surface` | `#FFFEFA` | Cards, inputs, sidebar, topbar |
| `elevated` | `#EDF3E6` | Subtle fills, chips, icon badges |
| `forest` | `#1A4035` | Headings, dark hero surfaces, primary text |
| `leaf` | `#1B7650` | Interactive primary: buttons, links, active nav, progress |
| `lime` | `#B7DC68` | Accent: charge visuals, selected surfaces, badges |
| `muted` | `#53685E` | Secondary text, captions |
| `soft` | `#819086` | Tertiary text, placeholders |
| `line` | `#DCE3D8` | Hairline borders, dividers |
| `warning` | `#79580D` | Amber states, estimates, attention |
| `red` | `#A43A32` | Errors, destructive, negative states |
| `sky` | `#5B8FA6` | Reserved: maps/routes only (never status or text accents) |

Mapping decisions:
- Mobile `VoltColors`: `forest #1A4035`, `lime #B7DC68`, `background #F4F3EC`, `surface #FFFEFA`, `elevated #EDF3E6`, `border #DCE3D8`, `muted #53685E`, `warning #79580D`, `red #A43A32` — already canonical. `VoltColors.green` (alias of forest) and `VoltColors.cyan #476E58` remain source-compatible; new UI must prefer `forest`/`lime`.
- Web: unify the three competing light palettes to the canonical tokens above:
  - `globals.css` light override (`:root` block) becomes the single source: `--bg:#F4F3EC --surface:#FFFEFA --elevated:#EDF3E6 --line:#DCE3D8 --green:#1B7650 --cyan:#476E58 --text:#1A4035 --muted:#53685E --soft:#819086 --red:#A43A32 --amber:#79580D`.
  - `portal-refresh.css` and the `admin.css` light block are reconciled to reference the same values (duplicate declarations allowed, identical values only).
  - Dark base blocks stay in place (dead code for an unselected theme) but must not reintroduce the old teal/green `#20c86b`/`#43d7ee` identity in any active override.

## 3. Typography

| Role | Mobile | Web |
|---|---|---|
| Display (page titles, heroes) | `fontFamily: 'serif'`, w600–w700, letter-spacing −0.4…−0.8 | `Georgia, 'Times New Roman', serif`, 600, clamp(29px,3vw,36px) |
| Heading (section titles) | titleLarge/titleMedium w700 | 15–16px, w750 |
| Body | 13–14px, height 1.45 | 11–13px, line-height 1.5–1.7 |
| Caption / meta | 10–11px muted | 9–10px muted, letter-spacing .5–1px uppercase for eyebrows |

## 4. Spacing & radii

| Scale | px | Mobile | Web |
|---|---|---|---|
| xxs / xs / sm / md / lg / xl / xxl | 4 / 8 / 12 / 16 / 24 / 32 / 44 | `VoltSpacing.*` (unchanged) | use 4px grid |
| Radius: control | 15 | `VoltRadii.control` | 12 (inputs), 999 (pill buttons) |
| Radius: card | 18–20 | `VoltRadii.card` = 20 | 17–18 |
| Radius: pill | 999 | `VoltRadii.pill` | 999 |

Web button radius: keep 999 pills (existing enterprise theme) — primary CTAs are pills, quiet/table actions are rounded 8–10.

## 5. Component specs

Shared conceptually across platforms; each platform implements natively.

| Component | Spec |
|---|---|
| Primary button | leaf background, surface text; busy/disabled states; min-height 42–54 |
| Secondary button | surface + line border, forest text |
| Quiet/danger | transparent / red-tinted |
| Card (`VoltCard` / `.panel`, `.admin-card`) | surface, line border, radius 18–20, soft shadow `0 7px 22px rgba(30,56,38,.045)` |
| Input | surface fill, line border, focus ring leaf at 3px/10% |
| Status pill | dot + label; green set: confirmed/completed/available/captured; amber: pending/limited/locked/authorized; red: cancelled/rejected/closed/failed/expired; booked: sky tint (web) / forest tint (mobile) |
| Navigation | mobile: `NavigationBar` h72 forest/lime; web: sidebar 254–258px, active item = lime-tinted gradient + leaf left bar |
| Dialog | radius 20, surface, scrim `rgba(20,34,24,.42)`; destructive or state-changing actions use the shared confirm dialog; admin API reason requirement stays enforced in the form itself |
| Loading | skeleton shimmer lines + centered spinner (both platforms already have) |
| Empty state | icon badge (elevated fill, forest icon), title, muted description, optional action |
| Error state | red-tinted icon, message, retry secondary button |
| Form validation | inline error text under field (red), field border red on error; server errors shown once above actions |
| Table | hairline row dividers, uppercase 8–9px headers, wrap in `overflow-x:auto`, hover tint |
| Filter | chips (mobile) / labeled selects+inputs (web admin); every filter input gets a label (visible or sr-only) |

## 6. Motion

- Durations 150–220ms for state changes; 650ms easeOutCubic for the charge ring; skeleton 1.5s loop; respect `prefers-reduced-motion` (web) and `MediaQuery.disableAnimations` (mobile) where feasible.
- Booking-success check animates once (scale+fade) — the confirmation is real server state, animation is presentation only.

## 8. Web dialog and feedback system (implemented)

One dismissal contract for every modal in `apps/vendor-web`, so vendor and admin screens behave identically.

| Piece | Where | Behaviour |
|---|---|---|
| `ConfirmDialog` | `components/portal.tsx` | Shared presentational confirm (no text entry). Backdrop click, `Escape`, and the close button all dismiss; every control is disabled while `busy`; confirm button is auto-focused; `role="dialog"`/`aria-modal`/`aria-labelledby` set. |
| `DialogEscapeBridge` | `components/portal.tsx`, mounted in the vendor `(protected)` layout and `AdminGuard` | One global `Escape` listener for the pre-existing dialogs it cannot own: it finds the top-most `.modal-backdrop`/`.admin-modal-backdrop` and clicks that dialog's own close control. Skips when the close control is missing or disabled, so an in-flight request is never cancelled by a stray keypress. |
| Backdrop dismissal | `app/admin/(secure)/*` dialogs | Every `admin-modal-backdrop` now closes on backdrop `mousedown` (guarded by `busy`), `role="presentation"`, and its close button carries `aria-label="Close dialog"`. |
| Filter labelling | `FilterSelect` across the admin console | Every select has an accessible name (`aria-label`), derived from its own "All …" placeholder option where one exists. |
| Toast | `ToastViewport` / `AdminToastHost` | Single event-bus toast for both portals (`voltstop-toast`), already mounted in vendor and admin shells. |

New shared CSS utilities in `app/globals.css` (token-driven, so they render correctly in both the light portal and the dark base): `.table-sub` (secondary cell line), `.table-footnote` (table footer row), `.select-inline` (auto-width filter select), `.cell-flag` (amber reconciliation flag in finance tables), `.action-link-danger` (destructive table action), `.metric-icon-cyan` / `.metric-icon-green`, `.request-row*` (dashboard inbox layout), `.label-note-spaced`. `app/admin.css` gains `.admin-chart-empty`, larger pager/close touch targets, and readable 9px chart and table-header labels.

Rule applied while auditing copy: no UI may imply data the API does not return. The vendor dashboard's "open capacity" bar was removed because `available_capacity` has no denominator; it is replaced by explicit counts plus a caption stating that published slots are not real-time charger availability.

## 9. Content principles (enforced by existing product)

- Never claim live charger telemetry; slot listings are reservations, not real-time plugs.
- Payment success is shown only after the API reports `confirmed`.
- Estimates are labeled estimates; refund copy always states finance review and no gateway fee deduction.
- Route/battery figures are estimates; footnote stays on every screen that shows them.
