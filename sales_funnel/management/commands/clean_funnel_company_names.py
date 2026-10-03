"""
Normalize Sales Funnel ``company_name`` values that have a contact person's name
appended in parentheses.

Historically some funnel entries were created (via CSV import / older proposal
data) with the contact baked into the company field, e.g.

    "FUJIFILM PHILIPPINES INC (Sam Christian Oronico)"

while the linked Customer record holds the clean name ("FUJIFILM PHILIPPINES
INC"). New entries created via ``update_sales_funnel()`` already copy the clean
customer name, so this command backfills the old rows.

SAFE BY DESIGN — it only rewrites an entry when ALL of the following hold:
  * the entry has a linked customer, AND
  * the funnel name STARTS WITH the clean customer name (case-insensitive), AND
  * the funnel name is longer (i.e. it only *adds* a trailing suffix), AND
  * the extra suffix is a trailing ``( ... )`` group.

This guarantees legitimate parentheses that are part of the real name — e.g.
"CCL PHARMACEUTICALS (PHILIPPINES), INC" or "DE HEUS PHILIPPINES (CJ PHILS)" —
are preserved; only the trailing contact suffix is dropped. Entries whose name
genuinely differs from the customer (case/spelling/wrong link) are left alone.

Dry-run by default. Pass --apply to write changes.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from sales_funnel.models import SalesFunnel

# A trailing "( ... )" group (optionally with surrounding spaces) at the very end.
TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")


class Command(BaseCommand):
    help = "Strip a trailing contact-name '(...)' from funnel company_name, using the linked customer's clean name."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write the changes. Without this flag the command only reports (dry-run).',
        )

    def handle(self, *args, **options):
        apply = options['apply']

        entries = (
            SalesFunnel.objects
            .filter(customer__isnull=False)
            .select_related('customer')
        )

        to_fix = []
        for e in entries:
            clean = (e.customer.company_name or '').strip()
            current = (e.company_name or '').strip()
            if not clean or current == clean:
                continue
            # Only touch "clean name + trailing suffix" rows.
            if not current.upper().startswith(clean.upper()):
                continue
            if len(current) <= len(clean):
                continue
            remainder = current[len(clean):]
            # The extra part must be exactly a trailing parenthetical group
            # (e.g. " (Sam Oronico)"), not some other distinguishing text.
            if not TRAILING_PAREN.fullmatch(remainder):
                continue
            to_fix.append((e, current, clean))

        self.stdout.write(
            f"Linked funnel entries scanned: {entries.count()}"
        )
        self.stdout.write(
            f"Entries with a trailing contact suffix to normalize: {len(to_fix)}"
        )
        for e, current, clean in to_fix[:50]:
            self.stdout.write(f"  #{e.id}: {current!r}  ->  {clean!r}")
        if len(to_fix) > 50:
            self.stdout.write(f"  ... and {len(to_fix) - 50} more")

        if not to_fix:
            self.stdout.write(self.style.SUCCESS("Nothing to change."))
            return

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nDRY RUN — no changes written. Re-run with --apply to commit."
            ))
            return

        with transaction.atomic():
            for e, current, clean in to_fix:
                e.company_name = clean
                e.save(update_fields=['company_name'])

        self.stdout.write(self.style.SUCCESS(
            f"\nUpdated {len(to_fix)} funnel entries."
        ))
