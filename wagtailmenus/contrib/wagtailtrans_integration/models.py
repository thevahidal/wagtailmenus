from django.db import models
from modelcluster.fields import ParentalKey
from wagtailtrans.conf import get_wagtailtrans_setting
from wagtailtrans.models import _language_default, get_user_language,\
    SiteLanguages

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if(
            'language' not in kwargs and
            get_wagtailtrans_setting('LANGUAGES_PER_SITE') and
            self.site_id
        ):
            site_settings = SiteLanguages.objects.select_related('default_language').get(site_id=self.site_id)
            self.language = site_settings.default_language


class LanguageSpecificMainMenu(LanguageSpecificMenuMixin, AbstractMainMenu):

    class Meta(AbstractMainMenu.Meta):
        unique_together = ('site', 'language')

    @classmethod
    def get_instance_for_rendering(cls, contextual_vals, option_vals):
        return cls.objects.get(
            site=contextual_vals.current_site,
            language=get_user_language(contextual_vals.request),
        )

    @classmethod
    def get_for_site(cls, site, language):
        """Return an instance with ``site`` and ``language`` values matching
        the values provided, or None if no such menu exists."""
        return cls.objects.filter(site=site, language=language).first()


class LanguageSpecificFlatMenu(LanguageSpecificMenuMixin, AbstractFlatMenu):

    class Meta(AbstractFlatMenu.Meta):
        unique_together = ('site', 'language', 'handle')

    @classmethod
    def get_instance_for_rendering(cls, contextual_vals, option_vals):
        return cls.get_for_site(
            handle=option_vals.handle,
            site=contextual_vals.current_site,
            language=get_user_language(contextual_vals.request),
            fall_back_to_default_site_menus=option_vals.extra[
                'fall_back_to_default_site_menus']
        )

    @classmethod
    def get_for_site(cls, handle, site, language, fall_back_to_default_site_menus=False):
        """Replicates the functionality of AbstractFlatMenu.get_for_site(), but
        only returns a menu object matching the supplied language"""
        return super().get_for_site(
            base_queryset=cls.objects.filter(language=language))


class MainMenuItem(AbstractMainMenuItem):

    menu = ParentalKey(
        LanguageSpecificMainMenu, on_delete=models.CASCADE, related_name="menu_items"
    )


class FlatMenuItem(AbstractFlatMenuItem):

    menu = ParentalKey(
        LanguageSpecificFlatMenu, on_delete=models.CASCADE, related_name="menu_items"
    )
