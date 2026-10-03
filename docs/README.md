All readme files are in folder "docs"
python modules requirements are in folder "dependencies"


Summary

I've resolved both of your issues:

✅ Issue 1: Admin Portal Login Fixed
•  Problem: The 'admin' user wasn't configured as a Django superuser
•  Solution: Updated the admin user to have is_superuser=True and is_staff=True, and ensured the password is properly hashed
•  Credentials: Username: admin, Password: admin123

✅ Issue 2: Team Creation Fixed  
•  Problem: Team creation requires an AVP user, but only admin role existed
•  Solution: Created an AVP user that can be assigned to teams
•  New AVP User: Username: avp_user, Password: avp123

Additional Users Created
I also created additional users to help you test the complete team hierarchy:
•  Supervisor: Username: supervisor_user, Password: supervisor123
•  Salesperson: Username: salesperson_user, Password: sales123

Current User List
How to Test

1. Admin Portal: Visit http://127.0.0.1:8000/admin/ and login with:
•  Username: admin
•  Password: admin123
2. Team Creation: Now you can create teams because you have an AVP user (avp_user) available to assign as the team manager.
3. Complete Workflow: You can now test the full hierarchy:
•  Admin creates teams and assigns AVP users
•  Teams can have groups managed by supervisors  
•  Salespeople can be assigned to groups

The system should now work as expected for both admin access and team management functionality.


---

## Feature Guides

- **[TEAMS_APP.md](TEAMS_APP.md)** — How the Teams app works (Team → Group → TeamMembership hierarchy, plus quota/commitment models) and a full breakdown of what **AVP, SM, ASM, and Supervisor** can see and do across **Customers, Sales Funnel, and Proposals** — including the customer create-request approvals (AVP scoped to their own team) and the proposal approval chain (Supervisor → SM-if-required → AVP). Includes an at-a-glance permissions matrix.
- **[SALES_MANAGER_GROUP_SCOPING.md](SALES_MANAGER_GROUP_SCOPING.md)** — How a Sales Manager (role `asm`) is scoped to only the groups they handle across Teams, Sales Monitoring, and Sales Proposals (the shared `asm_scoped_groups()` helper, Option A whole-team fallback), what changed, and a **no-code playbook** for assigning another group to a Sales Manager via the Edit Group screen / Django admin (with a data-migration option for scripted rollouts).
- **[CUSTOMERS_APP.md](CUSTOMERS_APP.md)** — How the Customers app works, with a deep dive on duplicate management (normalization, similarity scoring, the "Show Duplicates" filter) and how the create-request approval workflow notifies the AVP/approvers. References the merge design in CUSTOMER_MERGE_ANALYSIS.md.
- **[SALES_FUNNEL_DOCUMENTATION.md](SALES_FUNNEL_DOCUMENTATION.md)** — How the Sales Funnel works (the four Pink/Yellow/Green/Blue stages, the ₱500K Green-vs-Blue rule, how entries are created manually/from proposals/CSV, and the move→close lifecycle). **Details exactly what happens when a funnel entry is deleted** — a permanent hard delete with no audit trail that erases won-deal revenue from all reports — plus the FK cascade behavior, a permissions matrix, a best-practice workflow (close vs delete), and suggested guardrails for sign-off.
- **[CUSTOMER_MERGE_ANALYSIS.md](CUSTOMER_MERGE_ANALYSIS.md)** — Design/feasibility analysis for merging duplicate customers (not yet implemented).

## Proposals (for review/approval)

- **[PROPOSAL_DESCRIPTION_LENGTH_PLAN.md](PROPOSAL_DESCRIPTION_LENGTH_PLAN.md)** — Plan to prevent over-long item descriptions (users pasting 2,000+ char raw spec dumps) that produce ugly/oversized PDF cells: a defense-in-depth character cap (model save net + form validation + UI counter/maxlength), keeping the `splitInRow` PDF safety net, and a report of existing over-limit items for cleanup. No code changed yet.
- **[PROPOSAL_REJECTION_HANDLING.md](PROPOSAL_REJECTION_HANDLING.md)** — What happens to a rejected sales proposal (it can be edited, and editing auto-resets the approval workflow), the edge cases (e.g. trimming under the ₱500K threshold bypasses approval), and proposed options for management sign-off.
- **[PROPOSAL_OPTIONAL_ITEMS_APPROVAL.md](PROPOSAL_OPTIONAL_ITEMS_APPROVAL.md)** — Why proposals whose value comes from "Optional" line items skip the ₱500K approval threshold (optional items are excluded from the binding total used for approval), with options for management sign-off.
- **[BIOMETRIC_AUTHENTICATION_PROPOSAL.md](BIOMETRIC_AUTHENTICATION_PROPOSAL.md)** — Feasibility & phased implementation plan for biometric login (WebAuthn/Passkeys via existing django-allauth). For management review and sign-off; no code changed yet.
- **[BIOMETRIC_ENROLLMENT_STAFF_GUIDE.md](BIOMETRIC_ENROLLMENT_STAFF_GUIDE.md)** — 1-page staff how-to for enrolling a device (Touch ID / Face ID / Windows Hello / Android) and signing in with biometrics. Ready for the Phase 1 pilot once approved.

## Marketing (Mass Mailing)

- **[MARKETING_ANNOUNCEMENTS_VISIBILITY_PLAN.md](MARKETING_ANNOUNCEMENTS_VISIBILITY_PLAN.md)** — Plan (for review/approval) to let salespeople and all roles **view** Marketing's announcements/events and know when a new announcement/event/EDM/promo is posted. Reuses the existing `Announcement` model + the notification-bell pattern; proposes a read-only feed page and a per-user unread "Marketing Updates" bell count. No code changed yet.

## Security

- **[PASSWORD_RESET_AND_MFA.md](PASSWORD_RESET_AND_MFA.md)** — **(As built)** How password reset & MFA recovery work: self-service "Forgot Password?" (branded pages, single-use links), admin "Send Reset Link" and gated "Reset MFA" (admin-only, audited via `PasswordResetAudit`), rate limits + anti-enumeration, reset emails from `no-reply@microimageph.com` showing "MI CRM", and operations notes.
- **[PASSWORD_RESET_SECURITY_PLAN.md](PASSWORD_RESET_SECURITY_PLAN.md)** — Decision record / rationale behind the reset design (now ✅ implemented; the optional "Set Temporary Password" was intentionally skipped).

## Maintenance & Operations

- **[ACTIVITY_LOG_ARCHIVING.md](ACTIVITY_LOG_ARCHIVING.md)** — Archive old `UserActivityLog` records to compressed files (and restore them later) to keep the database lean. Includes the `archive_activity_logs` management command and recommended cron setup.
