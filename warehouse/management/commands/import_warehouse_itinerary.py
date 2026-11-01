import os
import django
import openpyxl
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from warehouse.models import Delivery, WarehouseStaff

class Command(BaseCommand):
    help = 'Import initial warehouse itinerary data from Excel'

    def handle(self, *args, **options):
        file_path = "WHSE ITINERARY-OCTOBER 30  2026.xlsx"
        if not os.path.exists(file_path):
            self.stderr.write(f"File not found: {file_path}")
            return

        wb = openpyxl.load_workbook(file_path, data_only=True)
        
        # 1. FOR SCHEDULE
        self.import_for_schedule(wb['FOR SCHEDULE'])
        
        # 2. ACCOMPLISHED
        self.import_accomplished(wb['ACCOMPLISHED'])
        
        # 3. SCHEDULED DELIVERY
        self.import_scheduled(wb['SCHEDULED DELIVERY '])

        self.stdout.write(self.style.SUCCESS("Successfully imported warehouse data."))

    def clean_val(self, val):
        if val is None:
            return ""
        return str(val).strip()

    def parse_date(self, date_val):
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, str):
            try:
                return datetime.strptime(date_val, '%m/%d/%Y').date()
            except ValueError:
                pass
        return None

    def import_for_schedule(self, ws):
        self.stdout.write("Importing FOR SCHEDULE...")
        # Headers on row 6
        for row in ws.iter_rows(min_row=7, values_only=True):
            so = self.clean_val(row[0])
            if not so: continue
            
            Delivery.objects.update_or_create(
                so_number=so,
                defaults={
                    'client': self.clean_val(row[1]),
                    'item': self.clean_val(row[2]),
                    'area': self.clean_val(row[3]),
                    'ae': self.clean_val(row[4]),
                    'remarks': self.clean_val(row[5]),
                    'status': Delivery.STATUS_FOR_SCHEDULE,
                }
            )

    def split_driver_staff(self, raw_val):
        """Split 'ROMMEL-BENJIE' into ('ROMMEL', <WarehouseStaff: BENJIE>)"""
        if not raw_val:
            return "", None
        
        driver = raw_val
        staff_obj = None
        
        if "-" in raw_val:
            parts = raw_val.split("-", 1)
            driver = parts[0].strip()
            staff_name = parts[1].strip()
            staff_obj, _ = WarehouseStaff.objects.get_or_create(name=staff_name)
            
        return driver, staff_obj

    def import_accomplished(self, ws):
        self.stdout.write("Importing ACCOMPLISHED...")
        # Date on Row 3, Col 3
        acc_date = self.parse_date(ws.cell(row=3, column=3).value)
        # Headers on row 4
        for row in ws.iter_rows(min_row=5, values_only=True):
            so = self.clean_val(row[0])
            if not so: continue
            
            driver_val, staff_obj = self.split_driver_staff(self.clean_val(row[4]))
            
            Delivery.objects.update_or_create(
                so_number=so,
                defaults={
                    'client': self.clean_val(row[1]),
                    'item': self.clean_val(row[2]),
                    'area': self.clean_val(row[3]),
                    'driver_staff': driver_val,
                    'warehouse_staff': staff_obj,
                    'ae': self.clean_val(row[5]),
                    'remarks': self.clean_val(row[6]),
                    'status': Delivery.STATUS_ACCOMPLISHED,
                    'accomplished_date': acc_date
                }
            )

    def import_scheduled(self, ws):
        self.stdout.write("Importing SCHEDULED DELIVERY...")
        # Date on Row 3, Col 3
        sch_date = self.parse_date(ws.cell(row=3, column=3).value)
        
        # Extract Van Details at the bottom
        van_map = {}
        # Find "VAN DETAILS" row
        van_start_row = 0
        for i in range(1, ws.max_row + 1):
            if self.clean_val(ws.cell(row=i, column=1).value) == "VAN DETAILS":
                van_start_row = i
                break
        
        if van_start_row:
            for i in range(van_start_row + 1, ws.max_row + 1):
                val = self.clean_val(ws.cell(row=i, column=1).value)
                if not val: continue
                # Example: "NIJ 4097 - GERRY/MARLON"
                if " - " in val:
                    plate, driver_staff_raw = val.split(" - ", 1)
                    # Normalize for mapping
                    van_map[driver_staff_raw.replace("/", "-").strip()] = plate.strip()

        # Headers on row 4
        for row in ws.iter_rows(min_row=5, values_only=True):
            so = self.clean_val(row[0])
            if so == "VAN DETAILS": 
                break
            if not so:
                continue
            
            raw_driver_staff = self.clean_val(row[4])
            driver_val, staff_obj = self.split_driver_staff(raw_driver_staff)
            
            # Use the raw string (with hyphen) to look up the plate
            plate = van_map.get(raw_driver_staff.replace("/", "-").strip(), "")
            
            Delivery.objects.update_or_create(
                so_number=so,
                defaults={
                    'client': self.clean_val(row[1]),
                    'item': self.clean_val(row[2]),
                    'area': self.clean_val(row[3]),
                    'driver_staff': driver_val,
                    'warehouse_staff': staff_obj,
                    'vehicle_plate': plate,
                    'ae': self.clean_val(row[5]),
                    'remarks': self.clean_val(row[6]),
                    'status': Delivery.STATUS_SCHEDULED,
                    'scheduled_date': sch_date
                }
            )
