from customers.models import CustomerHistory


def clear_auto_inactive_for_engagement(customer, *, source, changed_by=None):
    """Clear only the automatic inactivity flag after a qualifying engagement."""
    if not customer or not customer.auto_inactive_flag:
        return False

    customer.auto_inactive_flag = False
    customer.save(update_fields=['auto_inactive_flag'])
    CustomerHistory.log_customer_change(
        customer=customer,
        action='field_updated',
        description=f"System cleared auto-inactive status after {source}.",
        changed_by=changed_by,
        old_value={'auto_inactive_flag': True},
        new_value={'auto_inactive_flag': False},
        user_agent='system/customer_engagement',
    )
    return True
