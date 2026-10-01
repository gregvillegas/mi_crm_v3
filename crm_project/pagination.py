from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """
    Paginates only when the caller asks for it.

    The list endpoints were declared `pagination_class = None`, so a salesperson
    with 2,000 customers downloaded all of them on every screen open. Turning
    pagination on unconditionally would break the shipped Android build, which
    decodes a bare JSON array. So: no `page`/`page_size` parameter means the old
    flat-array response, and passing either opts into the wrapped
    `{count, next, previous, results}` envelope.
    """

    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if self.page_query_param not in request.query_params and \
           self.page_size_query_param not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)
