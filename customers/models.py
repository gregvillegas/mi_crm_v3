from django.db import models
from users.models import User
import json
from django.utils import timezone
from django.utils.dateparse import parse_datetime

class DelinquentCustomer(models.Model):
    company_name = models.CharField(max_length=200)
    assigned_ae = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['email']),
        ]
        unique_together = (('company_name', 'email'),)

    def __str__(self):
        return self.company_name

class Customer(models.Model):
    INDUSTRY_CHOICES = [
		('agriculture','Agriculture & Agribusiness'),
		('automotive','Automotive'),
		('business','BPO'),
		('construction','Construction & Engineering'),
		('defense','Defense & Security'),
		('digital','Digital Services / IT Services'),
		('education','Education & Training'),
		('energy','Energy & Power'),
		('financial','Financial Services & Banking'),
		('government','Government & Public Sector'),
		('healthcare','Healthcare & Medical Services'),
		('hospitality','Hospitality & Tourism'),
		('manufacturing','Manufacturing'),
		('media','Media, Entertainment & Publishing'),
		('mining','Mining & Quarrying'),
		('pharmaceuticals','Pharmaceuticals & Life Sciences'),
		('realestate','Real Estate & Property Development'),
		('retail','Retail & E-commerce'),
		('general','General Services'),
		('technology','Technology <Hardware & Software>'),
		('telecommunications','Telecommunications'),
		('transportation','Transportation & Logistics'),
		('utilities','Utilities <Water, Gas, Electricity>'),
		('wholesale','Wholesale & Distribution'),
		('others','Others'),
    ]
    
    TERRITORY_CHOICES = [
		('caloocan','Caloocan'),
		('laspinas','Las Piñas'),
		('makati','Makati'),
		('malabon','Malabon'),
		('mandaluyong','Mandaluyong'),
		('manila','Manila'),
		('marikina','Marikina'),
		('muntinlupa','Muntinlupa'),
		('navotas','Navotas'),
        ('novaliches','Novaliches'),
		('paranaque','Parañaque'),
		('pasay','Pasay'),
		('pasig','Pasig'),
		('quezoncity','Quezon City'),
		('sanjuan','San Juan'),
		('taguig','Taguig'),
		('valenzuela','Valenzuela'),
        ('laguna','Laguna'),
        ('batangas','Batangas'),
        ('cavite','Cavite'),
        ('isabela','Isabela'),
        ('rizal','Rizal'),
        ('bicol','Bicol'),
        ('nuevaecija','Nueva Ecija'),
        ('tarlac','Tarlac'),
        ('pampanga','Pampanga'),
        ('baguio','Baguio'),
        ('cebu','Cebu'),
        ('calabarzon','Calabarzon'),
		('outsidencr','Outside NCR'),
        ('overseas','Overseas'),
    ]
    
    # Basic Information
    company_name = models.CharField(max_length=255)
    contact_person_name = models.CharField(max_length=100)
    contact_person_position = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Contact person's job title or position"
    )
    email = models.EmailField()
    phone_number = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    
    # Business Information
    industry = models.CharField(
        max_length=50, 
        choices=INDUSTRY_CHOICES, 
        blank=True,
        help_text="Customer's industry sector"
    )
    territory = models.CharField(
        max_length=50, 
        choices=TERRITORY_CHOICES, 
        blank=True,
        help_text="Geographic territory/area"
    )
    
    # Status and Classification
    is_vip = models.BooleanField(
        default=False, 
        verbose_name='VIP/Millionaire Account',
        help_text='Mark as VIP or high-value millionaire account for special handling'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Designates whether this customer account is active'
    )
    is_millionaire_account = models.BooleanField(
        default=False,
        help_text='System-managed flag based on cumulative won revenue above 1,000,000'
    )
    auto_inactive_flag = models.BooleanField(
        default=False,
        help_text='System-managed flag when no sales activity is created within the configured period'
    )
    last_sales_activity_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Most recent sales activity creation date for this customer'
    )
    lifetime_won_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text='System-managed cumulative won revenue from sales funnel entries'
    )
    status_last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time automatic customer status fields were synchronized'
    )
    
    # Assignment
    salesperson = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customers', 
        limit_choices_to={'role__in': ['salesperson', 'supervisor', 'asm', 'sm', 'avp'], 'is_active': True}
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_vip']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_millionaire_account']),
            models.Index(fields=['auto_inactive_flag']),
            models.Index(fields=['industry']),
            models.Index(fields=['territory']),
        ]

    def __str__(self):
        status_indicators = []
        if self.is_millionaire_account:
            status_indicators.append('MILLIONAIRE')
        if not self.is_effectively_active:
            status_indicators.append('INACTIVE')
        
        name = f"{self.company_name} ({self.contact_person_name})"
        if status_indicators:
            name += f" [{', '.join(status_indicators)}]"
        return name
    
    @property
    def full_name(self):
        return f"{self.company_name} ({self.contact_person_name})"

    @property
    def is_effectively_active(self):
        return self.is_active and not self.auto_inactive_flag
    
    @property
    def display_status(self):
        """Return a human-readable status string"""
        if self.is_millionaire_account and self.is_effectively_active:
            return "Millionaire Active"
        elif self.is_millionaire_account and not self.is_effectively_active:
            return "Millionaire Inactive"
        elif self.is_effectively_active:
            return "Active"
        else:
            return "Inactive"
    
    def create_backup(self, changed_by, reason="Manual backup"):
        """Create a backup of the current customer state"""
        backup_data = {
            'company_name': self.company_name,
            'contact_person_name': self.contact_person_name,
            'contact_person_position': self.contact_person_position,
            'email': self.email,
            'phone_number': self.phone_number,
            'address': self.address,
            'industry': self.industry,
            'territory': self.territory,
            'is_vip': self.is_vip,
            'is_active': self.is_active,
            'is_millionaire_account': self.is_millionaire_account,
            'auto_inactive_flag': self.auto_inactive_flag,
            'last_sales_activity_at': self.last_sales_activity_at.isoformat() if self.last_sales_activity_at else None,
            'lifetime_won_revenue': str(self.lifetime_won_revenue),
            'status_last_synced_at': self.status_last_synced_at.isoformat() if self.status_last_synced_at else None,
            'salesperson_id': self.salesperson.id if self.salesperson else None,
            'salesperson_username': self.salesperson.username if self.salesperson else None,
        }
        
        return CustomerBackup.objects.create(
            customer=self,
            backup_data=json.dumps(backup_data),
            changed_by=changed_by,
            reason=reason
        )

class CustomerNote(models.Model):
    """Model for salespersons to add notes about customers"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_notes')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Note on {self.customer} by {self.author}"

class CustomerCreateRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    # Proposed customer fields
    company_name = models.CharField(max_length=255)
    contact_person_name = models.CharField(max_length=100)
    contact_person_position = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone_number = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    industry = models.CharField(max_length=50, blank=True)
    territory = models.CharField(max_length=50, blank=True)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='customer_create_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    similar_matches = models.JSONField(null=True, blank=True, help_text="List of similar existing customers with similarity scores")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_create_reviews')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)
    requester_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['company_name']),
        ]

    def approve(self, reviewer):
        if self.status != 'pending':
            return None
        customer = Customer.objects.create(
            company_name=self.company_name,
            contact_person_name=self.contact_person_name,
            contact_person_position=self.contact_person_position,
            email=self.email,
            phone_number=self.phone_number,
            address=self.address,
            industry=self.industry,
            territory=self.territory,
            salesperson=self.requested_by if self.requested_by and self.requested_by.role == 'salesperson' else None,
            is_active=True,
            is_vip=False
        )
        self.status = 'approved'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.requester_seen_at = None
        self.save(update_fields=['status','reviewed_by','reviewed_at', 'requester_seen_at'])
        return customer

    def reject(self, reviewer, notes=''):
        self.status = 'rejected'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.decision_notes = notes or ''
        self.requester_seen_at = None
        self.save(update_fields=['status','reviewed_by','reviewed_at','decision_notes', 'requester_seen_at'])
        return self

    @property
    def is_requester_unread(self):
        return self.status != 'pending' and self.requester_seen_at is None

    def mark_seen_by_requester(self):
        if self.requested_by_id and self.status != 'pending' and self.requester_seen_at is None:
            self.requester_seen_at = timezone.now()
            self.save(update_fields=['requester_seen_at'])

class CustomerHistory(models.Model):
    """Model to track all changes made to customers for audit trail and salesperson credit"""
    
    ACTION_CHOICES = [
        ('created', 'Customer Created'),
        ('updated', 'Customer Updated'),
        ('vip_enabled', 'Became VIP Customer'),
        ('vip_disabled', 'VIP Status Removed'),
        ('activated', 'Customer Activated'),
        ('deactivated', 'Customer Deactivated'),
        ('salesperson_assigned', 'Salesperson Assigned'),
        ('salesperson_changed', 'Salesperson Changed'),
        ('salesperson_removed', 'Salesperson Removed'),
        ('restored', 'Restored from Backup'),
        ('imported', 'Imported from CSV'),
        ('field_updated', 'Field Updated'),
        ('deal_won', 'Deal Marked Won'),
        ('deal_lost', 'Deal Marked Lost'),
        ('funnel_entry_removed', 'Funnel Entry Removed'),
        ('funnel_entry_restored', 'Funnel Entry Restored'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='history',
        help_text='The customer this history entry belongs to'
    )
    
    action = models.CharField(
        max_length=25,
        choices=ACTION_CHOICES,
        help_text='Type of action performed'
    )
    
    description = models.TextField(
        help_text='Detailed description of what changed'
    )
    
    # Track both the person who made the change and the salesperson at the time
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customer_changes_made',
        help_text='The user who made this change'
    )
    
    salesperson_at_time = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_history_as_salesperson',
        help_text='The salesperson assigned to the customer at the time of this change'
    )
    
    # Store previous and new values for important changes
    old_value = models.JSONField(
        null=True,
        blank=True,
        help_text='Previous value before the change (JSON format)'
    )
    
    new_value = models.JSONField(
        null=True,
        blank=True,
        help_text='New value after the change (JSON format)'
    )
    
    # Additional context
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='IP address of the user who made the change'
    )
    
    user_agent = models.TextField(
        blank=True,
        help_text='User agent string of the browser used'
    )
    
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text='When this change occurred'
    )
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['customer', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['salesperson_at_time', '-timestamp']),
            models.Index(fields=['changed_by', '-timestamp']),
        ]
        verbose_name = 'Customer History'
        verbose_name_plural = 'Customer Histories'

    @classmethod
    def log_customer_change(
        cls,
        customer: 'Customer',
        action: str,
        description: str,
        changed_by: 'User' = None,
        old_value=None,
        new_value=None,
        ip_address: str = None,
        user_agent: str = ''
    ):
        """Convenience method used by forms/views to record a history entry."""
        return cls.objects.create(
            customer=customer,
            action=action,
            description=description,
            changed_by=changed_by,
            salesperson_at_time=customer.salesperson if customer and customer.salesperson else None,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent or ''
        )

    @property
    def action_icon(self):
        """FontAwesome icon for this history action (used by the timeline badge)."""
        icons = {
            'created': 'fas fa-plus-circle',
            'updated': 'fas fa-edit',
            'vip_enabled': 'fas fa-star',
            'vip_disabled': 'far fa-star',
            'activated': 'fas fa-toggle-on',
            'deactivated': 'fas fa-toggle-off',
            'salesperson_assigned': 'fas fa-user-plus',
            'salesperson_changed': 'fas fa-user-edit',
            'salesperson_removed': 'fas fa-user-minus',
            'restored': 'fas fa-undo',
            'imported': 'fas fa-file-import',
            'field_updated': 'fas fa-pencil-alt',
            'deal_won': 'fas fa-trophy',
            'deal_lost': 'fas fa-heart-crack',
            'funnel_entry_removed': 'fas fa-box-archive',
            'funnel_entry_restored': 'fas fa-rotate-left',
        }
        return icons.get(self.action, 'fas fa-circle')

    @property
    def action_color(self):
        """Bootstrap contextual color for this history action's badge."""
        colors = {
            'created': 'success',
            'updated': 'primary',
            'vip_enabled': 'warning',
            'vip_disabled': 'secondary',
            'activated': 'success',
            'deactivated': 'danger',
            'salesperson_assigned': 'info',
            'salesperson_changed': 'warning',
            'salesperson_removed': 'secondary',
            'restored': 'info',
            'imported': 'primary',
            'field_updated': 'secondary',
            'deal_won': 'success',
            'deal_lost': 'danger',
            'funnel_entry_removed': 'warning',
            'funnel_entry_restored': 'info',
        }
        return colors.get(self.action, 'secondary')


class DelinquencyRecord(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
        ('watch', 'Watch List'),
    ]
    customer = models.ForeignKey(DelinquentCustomer, on_delete=models.CASCADE, related_name='delinquency_records')
    salesperson = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'salesperson'}, related_name='delinquency_customers')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    tin_number = models.CharField(max_length=50, blank=True)
    partner_name = models.CharField(max_length=100, blank=True)
    date_delivered = models.DateField(null=True, blank=True)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    last_payment_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_delinquencies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['salesperson']),
        ]

    def __str__(self):
        return f"{self.customer.company_name} - {self.get_status_display()} ₱{self.amount_due}"
    
    @property
    def action_icon(self):
        """Return FontAwesome icon for the action"""
        icons = {
            'created': 'fas fa-plus-circle text-success',
            'updated': 'fas fa-edit text-primary',
            'vip_enabled': 'fas fa-star text-warning',
            'vip_disabled': 'far fa-star text-muted',
            'activated': 'fas fa-toggle-on text-success',
            'deactivated': 'fas fa-toggle-off text-danger',
            'salesperson_assigned': 'fas fa-user-plus text-info',
            'salesperson_changed': 'fas fa-user-edit text-warning',
            'salesperson_removed': 'fas fa-user-minus text-secondary',
            'restored': 'fas fa-undo text-info',
            'imported': 'fas fa-file-import text-primary',
            'field_updated': 'fas fa-pencil-alt text-secondary',
        }
        # Fallback if action is not in the list, though action field is on CustomerHistory
        return icons.get('created', 'fas fa-circle text-secondary')
    
    @property
    def action_color(self):
        """Return Bootstrap color class for the action"""
        colors = {
            'created': 'success',
            'updated': 'primary',
            'vip_enabled': 'warning',
            'vip_disabled': 'secondary',
            'activated': 'success',
            'deactivated': 'danger',
            'salesperson_assigned': 'info',
            'salesperson_changed': 'warning',
            'salesperson_removed': 'secondary',
            'restored': 'info',
            'imported': 'primary',
            'field_updated': 'secondary',
        }
        return colors.get('created', 'secondary')


class CustomerBackup(models.Model):
    """Model to store customer backup data for restoration purposes"""
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.CASCADE,
        related_name='backups',
        help_text='The customer this backup belongs to'
    )
    backup_data = models.TextField(
        help_text='JSON data containing the customer state at backup time'
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        help_text='The user who made the change that triggered this backup'
    )
    reason = models.CharField(
        max_length=200,
        default='Manual backup',
        help_text='Reason for creating this backup'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='When this backup was created'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', '-created_at']),
        ]
        verbose_name = 'Customer Backup'
        verbose_name_plural = 'Customer Backups'
    
    def __str__(self):
        return f"Backup of {self.customer.company_name} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    
    def get_backup_data(self):
        """Return the backup data as a Python dictionary"""
        try:
            return json.loads(self.backup_data)
        except json.JSONDecodeError:
            return {}
    
    def restore(self, restored_by):
        """Restore the customer to this backup state"""
        backup_data = self.get_backup_data()
        if not backup_data:
            raise ValueError("Invalid backup data")
        
        # Create a backup of current state before restoring
        self.customer.create_backup(
            changed_by=restored_by,
            reason=f"Before restore from backup {self.id}"
        )
        
        # Restore the customer data
        for field, value in backup_data.items():
            if field == 'salesperson_id' and value:
                try:
                    salesperson = User.objects.get(id=value, role='salesperson')
                    self.customer.salesperson = salesperson
                except User.DoesNotExist:
                    # If salesperson doesn't exist anymore, leave as null
                    self.customer.salesperson = None
            elif field in ['last_sales_activity_at', 'status_last_synced_at'] and value:
                setattr(self.customer, field, parse_datetime(value) or value)
            elif field not in ['salesperson_id', 'salesperson_username']:
                setattr(self.customer, field, value)
        
        self.customer.save()
        
        # Create a restoration log entry
        CustomerBackup.objects.create(
            customer=self.customer,
            backup_data=json.dumps({
                'restored_from_backup_id': self.id,
                'restored_at': self.created_at.isoformat(),
                'restored_reason': self.reason
            }),
            changed_by=restored_by,
            reason=f"Restored from backup {self.id}"
        )

class CustomerContact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=120)
    position = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_primary', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.customer.company_name})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Ensure max 4 contacts per customer (soft enforcement)
        contacts = CustomerContact.objects.filter(customer=self.customer).order_by('-created_at')
        if contacts.count() > 4:
            # Keep newest 4; delete oldest extras
            for extra in contacts[4:]:
                extra.delete()
        # Ensure only one primary
        if self.is_primary:
            CustomerContact.objects.filter(customer=self.customer).exclude(id=self.id).update(is_primary=False)
