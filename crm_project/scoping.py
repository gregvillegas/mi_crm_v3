"""
Single source of truth for "whose records may this user see?".

The REST API and the server-rendered views used to answer this question
separately, and they drifted apart: the API let an AVP read every customer in
the company, scoped ASMs to their whole team instead of just the groups they
handle, and returned nothing at all for the `sm` and `marketing` roles (so SM
users saw empty lists in the mobile app). Every API queryset now derives from
the helpers below, which mirror what the web views already enforce.

`scoped_user_ids()` returns ``None`` to mean *unrestricted* — deliberately
distinct from an empty set, which means *this user may see nothing*.
"""
from customers.permissions import (
    EXEC_ROLES as CUSTOMER_GLOBAL_ROLES,
    get_team_scoped_users,
    get_user_team_ids,
    group_scoped_member_ids,
)
from teams.models import Group, TeamMembership

# Roles that see every sales record company-wide.
#
# Deliberately NOT the same set as customers.permissions.EXEC_ROLES: `marketing`
# belongs there (they run campaigns against the whole customer base) but has no
# business reading the sales pipeline, proposals, or activity logs.
SALES_GLOBAL_ROLES = {'admin', 'president', 'gm', 'vp'}


def _member_ids(groups):
    """Members of these groups, plus the groups' supervisors."""
    group_ids = list(groups.values_list('id', flat=True))
    if not group_ids:
        return set()
    members = TeamMembership.objects.filter(group_id__in=group_ids).values_list('user_id', flat=True)
    supervisors = (
        Group.objects
        .filter(id__in=group_ids, supervisor__isnull=False)
        .values_list('supervisor_id', flat=True)
    )
    return set(members) | set(supervisors)


def _avp_member_ids(user):
    """
    Everyone under an AVP's managed teams: group members, group supervisors, the
    SM managers assigned to those groups, and each team's ASM. Mirrors the `avp`
    branch of sales_proposals.views.proposal_list.
    """
    ids = set()
    for team in user.managed_teams.all():
        for group in team.groups.all():
            ids.update(group.members.values_list('user_id', flat=True))
            if group.supervisor_id:
                ids.add(group.supervisor_id)
            ids.update(group.sm_managers.values_list('id', flat=True))
        if team.asm_id:
            ids.add(team.asm_id)
    return ids


def scoped_user_ids(user):
    """
    The set of user IDs whose sales records `user` may see.

    Returns None for roles with unrestricted visibility, and an empty set for a
    user whose scope cannot be resolved (e.g. a supervisor with no groups yet).
    """
    if not getattr(user, 'is_authenticated', False):
        return set()

    role = getattr(user, 'role', None)

    if role in SALES_GLOBAL_ROLES:
        return None
    if role == 'salesperson':
        return {user.id}
    if role == 'supervisor':
        return _member_ids(Group.objects.filter(supervisor=user)) | {user.id}
    if role == 'teamlead':
        return _member_ids(Group.objects.filter(teamlead=user)) | {user.id}
    if role in {'asm', 'sm'}:
        # Group-scoped: only the groups they actually handle, never the whole team.
        return group_scoped_member_ids(user)
    if role == 'avp':
        return _avp_member_ids(user) | {user.id}

    return set()


def can_see_all_sales(user):
    return scoped_user_ids(user) is None


def filter_by_owner(queryset, user, field='salesperson_id'):
    """Narrow `queryset` to records owned by someone within `user`'s scope."""
    ids = scoped_user_ids(user)
    if ids is None:
        return queryset
    if not ids:
        return queryset.none()
    return queryset.filter(**{f'{field}__in': ids})


def visible_customer_queryset(user):
    # Customer visibility already has a well-tested implementation with its own
    # (broader) notion of who is global — reuse it rather than fork the rules.
    from customers.permissions import visible_customers_queryset
    return visible_customers_queryset(user)


def visible_proposal_queryset(user):
    from sales_proposals.models import Proposal
    return filter_by_owner(Proposal.objects.all(), user, field='created_by_id')


def visible_activity_queryset(user):
    from sales_monitoring.models import SalesActivity
    return filter_by_owner(SalesActivity.objects.all(), user)


def visible_funnel_queryset(user):
    from sales_funnel.models import SalesFunnel
    return filter_by_owner(SalesFunnel.objects.all(), user)


def can_review_customer_requests_globally(user):
    return getattr(user, 'role', None) in CUSTOMER_GLOBAL_ROLES
