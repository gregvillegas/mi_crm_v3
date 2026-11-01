# Micro Image CRM - User Manual

**Version:** 1.2\
**Date:** April 12, 2026\
**Prepared For:** Micro Image International Corp.

***

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Getting Started](#getting-started)
   - [System Access](#system-access)
   - [User Roles](#user-roles)
   - [Navigation](#navigation)
3. [Dashboard Overview](#dashboard-overview)
4. [Module Guides](#module-guides)
   - [Customer Management](#customer-management)
   - [Lead Generation](#lead-generation)
   - [Sales Funnel](#sales-funnel)
   - [Sales Proposals](#sales-proposals)
   - [Activity Monitoring](#activity-monitoring)
   - [Team Management](#team-management)
   - [Mass Mailing (New!)](#mass-mailing)
   - [Gamification](#gamification)
   - [Customer Service](#customer-service)
   - [File Sharing](#file-sharing)
   - [Warehouse & Deliveries](#warehouse--deliveries)
5. [Analytics & Reporting](#analytics--reporting)
6. [Administration](#administration)

***

## Executive Summary

The **Micro Image CRM** is a comprehensive Customer Relationship Management solution designed specifically for the needs of Micro Image International Corp. It serves as a centralized platform to streamline sales operations, enhance customer engagement, and provide actionable insights through data analytics.

### Key Benefits

- **Unified Customer View**: Consolidates customer data, history, and interactions in one place.
- **Streamlined Sales Process**: From lead generation to proposal creation and deal closing, the entire workflow is digitized.
- **Data-Driven Decisions**: Real-time dashboards and analytics empower executives and managers to make informed decisions.
- **Improved Accountability**: Activity tracking and quota management ensure teams stay on target.
- **Enhanced Motivation**: Gamification features like leaderboards and badges drive performance.

***

## Getting Started

### System Access

Access the CRM via your web browser at the designated URL. Log in using your username and password.

- **Note**: Upon login, you will be greeted with a daily motivational quote to start your day!

### User Roles

The system is tailored to different roles within the organization:

- **Salesperson**: Manage own leads, customers, proposals, and activities.
- **Supervisor**: Oversee a group of salespeople, view group performance.
- **ASM (Area Sales Manager)**: Manage multiple groups/teams, set quotas.
- **AVP (Assistant Vice President)**: Strategic oversight of teams and quotas.
- **Executive (VP/GM/President)**: Full view of company performance and analytics.
- **Technical Sales / Technical Manager**: Manage TSG customers, funnel, and proposals in covered teams.
- **Marketing**: Manages reusable campaign media assets for Mass Mailing.
- **Warehouse**: Maintains the delivery itinerary board (add/update deliveries); sees only the Warehouse module.
- **Admin**: System configuration and user management.

### Navigation

The top navigation bar provides quick access to all major modules:

- **Dashboard**: Your personal command center.
- **Customers**: Database of all clients.
- **Leads**: Lead generation and tracking.
- **Funnel**: Sales pipeline management.
- **Proposals**: Quote generation tool.
- **Activities**: Calendar and activity logs.
- **Teams**: (For Managers) Team structure and quotas.
- **Mass Mailing**: Send personalized bulk emails to clients.
- **Files**: Document repository.
- **Warehouse Deliveries**: (Under Monitoring) Delivery itinerary board, history, and Excel export.

***

## Dashboard Overview

Your dashboard is personalized based on your role:

- **Salesperson**: Shows today's tasks, upcoming appointments, recent leads, and personal performance stats.
- **Manager/Executive**: Displays high-level KPIs, team performance charts, and revenue forecasts.

***

## Module Guides

### Customer Management

- **View Customers**: Browse the searchable customer database.
- **Customer 360 View**: Click on a customer to see their profile, contact persons, activity history, sales funnel, and support tickets.
- **Delinquency Tracking**: Monitor and manage delinquent accounts with color-coded status indicators.
- **Additional Contact Persons**:
  - Add up to 4 additional contacts per customer.
  - Inline validation highlights invalid fields such as malformed email addresses before saving.
  - Existing contacts can be deleted using the **Delete** checkbox; a confirmation prompt appears before marking a contact for deletion.
  - Hidden form tracking is handled automatically, so editing and deleting multiple contact persons now saves correctly.
- **Customer Creation Requests**:
  - Salespeople can submit requests when a possible duplicate customer is detected.
  - Admin/AVP/GM/VP users can review **Pending Requests**, approve or reject them, and record a reason for rejection.
  - A **Requests History** page shows previously approved/rejected customer creation requests for audit reference.

### Lead Generation

- **Dashboard**:
  - Open **Leads** to access the **Lead Generation Dashboard**.
  - Summary cards show:
    - **Total Leads**
    - **Lost Leads**
    - **Hot Leads**
    - **Conversion**
    - **Conversion Rate**
  - The dashboard also includes:
    - **Quick Actions**
    - **Follow-up Required**
    - **Top Performing Lead Sources**
    - **Recent Activity**
- **Capture Leads**:
  - Salespeople can add leads manually from the dashboard or lead list.
  - Leads can also be imported in bulk using CSV.
- **Lead Scoring**:
  - The system calculates a lead score from profile completeness and engagement details.
  - Score bands are used throughout the dashboard:
    - **80+** = Hot
    - **60+** = Warm / ready
    - Below **60** = Cold
  - Leads with a score of **70 or higher** are automatically marked as **Qualified**.
  - Automatic qualification updates the qualified flag, but does not force all pipeline statuses to jump automatically.
- **Lead Detail Actions**:
  - Each lead detail page provides the main outcome actions:
    - **Edit Lead**
    - **Convert to Customer**
    - **Mark as Lost**
    - **Log Activity**
  - The lead header also shows current:
    - status
    - priority
    - score
    - assigned salesperson
- **Mark as Lost**:
  - Use **Mark as Lost** from the lead detail page.
  - A modal asks for:
    - loss reason
    - optional notes
  - After saving:
    - the lead status changes to **Lost**
    - the lead is removed from active conversion flow
    - a lead activity entry is recorded for audit history
- **Conversion**:
  - Use **Convert to Customer** from the lead detail page or lead list when the lead is eligible for conversion.
  - Conversion is available for leads that are officially qualified or already in later sales stages.
  - During conversion, users can:
    - set **Conversion Value**
    - add **Notes**
    - optionally **Create Sales Funnel Entry**
    - choose the initial **Sales Funnel Stage**
  - After conversion:
    - a new customer record is created
    - the lead status changes to **Converted**
    - conversion history is preserved
    - an optional sales funnel record can be created for follow-through deal tracking
  - If a sales funnel entry is requested, the lead should be assigned to a salesperson first.
- **Activities & Follow-up**:
  - Activities logged on the lead appear in the activity timeline.
  - The dashboard **Follow-up Required** panel highlights leads with pending next follow-up dates.
  - **Recent Activity** displays the newest lead updates, including status changes and logged follow-ups.
- **Lead Sources & Analytics**:
  - Managers and executives can review **Top Performing Lead Sources** directly on the dashboard.
  - The analytics area tracks:
    - lead source performance
    - conversion trends
    - acquisition efficiency
- **Import Leads (CSV)**:
  - Navigate to **Leads → Import**.
  - Download the sample template to ensure correct columns.
  - Upload your CSV; optionally auto-calculate lead scores.
  - Role-aware defaults restrict assignment options based on your role.

### Sales Funnel

Manage your sales opportunities through distinct stages:

1. **Pink Funnel (Quoted)**: Initial proposal sent.
2. **Yellow Funnel (Closable)**: High probability of closing.
3. **Green Funnel**: Deals greater than 500K.
4. Blue Funnel: Deals below 500K

- **Pipeline View**: Drag-and-drop interface to move deals across stages.
- **Forecasting**: System calculates expected revenue based on deal probability.

### Sales Proposals

Create professional, branded PDF proposals in minutes, with multi-level approval and tighter data entry controls.

- **Create Proposal**: Select a customer, add items (products/services), and set terms.
- **Customer Filtering**: Salespeople only see customers assigned to them in the Customer dropdown.
- **Date Pickers**: Both Date and Valid until use a date picker for consistent input.
- **Items**:
  - Per-item **Warranty** field replaces Availability; shown in proposal details and the PDF items table. If an item warranty is blank, the proposal’s overall warranty is used.
  - Unit price column spacing adjusted to avoid wrapping. An Item no. column helps track entries.
  - Unit cost/price inputs use plain numeric fields without spinner arrows; values show full amounts with 2 decimals.
  - Margin% now persists between create and edit, preventing rounding shifts on reload.
  - Text Areas: Introduction, Special note, and Closing default to compact 3-line editors for cleaner forms.
  - Attachments: Upload related files on the proposal screen and choose which ones to include when emailing the client.
- **PDF Generation**: Automatically generates a standardized PDF with Micro Image branding.
- **Email Integration**: Send the proposal directly to the client from within the CRM.
  - **Multiple Recipients**: The **Send To** field accepts multiple email addresses separated by commas or semicolons.
  - **CC Support**: Additional CC recipients can still be entered separately.
  - **Cover Letter**: The **Email Customer** screen includes an optional cover letter message box. If left blank, the system uses the default proposal email text.
  - Include selected attachments along with the generated PDF.
- **Currency Support**: Supports both PHP and USD with exchange rate handling.
- **Bank Details by Currency**:
  - When **Include bank details** is enabled, the form shows editable bank details for the selected currency.
  - **PHP** proposals use the PHP bank account block.
  - **USD** proposals use the USD beneficiary/account/SWIFT block.
  - These values are editable per proposal and appear in the generated PDF.
- **Price Validity Options**:
  - In addition to the **Valid until** date, users can optionally enable:
    - **Subject to Prior Sale**
    - **Availability at the time of Order**
  - Selected notes appear under **Price Validity** in the PDF.
- **Approvals**:
  - Proposals at or above configured PHP thresholds require approval before email sending.
  - Multi-level routing (e.g., Supervisor → ASM → AVP/GM) based on amount and team structure.
  - Supervisors/Managers use the **Approvals Inbox** to review, approve, or reject proposals.
  - Email sending is gated until the proposal is fully approved.

### Activity Monitoring

- **Log Activities**: Record calls, meetings, visits, and emails.
- **Calendar**: View your schedule and upcoming tasks.
- **Proof of Concept (POC)**: Track technical POCs and their outcomes.
- **Reports**: Generate daily or weekly activity reports for management.

### Team Management

- **Structure**: Organize users into Groups and Teams.
- **Quota Management (AVP Only)**:
  - AVPs have a dedicated "Quotas" link in the navbar.
  - Manage monthly quotas for ASMs, Supervisors, and Salespeople from a single interface.
 - **Approvals Inbox (Supervisors/Managers/Execs)**: Review proposals awaiting your approval.
 - **Approval Tiers (Exec/Admin)**:
   - Navigate to Proposals → Approval Tiers to configure thresholds and approver chains.
   - Manage tiers via UI; Import/Export CSV supported.
   - Download a ready-made CSV template or click “Seed Defaults” to populate the standard three-tier setup (500k supervisor, 1M supervisor+ASM, 3M supervisor+ASM+AVP/GM).

### Mass Mailing

The Mass Mailing module allows salespersons to send personalized bulk emails to their assigned customers while adhering to Data Privacy Act (DPA) standards and preventing spam.

- **Campaign Creation**: Create email campaigns with custom subject lines and either custom HTML or builder-based templates.
  - **Personalization Tags**: Use `{{ contact_name }}` and `{{ company_name }}` to automatically personalize each email.
  - **Templates**:
    - **Hero Promo**
    - **Product Launch**
    - **Newsletter Digest**
    - plus quick text templates such as Product Updates, Quarterly Check-ins, and Promotions
  - **Builder-First Workflow**:
    - Sales users can choose a layout template, upload/select images, enter headline/intro/bullets/CTA, and preview the final email without writing HTML.
    - The system generates email-safe HTML automatically.
- **Campaign Images**:
  - Upload campaign-specific images directly on the campaign form.
  - Mark images as **Embed inline** to place them inside the email body.
  - Non-inline images are sent as attachments.
- **Marketing Media Library**:
  - A dedicated **Media Library** page allows reusable campaign images to be uploaded once and selected in multiple campaigns.
  - Only **Admin** and **Marketing** users can access and manage the Media Library.
  - Sales users can use the saved images inside campaigns where available, without needing to re-upload them manually.
- **Live Preview**: Click the "Preview" button to see exactly how the email will render in a client's inbox before sending.
- **Inline Image Behavior**:
  - **Hero Promo**: uses the first inline image as the hero/banner image.
  - **Product Launch**: uses the first inline image as the banner and the second inline image as the product image.
  - **Newsletter Digest**: uses the first inline image as the main header image and the second as the side image.
- **DPA Compliance & Opt-Outs**:
  - All emails include a mandatory company footer and a secure "Unsubscribe" link.
  - If a customer unsubscribes, the system automatically adds them to an Opt-Out list and blocks them from receiving future mass mailings.
- **Rate-Limited Sending**: Once scheduled, emails are processed in the background using a rate-limited queue. This prevents server blocking and ensures high deliverability by avoiding spam filters.
- **Tracking**: Monitor the progress of your campaign in real-time on the dashboard (Total Sent, Failed, and Progress %).

### Gamification

- **Leaderboard**: See who the top performers are in real-time.
- **Badges**: Earn badges for achievements (e.g., "Top Closer", "Lead Magnet").
- **Profile**: Upload your profile picture to personalize your leaderboard appearance.

### Customer Service

- **Ticket Integration**: View "Support Tickets" directly in the Customer details page.
- **Redmine Bridge**: Seamlessly fetches ticket status and updates from the Redmine system without needing a separate login.

### File Sharing

- **Repository**: Upload and share important documents (brochures, price lists, forms).
- **Permissions**: Control who can view or download specific files.

### Warehouse & Deliveries

- **Itinerary Board**: Three stacked sections — **For Schedule**, **Scheduled Delivery**, and **Accomplished Delivery** — each with a date picker. Remarks for "For Schedule" items are shown in bold red. A **VAN DETAILS** footer groups the day's items by vehicle plate and driver.
- **Real-Time Updates**: Changes appear instantly on every open board (no refresh needed).
- **Add / Update**: The **Warehouse** role sees a **New Delivery** button and a per-row **edit** link to maintain the itinerary (drivers, plates, warehouse staff, status).
- **Delivery History**: A paginated log of all scheduled, accomplished, and **backlog** items with columns Date, Status, Company, Item, AE, Driver, and Warehouse Staff — useful for driver/staff KPI and backlog tracing.
- **Backlog Tracing**: When an item is moved back from Scheduled/Accomplished to For Schedule, it is flagged **BACKLOG** (with a move count) so recurring delays are recorded.
- **Excel Export**: Download the board as a workbook with one sheet per section. Export is available to all viewers **except** the Account Manager (salesperson) role.
- **Warehouse role access**: Warehouse users are soft-locked to this module — their navbar shows only Warehouse Deliveries and Delivery History.

> Full technical details are in [WAREHOUSE_APP.md](WAREHOUSE_APP.md).

***

## Analytics & Reporting

- **Executive Dashboard**: A bird's-eye view of the company's health, including total revenue, active deals, and team comparisons.
- **Sales Reports**: Detailed breakdown of sales performance by product, region, or salesperson.
- **Export**: Most reports can be exported to CSV/Excel for further analysis.

***

## Administration

- **User Management**: Create and manage user accounts.
- **Import Tool**: Use the `import_users` command-line tool to bulk onboard users from JSON.
  - *New*: Supports filtering by role (e.g., import only salespeople).
- **System Configuration**: Manage dropdown options, lead sources, approval tiers, and global settings.
- **Approvals Configuration**:
  - Use the **Approval Tiers** screen to adjust thresholds and chains without code changes.
  - Export the current tiers, edit offline, and import to update in bulk.

***

**Micro Image International Corp.**\
*Empowering Business through Technology*
