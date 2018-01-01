
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from rest_framework import fields
from rest_framework.exceptions import ValidationError
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import Serializer
from wagtail.core.models import Page, Site

from wagtailmenus.conf import constants, settings
from wagtailmenus.utils.misc import make_dummy_request

main_menu_model = settings.models.MAIN_MENU_MODEL
flat_menu_model = settings.models.FLAT_MENU_MODEL

UNDERIVABLE_ERROR_MSG = _(
    "This value could not be derived from other values, and "
    "so must be provided."
)


class RenderViewArgumentSerializer(Serializer):
    apply_active_classes = fields.BooleanField()
    allow_repeating_parents = fields.BooleanField()
    use_absolute_page_urls = fields.BooleanField()
    current_url = fields.URLField(required=False)
    current_page = PrimaryKeyRelatedField(required=False, queryset=Page.objects.all())
    site = PrimaryKeyRelatedField(required=False, queryset=Site.objects.all())

    def to_internal_value(self, data):
        """
        Overrides Serializer.to_internal_value() to allow 'site' and
        'current_page' to be derived from other values if they were not
        supplied as GET parameters.
        """
        data = super().to_internal_value(data)
        self._dummy_request = None

        if data.get('site') and data.get('current_page'):
            if data['apply_active_classes']:
                self.derive_ancestor_page_ids(data)
            return data

        # Complain if 'current_url' has not been provided
        if not data.get('current_url'):
            raise ValidationError({'current_url': _(
                "The value is required to allow 'site', 'current_page' "
                "and other values to be derived."
            )})

        # We need a HttpRequest to use Site.find_for_request() or
        # Page.route(), so let's create one
        request = make_dummy_request(
            url=data['current_url'],
            original_request=self._context['request']
        )
        self._dummy_request = request

        if not data.get('site'):
            self.derive_site(data, request)

        if not data.get('current_page'):
            self.derive_current_page(data, request)

        if data['apply_active_classes']:
            self.derive_ancestor_page_ids(data)

        return data

    def derive_site(self, data, request):
        try:
            data['site'] = Site.find_for_request(request)
        except Site.DoesNotExist:
            raise ValidationError({'site': UNDERIVABLE_ERROR_MSG})

    def derive_current_page(self, data, request, force_derivation=False):
        if not force_derivation and not data['apply_active_classes']:
            return

        path_components = [pc for pc in request.path.split('/') if pc]
        first_run = True
        best_match = None
        while path_components and best_match is None:
            try:
                site = data['site']
                best_match = site.root_page.specific.route(request, path_components)[0]
                if first_run:
                    # A page was found matching the exact path, so it's
                    # safe to assume it's the 'current page'
                    data['current_page'] = best_match
                else:
                    data['best_match_page'] = best_match
            except Http404:
                # Remove a path component and try again
                path_components.pop()
            first_run = False

    def derive_ancestor_page_ids(self, data):
        page = data.get('current_page') or data.get('best_match_page')
        if page:
            data['ancestor_page_ids'] = set(
                page.get_ancestors(inclusive=bool('best_match_page' in data))
                .filter(depth__gte=settings.SECTION_ROOT_DEPTH)
                .values_list('id', flat=True)
            )
        else:
            data['ancestor_page_ids'] = ()


class ModelBasedMenuArgumentSerializer(RenderViewArgumentSerializer):
    USE_SPECIFIC_CHOICES = (
        ('', _('Use menu object defaults')),
    ) + constants.USE_SPECIFIC_CHOICES

    max_levels = fields.IntegerField(required=False, min_value=1, max_value=5)
    use_specific = fields.ChoiceField(required=False, choices=USE_SPECIFIC_CHOICES)


class ClassBasedMenuArgumentSerializer(RenderViewArgumentSerializer):
    max_levels = fields.IntegerField(min_value=1, max_value=5)
    use_specific = fields.ChoiceField(choices=constants.USE_SPECIFIC_CHOICES)


class MainMenuArgumentSerializer(ModelBasedMenuArgumentSerializer):
    pass


class FlatMenuArgumentSerializer(ModelBasedMenuArgumentSerializer):
    handle = fields.SlugField()


class ChildrenMenuArgumentSerializer(ClassBasedMenuArgumentSerializer):
    parent_page = PrimaryKeyRelatedField(
        required=False,
        queryset=Page.objects.all(),
    )

    def to_internal_value(self, data):
        """
        Overrides RenderViewArgumentSerializer.to_internal_value() to allow a
        'parent_page' value to be derived from other values if it was not
        supplied as a GET paramter.
        """
        data = super().to_internal_value(data)

        if not data.get('parent_page'):
            self.derive_parent_page(data)

        return data

    def derive_current_page(self, data, request, force_derivation=False):
        """
        Overrides RenderViewArgumentSerializer.derive_current_page(),
        because if neither 'parent_page' or 'current_page' have been
        provided, we want to force derivation, so that 'current_page' can
        serve as a stand-in for 'parent_page'.
        """
        force_derivation = force_derivation or (
            not data.get('parent_page') and not data.get('current_page')
        )
        super().derive_current_page(data, request, force_derivation)

    def derive_parent_page(self, data):
        """
        If possible, derive a value for 'parent_page' and update the supplied
        ``data`` dictionary to include it.
        """
        if data['current_page']:
            data['parent_page'] = data['current_page']
        raise ValidationError({'parent_page': UNDERIVABLE_ERROR_MSG})


class SectionMenuArgumentSerializer(ClassBasedMenuArgumentSerializer):
    section_root_page = PrimaryKeyRelatedField(
        required=False,
        queryset=Page.objects.filter(depth=settings.SECTION_ROOT_DEPTH),
    )

    def to_internal_value(self, data):
        """
        Overrides RenderViewArgumentSerializer.to_internal_value() to allow a
        'section_root_page' value to be derived from other values if it was not
        supplied as a GET paramter.
        """
        data = super().to_internal_value(data)

        if not data.get('section_root_page'):
            self.derive_section_root_page(data)

        return data

    def derive_current_page(self, data, request, force_derivation=False):
        """
        Overrides RenderViewArgumentSerializer.derive_current_page(),
        because if neither 'section_root_page' or 'current_page' have been
        provided, we want to force derivation, so that 'section_root_page'
        might then be further derived from 'current_page'.
        """
        force_derivation = force_derivation or (
            not data.get('section_root_page') and not data.get('current_page')
        )
        super().derive_current_page(data, request, force_derivation)

    def derive_section_root_page(self, data):
        """
        If possible, derive a value for 'section_root_page' and update the
        supplied ``data`` dictionary to include it.
        """
        section_root_depth = settings.SECTION_ROOT_DEPTH
        page = data.get('current_page') or data.get('best_match_page')
        if page is None or page.depth < section_root_depth:
            raise ValidationError({'section_root_page': UNDERIVABLE_ERROR_MSG})
        if page.depth > section_root_depth:
            data['section_root_page'] = page.get_ancestors().get(
                depth__exact=section_root_depth)
        else:
            data['section_root_page'] = page


class MenuSerializer(Serializer):
    pass


class MainMenuSerializer(MenuSerializer):
    pass


class FlatMenuSerializer(MenuSerializer):
    pass


class ChildrenMenuSerializer(MenuSerializer):
    pass


class SectionMenuSerializer(MenuSerializer):
    pass
