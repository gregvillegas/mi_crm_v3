# MiCRM — System Presentation
## Micro Image International Corp.

**Platform:** Django 5.2 Web Application  
**Stack:** Python · Bootstrap 5 · MariaDB · nginx · Gunicorn · Daphne  
**Date:** July 2026

---

## Agenda

1. [Customer Database](#1-customer-database)
2. [Sales Proposals](#2-sales-proposals)
3. [Sales Funnel](#3-sales-funnel)
4. [Role-Based Dashboards](#4-role-based-dashboards)
5. [Sales Monitoring](#5-sales-monitoring)
6. [Email Campaigns (Mass Mailing)](#6-email-campaigns-mass-mailing)

---

## 1. Customer Database

### What it does

The Customer module is the master record for all companies Micro Image does business with or is pursuing. Every other module — Proposals, Funnel, Activities, Campaigns — references a Customer record.

### Key Features

**Customer Record**
- Company name, contact persons (up to 5), email, phone, address
- Industry classification and territory assignment
- Millionaire Account flag (VIP accounts)
- Active / Inactive status with automatic inactivity detection
- Assigned Corporate Account Manager (salesperson)

**Customer Creation Workflow**
- Salespersons submit a creation request when a similar company name is detected
- System uses fuzzy matching (Jaccard + SequenceMatcher) to find duplicates
- AVP / GM / VP / Marketing approves or rejects with notes
- Direct creation allowed for managers and above

**Data Tools**
- Import via CSV (legacy, contacts-only, and combined formats)
- Export to CSV (customers + up to 5 contacts per row)
- Sample CSV templates downloadable from the list view
- Customer history and audit trail — every field change is logged

**Delinquency Tracking**
- Separate delinquent customer database
- Import / export of delinquency records with TIN, partner name, payment dates
- Status: Open · Watch · Resolved

**Access by Role**

| Role | Can See | Can Create | Can Transfer | Can Import/Export |
|---|---|---|---|---|
| Admin / VP / GM | All customers | ✅ Direct | ✅ | ✅ |
| Marketing | All customers | ✅ Direct | ✅ | ✅ |
| AVP | Team customers | ✅ Direct | ✅ | — |
| Supervisor / ASM | Group customers | ✅ Direct | ✅ | — |
| Teamlead | Group customers | ✅ Direct | — | — |
| Salesperson | Own customers | Request only | — | — |

---

## 2. Sales Proposals

### What it does

The Proposals module handles the full lifecycle of a formal sales quotation — from drafting to PDF generation, client email delivery, and internal approval.

### Proposal Number Format

Auto-generated: `{INITIALS}-{YEAR}-{SEQUENCE}`  
Example: `PCR-2026-0042`

Reference number also auto-generated: `{INITIALS}{YYYYMMDD}{SEQ}`  
Example: `PCR202607230042`

### Key Features

**Proposal Creation**
- Line items with part number, description, quantity, unit price, unit cost
- Optional items (excluded from total, printed as "Option" in PDF)
- Bundle items — one priced row that expands to show component part numbers
- Currency support: PHP and USD with configurable exchange rate
- Tax types: VAT 12% · Zero-Rated · VAT-Exempt

**Terms & Conditions**
- Payment terms (free text)
- Delivery lead time (selectable from standard options)
- Stock availability (On-Stock / Order Basis / Config to Order variants)
- Warranty (default: 1 year Parts Warranty)
- Cancellation policy (fixed: Short and Polite)
- Bank details (PHP: BDO · USD: SWIFT) — shown only when toggled

**PDF Generation**
- Professional branded PDF built with ReportLab
- Company logo, signature image of the AE
- Itemized table with GP margin visible only internally
- Terms & Conditions table on final page

**Email Delivery**
- Send PDF directly from CRM to customer's email
- CC field, attachments (files other than costing matrix auto-included)
- HTML email body with company branding

**Approval Workflow**
- Triggered when proposal total ≥ ₱500,000
- Configurable approval tiers (amount range → approval chain)
- Default chain: Supervisor → ASM → AVP
- Step-by-step: each approver must decide before the next is notified
- Approvers access via Approvals Inbox
- Full changelog — every edit recorded with before/after values

**Proposal Status Flow**

```
Draft → Sent → Accepted
                └── Declined
                └── Expired
```

**Approval Status Flow**

```
Not Required
Pending → In Progress → Approved
                     └── Rejected
```

---

## 3. Sales Funnel

### What it does

The Sales Funnel is a pipeline management tool that tracks all active deals from initial quote to closure. It gives management real-time visibility into the value and stage distribution of opportunities across all teams.

### Funnel Stages

| Stage | Color | Description |
|---|---|---|
| **Newly Quoted** | Pink | Fresh quotation submitted, deal just entered pipeline |
| **Closable Deals** | Yellow | High probability deals expected to close this month |
| **Green Funnel** | Green | Project-based, ≥ ₱500,000 SRP |
| **Blue Funnel** | Blue | Services / smaller project, < ₱500,000 SRP |

> Green / Blue classification is **automatic** — the system evaluates the retail value and assigns the stage on save.

### Key Fields per Entry

- Company name, brand, requirement description
- Cost (internal) and Retail/SRP (quoted to customer)
- Profit = Retail − Cost (shown as ₱ and %)
- Expected close date and probability (0–100%)
- Deal outcome: Active · Won · Lost
- Notes (AVP can update notes; email notification sent to AE + Supervisor)
- Link to formal Proposal (retail value auto-syncs from proposal total)

### Dashboard Views by Role

| Role | Scope |
|---|---|
| Salesperson | Own entries only |
| Supervisor / Teamlead | All entries from group members |
| ASM | All entries from assigned teams |
| AVP | All entries across all teams under AVP |
| Admin / President / GM / VP | All entries company-wide |

### Export Options
- Excel export (current filter view)
- PDF fiscal summary (by fiscal quarter)
- CSV import from external spreadsheets

### Deal Outcome Tracking
- Marking a deal **Won** or **Lost** closes it (removed from active pipeline)
- Closed date recorded automatically
- History available in Deals History view

---

## 4. Role-Based Dashboards

### What it does

Every user sees a personalized home dashboard based on their role. Data is always scoped to what the user is responsible for — no role sees data outside their hierarchy.

### Salesperson Dashboard

**Shows:**
- Active Missions (daily and weekly gamification targets)
- Sales Funnel Overview:
  - Total active entries count
  - Newly Quoted count
  - Closable This Month count
  - Project-Based count
  - Total Pipeline Value (₱)
- Recent 5 funnel entries (quick-access table)

**Quick Links:** Add Funnel Entry · View Full Funnel · My Proposals · Customer List

---

### Supervisor Dashboard

**Shows:** Same funnel widgets as salesperson but **scoped to all members of supervised groups** — supervisor sees every entry from every AE in their group(s).

Additional access:
- Pending activities needing supervisor review (Sales Monitoring)
- Group performance metrics

---

### Sales Manager (ASM) Dashboard

**Shows:** Funnel data aggregated across **all groups within assigned teams**.

Additional access:
- Team-level pipeline value breakdown
- All proposal approvals in their chain

---

### AVP Dashboard

**Shows:** Funnel data for **all teams under the AVP**.

Additional access:
- Executive-level pipeline overview
- Approval inbox for proposals ≥ configured threshold
- Can edit Notes on any funnel entry (triggers email to AE + Supervisor)
- Customer create request approvals

---

### Admin Dashboard

**Shows:** Everything, company-wide, plus:

- **Currently Active Users widget** — real-time list of staff logged in within the last 15 minutes, showing name, role, and time since last activity
- Full funnel overview across all teams
- Quick links to User Management and Team Management

---

## 5. Sales Monitoring

### What it does

Sales Monitoring is the activity tracking system. Every client-facing action — calls, meetings, emails, proposals, POCs — is logged here with timestamps, outcomes, and supervisor review notes.

### Activity Types (configurable)

| Type | Sub-types / Details |
|---|---|
| **Call** | Cold / Warm / Follow-up / Demo / Support |
| **Meeting** | Initial / Demo / Proposal Presentation / Negotiation / Closing |
| **Email** | Introduction / Follow-up / Quote / Proposal / Newsletter |
| **Proposal** | Draft / Sent / Under Review / Accepted / Rejected |
| **Task** | Research / Preparation / Documentation / Admin / Training |
| **POC** | Proof of Concept tracking with start/end dates and success criteria |

### Activity Statuses

`Planned → In Progress → Completed`  
`Cancelled / Postponed`

### Key Features

**Activity Logging**
- Title, description, activity type, linked customer
- Scheduled start / end vs actual start / end
- Priority: Low · Medium · High · Urgent
- Follow-up flag with follow-up date
- Notes and outcome

**Supervisor Review**
- Supervisor can annotate activities with notes
- `Engineer Required` flag for client meetings
- Reviewed timestamp recorded

**Meeting Reminder Emails**
- Automated email sent 2 days before a Client Meeting activity
- Recipients: Supervisor + ASM + AVP of the salesperson's team
- Triggered via management command: `python manage.py send_meeting_activity_reminders`

**Monitoring Views by Role**

| Role | View |
|---|---|
| Salesperson | Own activity log and history |
| Supervisor | All activities from supervised group members |
| Teamlead | Group member activities |
| ASM / SM | All activities across assigned teams |
| AVP | All activities across all teams |
| Admin / Exec | Company-wide view |

### Reports & Exports
- Group performance report (Excel + PDF)
- Team performance summary
- Fiscal period summary
- Activity breakdown by type per salesperson

---

## 6. Email Campaigns (Mass Mailing)

### What it does

The Mass Mailing module allows the Marketing team and admins to build, schedule, and send branded email campaigns to CRM customers and leads. It tracks delivery, opt-outs, and recipient interest.

### Campaign Templates

| Template | Use Case |
|---|---|
| **EDM** (Electronic Direct Mail) | Single large product image, clean layout |
| **Newsletter Digest** | Multi-section digest with headline, bullets, side image |

### Campaign Workflow

```
Draft → Scheduled → Sending → Completed
                 └── Cancelled (at any point before Completed)
```

### Key Features

**Building a Campaign**
- Campaign name and email subject line
- Template selection (EDM or Newsletter)
- Hero image uploaded from Media Library or new upload
- Optional: headline, intro text, bullet points, CTA button label + URL
- Recipient selection: CRM Customers or Manual Entry (email list)

**Media Library**
- Centralised image store for reusable campaign assets
- Assets can be tagged as inline (embedded in email) or attachments
- Access restricted to Admin and Marketing roles

**DPA Compliance (R.A. 10173)**
- Every campaign includes an unsubscribe link by default
- Unsubscribed emails stored in OptOut table
- Opted-out recipients automatically skipped on future sends

**Delivery Engine**
- Management command: `python manage.py process_mail_queue`
- Rate-limited (configurable delay between emails)
- Per-recipient status: Pending · Sent · Failed · Opted Out
- Failed emails stored with error message for review
- Inline images embedded as MIME attachments (CID)

**Interest Tracking**
- "Interested — Send More Information" button included in every email
- When clicked: recipient sees an inquiry form (name, company, phone, message)
- On submission: email sent to the campaign creator (AE) with inquiry details
- Interest click recorded with timestamp
- Customer/Lead note automatically added in CRM

**Campaign Detail Dashboard**
- Delivery Statistics: Total Recipients · Sent · Failed · **Interested** (clickable)
- Clicking **Interested** count → filtered list of all interested recipients
- Recipient table: name, email, source, status, sent timestamp, interest badge
- Interest badge shown inline on any recipient who clicked

**Unsubscribe Flow**
- Recipient clicks unsubscribe link in email
- Confirmation page shown
- Email added to OptOut table
- All future campaigns skip this address automatically

**Production URL Requirement**
- All email links (unsubscribe + interested) use `SITE_URL` from `.env`
- Must be set to the server's actual domain before sending campaigns:

```ini
# .env
SITE_URL=https://micrm.microimageph.com
```

**Access by Role**

| Action | Admin | Marketing | Others |
|---|---|---|---|
| Create campaign | ✅ | ✅ | — |
| Send campaign | ✅ | ✅ | — |
| Media Library | ✅ | ✅ | — |
| View campaign detail | ✅ | ✅ | — |
| View interested list | ✅ | ✅ | — |

---

## Admin: Active Users Widget

Available exclusively on the Admin home dashboard.

**How it works:**
- Every page request by a logged-in user updates their `last_activity` timestamp (handled by `UserActivityMiddleware`)
- The dashboard queries all users with `last_activity` within the last **15 minutes**
- No additional database tables — powered entirely by the existing `last_activity` field

**What it shows:**
- User's profile picture or initials avatar
- Full name and username
- Role badge (color-coded by role tier)
- Exact last-seen timestamp
- Human-readable "X minutes ago"

**Configuration:**  
Threshold is controlled in `.env` / `settings.py`:

```python
# crm_project/settings.py
ONLINE_THRESHOLD_MINUTES = 15  # adjust as needed
```

---

## Summary — Modules at a Glance

| Module | URL Prefix | Key Roles |
|---|---|---|
| Customer Database | `/customers/` | All roles (scoped) |
| Sales Proposals | `/proposals/` | Salesperson → Approval chain |
| Sales Funnel | `/funnel/` | Salesperson → AVP |
| Home Dashboard | `/` | All roles (personalized) |
| Sales Monitoring | `/sales-monitoring/` | Salesperson → AVP |
| Email Campaigns | `/mass-mailing/` | Admin, Marketing |
| Lead Generation | `/leads/` | Salesperson, Marketing |
| File Sharing | `/files/` | All sales roles |
| Gamification | `/gamification/` | All sales roles |
| Customer Service | `/service/` | Integrated with Redmine |
| REST API | `/api/v1/` | Android App |

---

*MiCRM · Micro Image International Corp. · July 2026*
