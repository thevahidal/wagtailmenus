from django.db import models
from modelcluster.fields import ParentalKey
from wagtailtrans.models import _language_default

from wagtailmenus.models import (
    AbstractMainMenu, AbstractFlatMenu,
    AbstractMainMenuItem, AbstractFlatMenuItem
)


class LanguageSpecificMenuMixin(models.Model):
    language = models.ForeignKey(
        'wagtailtrans.Language',
        on_delete=models.CASCADE,
        default=_language_default,
        editable=False,
    )
    site = models.ForeignKey(
        'wagtailcore.Site',
        db_index=True,
        editable=False,
        on_delete=models.CASCADE,
        related_name='+'
    )

    class Meta:
        abstract = True


class MainMenu(LanguageSpecificMenuMixin, AbstractMainMenu):

    class Meta(AbstractMainMenu.Meta):
        unique_together = ('site', 'language')


class FlatMenu(LanguageSpecificMenuMixin, AbstractFlatMenu):

    class Meta(AbstractFlatMenu.Meta):
        unique_together = ('site', 'language', 'handle')


class MainMenuItem(AbstractMainMenuItem):

    menu = ParentalKey(
        MainMenu, on_delete=models.PROTECT, related_name="menu_items"
    )


class FlatMenuItem(AbstractFlatMenuItem):

    menu = ParentalKey(
        FlatMenu, on_delete=models.PROTECT, related_name="menu_items"
    )
