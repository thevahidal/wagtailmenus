from django.db.models import Manager, Q


class MenuItemManager(Manager):
    ''' App-specific manager overrides '''

    def for_display(self):
        return self.filter(
            Q(link_page__isnull=True) |
            Q(link_page__live=True) &
            Q(link_page__expired=False) &
            Q(link_page__show_in_menus=True)
        )

    def page_links_for_display(self):
        return self.filter(
            link_page__live=True,
            link_page__expired=False,
            link_page__show_in_menus=True)
