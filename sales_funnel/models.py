from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from users.models import User
from customers.models import Customer

class SalesFunnel(models.Model):
    FUNNEL_STAGES = [
        ('quoted', 'Newly Quoted'),       # Pink funnel
        ('closable', 'Closable Deals'),  # Yellow funnel  
        ('project', 'Green Funnel'),     # Green funnel
        ('services', 'Blue Funnel'),         # Blue funnel
    ]
    
    # Basic Information
    date_created = models.DateField(
        help_text="Date when this funnel entry was created"
    )
    company_name = models.CharField(
        max_length=200,
        help_text="Name of the company for this proposal"
    )
    brand = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional product or solution brand, e.g. Cisco, IBM, Dell"
    )
    requirement_description = models.TextField(
        help_text="Description of the customer's requirements"
    )
    
    # Financial Information
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Cost/expense for this proposal"
    )
    retail = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="SRP quoted to customer"
    )
    
    # Funnel Classification
    stage = models.CharField(
        max_length=20,
        choices=FUNNEL_STAGES,
        default='quoted',
        help_text="Current stage of this proposal in the sales funnel"
    )
    
    # Relationships
    salesperson = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='funnel_entries',
        limit_choices_to={'role': 'salesperson'},
        help_text="Account Manager responsible for this proposal"
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='funnel_entries',
        null=True,
        blank=True,
        help_text="Associated customer (if exists in customer database)"
    )

    proposal = models.ForeignKey(
        'sales_proposals.Proposal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='funnel_entries',
        help_text="The proposal that generated this funnel entry"
    )
    
    # Additional Information
    expected_close_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expected date to close this deal"
    )
    probability = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0)],
        help_text="Probability of closing this deal (0-100%)"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this proposal"
    )
    
    # Deal outcome choices
    DEAL_OUTCOMES = [
        ('active', 'Active'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ]
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this funnel entry is active"
    )
    is_closed = models.BooleanField(
        default=False,
        help_text="Whether this deal has been closed (won or lost)"
    )
    is_test = models.BooleanField(
        default=False,
        help_text="Marks a throwaway test/scratch entry. Only test entries may be deleted."
    )
    deal_outcome = models.CharField(
        max_length=20,
        choices=DEAL_OUTCOMES,
        default='active',
        help_text="Outcome of this deal - active, won, or lost"
    )
    closed_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when this deal was closed"
    )
    lost_reason = models.TextField(
        blank=True,
        help_text="Why this deal was lost. Required when marking a deal LOST so "
                  "the team can learn from it; shown in deal history."
    )

    # Soft-delete / archive. A real entry is never hard-deleted (that would
    # erase pipeline/revenue history). Instead it is removed from the active
    # pipeline by setting is_active=False and recording who/why/when, so a
    # supervisor can still review it and restore it if needed.
    removed_reason = models.TextField(
        blank=True,
        help_text="Why this entry was removed from the pipeline. Required when "
                  "removing a real entry; kept for supervisor review."
    )
    removed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this entry was removed from the active pipeline."
    )
    removed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='removed_funnel_entries',
        help_text="The user who removed this entry from the pipeline."
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_created', '-created_at']
        indexes = [
            models.Index(fields=['salesperson', 'stage']),
            models.Index(fields=['stage', 'is_active']),
            models.Index(fields=['date_created']),
            models.Index(fields=['expected_close_date']),
            models.Index(fields=['brand']),
        ]
        verbose_name = 'Sales Funnel Entry'
        verbose_name_plural = 'Sales Funnel Entries'
    
    def __str__(self):
        return f"{self.company_name} - {self.get_stage_display()} (₱{self.display_retail:,.2f})"

    @property
    def display_retail(self):
        if self.proposal_id and self.proposal:
            return self.proposal.quoted_amount_php
        return self.retail

    @property
    def display_cost(self):
        return self.cost
    
    @property
    def profit(self):
        """Calculate profit as retail - cost"""
        return self.display_retail - self.display_cost
    
    @property
    def profit_margin(self):
        """Calculate profit margin as percentage"""
        retail = self.display_retail
        if retail > 0:
            return (self.profit / retail) * 100
        return 0
    
    @property
    def stage_color(self):
        """Return the color code for this funnel stage"""
        colors = {
            'quoted': 'pink',
            'closable': 'warning',  # Bootstrap yellow/warning
            'project': 'success',   # Bootstrap green/success
            'services': 'primary',  # Bootstrap blue/primary
        }
        return colors.get(self.stage, 'secondary')
    
    @property
    def stage_icon(self):
        """Return the icon for this funnel stage"""
        icons = {
            'quoted': 'fas fa-quote-left',
            'closable': 'fas fa-handshake',
            'project': 'fas fa-project-diagram',
            'services': 'fas fa-screwdriver-wrench',
        }
        return icons.get(self.stage, 'fas fa-circle')
    
    def save(self, *args, **kwargs):
        # Auto-set closed_date when marking as closed
        if self.is_closed and not self.closed_date:
            from django.utils import timezone
            self.closed_date = timezone.now().date()
        # Auto-classify services/project based on retail threshold
        if not self.is_closed and self.stage in ['project', 'services']:
            threshold = Decimal('500000')
            self.stage = 'project' if self.display_retail >= threshold else 'services'
        super().save(*args, **kwargs)
