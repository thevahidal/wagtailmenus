from django.test import RequestFactory
from django.utils.translation import ugettext_lazy as _
from rest_framework import fields
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import Serializer
from wagtail.core.models import Page, Site

from wagtailmenus.conf import constants, settings

main_menu_model = settings.models.MAIN_MENU_MODEL
flat_menu_model = settings.models.FLAT_MENU_MODEL


class RenderViewArgumentSerializer(Serializer):
    current_url = fields.URLField()
    apply_active_classes = fields.BooleanField()
    allow_repeating_parents = fields.BooleanField()
    use_absolute_page_urls = fields.BooleanField()

    def to_internal_value(self, data):
        """
        Overrides Serializer.to_internal_value() to allow us to derive a
        ``wagtail.core.models.Site`` object from the 'current_url' value and
        include it as 'site' in the return value.
        """
        result = super().to_internal_value(data)
        rf = RequestFactory()
        request = rf.get(result['current_url'])
        try:
            result['site'] = Site.find_for_request(request)
        except Site.DoesNotExist:
            raise ValidationError({'current_url': _(
                'No site could be derived this value'
            )})
        return result


class ModelBasedMenuArgumentSerializer(RenderViewArgumentSerializer):
    USE_SPECIFIC_CHOICES = (
        ('', _('Use menu object defaults')),
    ) + constants.USE_SPECIFIC_CHOICES

    max_levels = fields.IntegerField(min_value=1, max_value=5, allow_null=True)
    use_specific = fields.ChoiceField(choices=USE_SPECIFIC_CHOICES, allow_blank=True)


class ClassBasedMenuArgumentSerializer(RenderViewArgumentSerializer):
    max_levels = fields.IntegerField(min_value=1, max_value=5)
    use_specific = fields.ChoiceField(choices=constants.USE_SPECIFIC_CHOICES)


class MainMenuArgumentSerializer(ModelBasedMenuArgumentSerializer):
    pass


class FlatMenuArgumentSerializer(ModelBasedMenuArgumentSerializer):
    handle = fields.SlugField()


class ChildrenMenuArgumentSerializer(ClassBasedMenuArgumentSerializer):
    parent_page = fields.RelatedField(
        queryset=Page.objects.all(),
        allow_empty=True
    )


class SectionMenuArgumentSerializer(ClassBasedMenuArgumentSerializer):
    pass


class MenuSerializer(Serializer):
    pass


class MainMenuSerializer(MenuSerializer):
    pass


class FlatMenuSerializer(MenuSerializer):
    site = Field()
    handle = Field()


class ChildrenMenuSerializer(MenuSerializer):
    parent_page = Field()


class SectionMenuSerializer(MenuSerializer):
    section_root_page = Field()
