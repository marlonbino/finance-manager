# PesaPlan — Youth finance completion plan

## Goal

Help a young person **capture money when it arrives**, **split it into life/work wallets**, **spend with limits**, and **fix mistakes** — daily on mobile.

## What exists today

- Auth (phone/username), wallets with % split, income auto-allocation, spending, activity snippet, insights + PDF
- Mobile-first UI (sheet, FAB, bottom nav)

## Implementation phases

### Phase 1 — Daily habit (this sprint)

| Feature | How |
|--------|-----|
| **Onboarding** | New `/onboarding` page; 3 templates (Student, Hustle, Employed); `POST /api/onboarding/setup`; redirect new users with 0 wallets |
| **Transfers** | `POST /api/transfer`; two ledger rows (`transfer_out` / `transfer_in`); sheet tab "Move" |
| **Transaction CRUD** | `DELETE`/`PUT` spending; `DELETE` income (reverse wallet split); activity page lists all |
| **Activity page** | `/activity` with filters (type, wallet, days) + edit/delete actions |
| **Income success** | After income POST, toast + optional breakdown list in sheet |

### Phase 2 — Control & limits

| Feature | How |
|--------|-----|
| **Monthly caps** | `Kitty.monthly_cap`; migration; spend blocked/warned at cap; progress on wallet cards |
| **Low balance alerts** | Banner on Home when wallet &lt; 20% of cap or empty |
| **Quick amounts** | Chips 100 / 200 / 500 on spend form |

### Phase 3 — Local & polish

| Feature | How |
|--------|-----|
| **M-Pesa quick capture** | Income form preset source "M-Pesa" + amount focus |
| **Goals** | `Goal` model (name, target, deadline, wallet_id) — stretch |

## Data model changes

```text
Kitty.monthly_cap          Float, nullable
Transaction.type           spending | transfer_out | transfer_in
User.onboarding_done       Boolean, default False
```

## API additions

- `POST /api/onboarding/setup` — `{ template: "student" | "hustle" | "employed" }`
- `POST /api/transfer` — `{ from_kitty_id, to_kitty_id, amount, note? }`
- `PUT /api/transactions/<id>` — spending only
- `DELETE /api/transactions/<id>`
- `DELETE /api/income/<id>` — reverse allocation
- `GET /api/transactions?days=&kitty_id=&type=`

## UI routes

- `/onboarding` — template picker
- `/activity` — full history (nav tab)

## Success criteria

1. New user completes onboarding in &lt; 2 minutes with 5 wallets at 100%
2. User can move money between wallets without fake expenses
3. User can fix a wrong spend from Activity
4. User sees monthly cap progress before overspending (Phase 2)

## Implementation status (latest)

- [x] Phase 1: models, onboarding, transfer, transaction/income CRUD, activity page, income breakdown
- [x] Phase 2: monthly caps, quick amounts, alert banner, M-Pesa preset
- [x] Phase 3: Activity in bottom nav
- [ ] Phase 3 stretch: Goals model (deferred)
