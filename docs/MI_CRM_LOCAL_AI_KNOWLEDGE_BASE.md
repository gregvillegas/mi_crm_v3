# MI CRM Knowledge Base Master Document

Document type: Upload-ready master knowledge base file for Local AI / MIICiQ
Recommended filename when uploading: `MI_CRM_Knowledge_Base_Master.md`
Recommended category: `Company Policy` or `System Documentation`
Recommended department: `All`
Recommended access role: `All Employees` or role-scoped if needed

---

## 1. Purpose of this document

This document is the main AI-friendly overview of the **Micro Image CRM (MI CRM)** application.

It is designed to help a local AI assistant answer common questions such as:

- What modules exist in MI CRM?
- How do users navigate the CRM?
- What does each role see and manage?
- How do I create customers, proposals, funnel entries, activities, and tickets?
- How do approvals work?
- What are the key business rules?
- Where should the AI look for deeper detail?

This file is a **master summary**, not the only source. It should be uploaded together with the deeper app documents already available in the `docs/` folder.

---

## 2. What MI CRM is

**MI CRM** is a Django-based internal CRM for Micro Image International Corp. It supports the sales lifecycle from lead generation to customer management, proposals, sales funnel tracking, activity monitoring, reporting, support ticket creation, file sharing, and role-based management oversight.

Main technology notes:

- Backend: Django
- Database: SQLite in local development, MariaDB in production
- Frontend: Django templates + Bootstrap
- PDF generation: ReportLab
- Excel exports: openpyxl
- Authentication: django-allauth + MFA/TOTP
- API: Django REST Framework

Main URL areas:

- `/` = Home / dashboard
- `/customers/` = Customers
- `/teams/` = Teams and groups
- `/funnel/` = Sales funnel
- `/sales-monitoring/` = Activity monitoring and dashboards
- `/leads/` = Lead generation
- `/proposals/` = Sales proposals
- `/files/` = Group file sharing
- `/service/` = Customer service tickets
- `/gamification/` = Leaderboard and rewards
- `/mass-mailing/` = Email campaigns
- `/users/` = User management
- `/accounts/` = Login, password reset, MFA
- `/api/v1/` = REST API

---

## 3. Core user roles

The CRM uses a role field on the User model. Typical roles:

- `admin` = full system access
- `president` = executive read access
- `vp` = executive read access
- `gm` = executive read access
- `avp` = team-level management and approvals
- `asm` = area sales manager; handles scoped groups/teams
- `sm` = sales manager; scoped to assigned groups
- `supervisor` = group supervisor
- `teamlead` = lead role with narrower group scope
- `salesperson` = own customers, proposals, funnel, activities
- `marketing` = marketing and campaign-related access
- `techmgr` / `asst_techmgr` = technical sales group roles

Simple rule of thumb:

- **Salesperson** sees and edits mostly their own records.
- **Supervisor / Teamlead / SM / ASM / AVP** see records based on team/group hierarchy.
- **Admin / GM / VP / President** usually have full company visibility.

---

## 4. High-level module map

### 4.1 Home dashboard

The home page is role-aware. It shows summary cards, quick actions, and links into the major modules.

Typical use:

- Daily check-in
- Review reminders and notifications
- Jump to customers, funnel, proposals, or monitoring

### 4.2 Customers

The Customers module stores:

- company records
- main contact person
- additional contact persons
- email, phone, address
- industry and territory
- assigned salesperson
- notes, backups, and history
- delinquency data

Key customer capabilities:

- searchable customer list
- customer profile / 360 view
- add and edit customers
- add up to 4 extra contacts
- transfer customer ownership
- view notes and history
- import/export customers
- duplicate detection and customer creation approval workflow

### 4.3 Teams and Groups

The Teams module manages the sales hierarchy:

- Team
- Group
- TeamMembership
- AVP / ASM / Supervisor / SM relationships
- quota and commitment records

This hierarchy is important because many permissions in **Customers**, **Sales Funnel**, and **Sales Proposals** depend on it.

### 4.4 Sales Funnel

The Sales Funnel tracks sales opportunities from active pipeline to won/lost closure.

Main funnel stages:

- `quoted` = Pink Funnel / Newly Quoted
- `closable` = Yellow Funnel / Closable Deals
- `project` = Green Funnel
- `services` = Blue Funnel

Key fields:

- company
- requirement description
- cost
- retail / SRP
- salesperson
- stage
- probability
- notes
- won/lost outcome
- lost reason

### 4.5 Sales Monitoring

Sales Monitoring tracks sales activities and performance reporting.

Examples:

- create activity
- quick log activity
- create POC
- calendar view
- reports
- group performance
- team performance
- executive dashboard
- fiscal year comparison

### 4.6 Sales Proposals

The Proposals module creates customer quotations and branded PDFs.

Main capabilities:

- draft proposals
- add line items
- optional items
- bundled items
- multi-option proposals
- approval workflow
- PDF generation
- email customer
- auto-sync with sales funnel

### 4.7 Lead Generation

Lead Generation supports:

- lead capture
- lead scoring
- follow-up tracking
- conversion to customer
- optional conversion into sales funnel entry
- source analytics

### 4.8 Customer Service

Customer Service integrates with Redmine-based support ticketing.

Users can:

- create a ticket from a customer
- view ticket detail
- sync ticket status

### 4.9 File Sharing

File Sharing lets groups upload and share files.

Examples:

- proposal templates
- contracts
- presentations
- forms
- training materials
- internal references

### 4.10 Mass Mailing

Mass Mailing supports campaign creation and email sending to customer lists.

### 4.11 Gamification

Gamification provides:

- leaderboard
- missions
- badges
- motivation and performance recognition

### 4.12 Users, password reset, and MFA

The Users area supports:

- user management
- admin actions
- password reset link sending
- MFA reset
- role assignment

Authentication notes:

- login uses django-allauth
- MFA/TOTP is enabled
- self-service password reset is available

---

## 5. Typical business workflows

### 5.1 Lead to customer workflow

Typical path:

1. User creates or imports a lead in `Leads`
2. Lead is scored and followed up
3. Qualified lead is converted to a customer
4. Optional funnel entry is created during conversion
5. Proposal may later be created for that customer

### 5.2 Proposal to funnel workflow

Typical path:

1. Salesperson creates proposal
2. Proposal items and terms are prepared
3. Approval workflow runs if threshold requires it
4. Proposal PDF is generated and sent
5. Proposal is linked to a sales funnel entry
6. Funnel entry moves through stages
7. Deal is closed as won or lost

Important rule:

- Proposal updates can create or sync a related funnel entry automatically.

### 5.3 Customer request approval workflow

When a salesperson tries to create a customer that looks like a duplicate:

1. System checks similar company names
2. If a likely duplicate exists, customer is not created immediately
3. A `CustomerCreateRequest` is created instead
4. AVP or executive approver reviews it
5. Request is approved or rejected

### 5.4 Funnel close workflow

When a deal is finished:

- mark it as **Won** or **Lost**
- if **Lost**, a reason should be recorded
- the deal moves out of active pipeline and remains available in history/reporting

Important rule:

- Lost reasons are important for coaching and win/loss analysis.

### 5.5 Customer service workflow

1. Open a customer
2. Create a support ticket
3. Monitor ticket detail
4. Sync ticket status from Redmine

---

## 6. Important role and visibility rules

These are common support questions and the AI should answer them carefully.

### 6.1 Customers visibility

- Salesperson sees only their own customers
- Supervisor sees customers of their group plus own
- AVP sees customers across managed teams
- ASM and SM see customers based on their scoped groups/teams
- Executives and admin usually see all customers

### 6.2 Funnel visibility

- Salesperson sees own funnel entries
- Managers see entries from scoped team/group members
- Executives/admin see all

### 6.3 Proposal visibility

- Proposal scope is based mainly on `Proposal.created_by`
- Salesperson sees own proposals
- Managers see proposals from scoped members
- AVP visibility includes team members and related managers in scope
- Executives/admin see all proposals

### 6.4 Approval visibility

- AVP and executive-level approvers handle customer-create approvals within scope
- Proposal approvals depend on approval tiers and team/group structure
- Watcher roles may see requests but not always decide them

---

## 7. Common module questions and answers

This section is intentionally written in AI-friendly Q&A form.

### 7.1 Customers

**Q: How do I add a customer?**  
A: Go to `Customers`, use the create/add action, fill in company and contact details, assign the salesperson if allowed by your role, and save. If the system detects a possible duplicate for a salesperson, it may create a customer request for approval instead of saving immediately.

**Q: Why was my customer not created immediately?**  
A: The duplicate-check workflow likely detected a similar customer name. Salespeople may trigger a `CustomerCreateRequest` for AVP or executive review instead of direct creation.

**Q: Can I transfer a customer to another salesperson?**  
A: Yes, if your role has customer-management rights. Customer reassignment is controlled by role and scope.

**Q: How many extra contact persons can a customer have?**  
A: Up to 4 additional contacts.

**Q: Can the CRM detect duplicate customers?**  
A: Yes. It normalizes company names and compares similarity. There is also a duplicates filter for managers.

### 7.2 Sales Funnel

**Q: What do the funnel colors mean?**  
A: Pink = newly quoted, Yellow = closable, Green = project-based/high-value, Blue = services/lower-value category.

**Q: How is Green vs Blue decided?**  
A: For open entries in `project/services`, the system uses the SRP threshold rule: deals at or above about `PHP 500,000` go to Green; lower-value ones go to Blue.

**Q: What happens when I mark a deal as lost?**  
A: The entry becomes a closed lost deal, it leaves the active pipeline, and the lost reason should be stored for reporting and lessons learned.

**Q: What should I do instead of deleting a real funnel entry?**  
A: Prefer close or remove/archive behavior rather than hard deletion, because hard deletion can damage reporting history.

### 7.3 Deals History

**Q: What is Deals History for?**  
A: It shows closed won and lost deals, win rate, deal values, recent closures, and summary statistics.

**Q: Can I see all won deals or all lost deals?**  
A: Yes. The Won Deals and Lost Deals cards can open dedicated detail pages listing all records in that outcome.

**Q: Does the Lost Deals page show the reason?**  
A: Yes. The lost-deals detail page includes a `Reason` column.

### 7.4 Sales Proposals

**Q: How do I create a proposal?**  
A: Go to `Proposals`, create a draft, choose the customer, add items, set terms, and save.

**Q: What is the difference between a single-format and multi-option proposal?**  
A: Single-format proposals present one main pricing structure. Multi-option proposals present separate option groups such as Option 1, Option 2, and Option 3 with independent totals.

**Q: Can a proposal generate a PDF?**  
A: Yes. The system generates a branded proposal PDF.

**Q: Can I email the proposal directly from the CRM?**  
A: Yes. The email flow can attach the generated PDF and selected attachments.

**Q: Why can’t I send the proposal yet?**  
A: It may require approval first based on configured amount thresholds and approval chain logic.

**Q: What are optional proposal items?**  
A: Optional items are shown to the customer but excluded from the main binding total.

### 7.5 Sales Monitoring

**Q: What can I log in Sales Monitoring?**  
A: Calls, meetings, visits, POCs, and related sales activities.

**Q: Are there role-specific dashboards?**  
A: Yes. Salesperson, supervisor, admin, and executive users get different dashboards and reporting views.

**Q: What is the Executive Dashboard?**  
A: A high-level performance dashboard for admin/GM/VP/president-level users with KPI cards, group performance, funnel overview, and individual performance rankings.

### 7.6 Lead Generation

**Q: Can a lead become a customer directly?**  
A: Yes. Qualified leads can be converted into customers, with optional funnel entry creation.

**Q: Does the CRM score leads automatically?**  
A: Yes. The lead-generation module includes automated scoring and qualification rules.

### 7.7 File Sharing

**Q: Who can access shared files?**  
A: Access is group-based and role-scoped. Executives can see more broadly; regular users usually see files from their own group.

**Q: What file types can be uploaded?**  
A: Common office documents, PDFs, text files, images, and archives, subject to configured validation and size limits.

### 7.8 Authentication and security

**Q: What if a user forgets their password?**  
A: They should use the self-service password reset via the login page.

**Q: Can an admin directly type a new password for a user?**  
A: The preferred approach is sending a reset link rather than manually setting a password.

**Q: What if a user loses their MFA authenticator?**  
A: An admin can reset MFA after identity verification.

---

## 8. Important business rules the AI should know

These rules matter because users often ask questions that depend on them.

### 8.1 Duplicate customer handling

- Duplicate customer prevention is not only based on exact company-name match
- Similar-name detection can trigger an approval request instead of direct creation

### 8.2 Millionaire and active/inactive customer status

- Customers may be classified with system-managed flags such as millionaire account or inactive status
- Some dashboards and filters use these flags

### 8.3 Funnel reporting depends on real surviving data

- Won/lost statistics and executive reporting depend on preserved funnel data
- Hard deletion of real won deals is dangerous because it removes historical revenue from reports

### 8.4 Lost reason is valuable

- A lost deal should include a reason
- Lost reasons support coaching, trend analysis, and win/loss improvement

### 8.5 Proposal approval is separate from proposal status

- A proposal can still be a draft while approval is pending
- Email sending may be blocked until approval completes

### 8.6 Proposal-linked funnel entries can auto-sync

- Funnel entries linked to proposals may update when the proposal changes

### 8.7 Team hierarchy drives visibility

- Team, group, supervisor, AVP, ASM, and SM relationships are central to access control

---

## 9. How to use lost-deal reasons to improve win rate

This section is for coaching and management questions.

Recommended practice:

1. Collect a clear lost reason for every lost deal
2. Group reasons into categories such as:
   - price too high
   - competitor won
   - no budget
   - timing delayed
   - wrong specs / requirement mismatch
   - client chose incumbent supplier
   - internal follow-up delay
3. Review those reasons monthly by:
   - salesperson
   - team/group
   - product brand
   - deal size
4. Turn frequent patterns into action:
   - if many losses are price-related, improve qualification and pricing strategy
   - if many are competitor-related, build objection-handling playbooks
   - if many are spec mismatch, improve solution discovery earlier
   - if many are timing/no budget, improve follow-up and reactivation strategy
5. Use top reasons as training topics for supervisors and AVPs

Good AI answer pattern:

- explain the top loss category
- compare it with sales stage or team
- recommend one concrete coaching action

---

## 10. Common URLs and navigation shortcuts

Main routes:

- `/` = home
- `/customers/`
- `/teams/`
- `/funnel/`
- `/funnel/deals-history/`
- `/sales-monitoring/`
- `/sales-monitoring/executive/`
- `/proposals/`
- `/leads/`
- `/files/`
- `/service/`
- `/mass-mailing/`
- `/gamification/`
- `/users/`
- `/accounts/login/`
- `/accounts/password/reset/`

API routes:

- `/api/v1/users/`
- `/api/v1/customers/`
- `/api/v1/customer-requests/`
- `/api/v1/funnel/`
- `/api/v1/proposals/`
- `/api/v1/activities/`
- `/api/v1/campaigns/`

---

## 11. Recommended companion documents to upload with this master file

For the best Local AI results, upload this file together with these existing docs:

### Highest-priority companion docs

- `docs/CRM_USER_MANUAL.md`
- `docs/CUSTOMERS_APP.md`
- `docs/SALES_FUNNEL_DOCUMENTATION.md`
- `docs/SALES_PROPOSALS_DOCUMENTATION.md`
- `docs/TEAMS_APP.md`
- `docs/EXECUTIVE_DASHBOARD_README.md`
- `docs/PASSWORD_RESET_AND_MFA.md`
- `docs/FILE_SHARING_README.md`
- `docs/HANDOVER_GUIDE.md`

### Useful operational and special-topic docs

- `docs/CUSTOMER_STATUS_SYNC.md`
- `docs/FISCAL_YEAR_WORKFLOW.md`
- `docs/SALES_MANAGER_GROUP_SCOPING.md`
- `docs/LEAD_GENERATION_GUIDE.md`
- `docs/PROPOSAL_OPTIONAL_ITEMS_APPROVAL.md`
- `docs/PROPOSAL_REJECTION_HANDLING.md`
- `docs/PROPOSAL_HIDE_PART_NUMBER_PLAN.md`
- `docs/MULTI_OPTION_PROPOSAL_PLAN.md`
- `docs/GROUP_PERFORMANCE_FEATURE.md`
- `docs/SALES_MONITORING_MEETING_REMINDERS.md`
- `docs/ADMIN_SETUP.md`

---

## 12. Suggested AI answering rules

If this document is uploaded into a local AI knowledge base, the AI should follow these guidelines:

1. Answer based on documented behavior in MI CRM
2. Prefer current, implemented behavior over old plans
3. If a feature is only proposed or planned, explicitly say it is planned and not necessarily live
4. If the answer depends on role, explain the role difference
5. If the answer depends on team/group scope, mention that hierarchy matters
6. When relevant, mention the exact module or page name the user should open
7. For proposal, funnel, customer, and approval questions, mention related business rules
8. If the documentation does not confirm something, say it is not documented instead of guessing

---

## 13. Known limitations and caution points

- Some documents in `docs/` are plans or proposals, not always shipped features
- Deleting real funnel data can affect historical reporting
- Duplicate customer merge is discussed in analysis docs but is not necessarily implemented
- Proposal approval behavior depends on configured tiers and hierarchy
- Some views are role-scoped and may appear different to different users

---

## 14. Best-use questions this knowledge base should answer well

Examples of questions the AI should be able to answer after ingesting this file and companion docs:

- How do I create a customer in MI CRM?
- Why did my customer creation become a pending request?
- What is the difference between Won and Lost deals history?
- What does the Win Rate card mean?
- How do I create a proposal and send its PDF?
- Why does my proposal need approval?
- How do optional items work in proposals?
- How does the sales funnel decide Green vs Blue?
- What happens when a deal is marked lost?
- Where can I see the lost reason?
- What can an AVP see versus a Supervisor?
- How do I reset a user’s password or MFA?
- How do I upload a file for my group?
- How do I create a support ticket from a customer?
- What dashboards are available to executives?

---

## 15. Summary

This document is the **AI-friendly master overview** of MI CRM.

Use it as:

- the first document to upload
- the top-level orientation layer for Local AI
- the connector between module-specific docs already stored in `docs/`

Best practice:

- upload this file first
- upload the highest-priority companion documents next
- rebuild the vector index after upload

