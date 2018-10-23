from rest_framework import exceptions
from rest_framework import viewsets
from rest_framework.response import Response
from wagtail.core.models import Page

from wagtailmenus.conf import settings

from . import forms
from . import serializers


class MenuViewSetMixin:
    default_max_levels = None
    default_use_specific = None
    default_apply_active_classes = True
    default_allow_repeating_parents = True
    default_use_absolute_page_urls = False
    detail_view_url_kwargs = None
    detail_view_serializer_class = None
    detail_view_option_validator_form_class = None
    model = None

    @classmethod
    def get_model(cls):
        if cls.model is None:
            raise NotImplementedError(
                "For subclasses of MenuViewSetMixin, you must set the 'model' "
                "attribute or override the get_model() class method."
            )
        return cls.model

    def get_detail_view_serializer_class(self):
        if self.detail_view_serializer_class is None:
            raise NotImplementedError(
                "For subclasses of MenuViewSetMixin, you must set the "
                "'detail_view_serializer_class' attribute or override the "
                "get_detail_view_serializer_class() class method."
            )
        return self.detail_view_serializer_class

    def get_detail_view_serializer(self, *args, **kwargs):
        serializer_class = self.get_detail_view_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def retrieve(self, request, **kwargs):
        context_data = self.get_detail_view_context_data(request, kwargs)
        instance = self.get_object(context_data)
        serializer = self.get_detail_view_serializer(instance)
        return Response(serializer.data)

    def get_detail_view_context_data(self, request, **kwargs):
        initial_data = self.get_detail_view_context_defaults()
        initial_data.update(kwargs)
        form_class = self.get_detail_view_context_validator_form()
        form = form_class(data=request.GET, initial=initial_data)
        if not form.is_valid():
            raise exceptions.ValidationError(form.errors)
        return form.cleaned_data

    def get_detail_view_context_defaults(self):
        return {
            'max_levels': self.default_max_levels,
            'use_specific': self.default_use_specific,
            'apply_active_classes': self.default_apply_active_classes,
            'allow_repeating_parents': self.default_allow_repeating_parents,
            'use_absolute_page_urls': self.default_use_absolute_page_urls,
            'site': None,
            'current_page': None,
        }

    def get_detail_view_url_kwargs(self):
        if self.detail_view_url_kwargs is None:
            raise NotImplementedError(
                "For subclasses of MenuViewSetMixin, you must set the "
                "'detail_view_url_kwargs' attribute or override the "
                "get_detail_view_url_kwargs() method.")
        return self.detail_view_url_kwargs

    def get_detail_view_context_validator_form(self):
        if self.detail_view_option_validator_form_class is None:
            raise NotImplementedError(
                "For subclasses of MenuViewSetMixin, you must set the "
                "'detail_view_option_validator_form_class' attribute or "
                "override the get_detail_view_option_validator_form_class() "
                "method."
            )
        return self.detail_view_option_validator_form_class

    def get_object(self, **context_data):
        """
        The Menu classes themselves are responsible for getting/creating menu
        instances and preparing them for rendering. So, the role of this
        method is to bundle up all available data into a format that
        ``Menu._get_render_prepared_object()`` will understand, and call that.
        """

        # Menus are typically rendered from an existing ``RequestContext``
        # object, which we do not have. However, we can provide a dictionary
        # with a similar-looking data structure.
        context = {
            'request': self.request,
            'current_site': context_data.pop('site'),
            # Typically, this would be added by wagtailmenus' context processor
            'wagtailmenus_vals': {
                'current_page': context_data.pop('current_page'),
                'section_root': context_data.pop('section_root_page'),
                'current_page_ancestor_ids': context_data.pop('current_page_ancestor_ids'),
            }
        }

        # The remaining values can safely be considered as 'option values'
        option_values = context_data

        # Setting this to allow the serializer to render multi-level menu items
        option_values['add_sub_menus_inline'] = True

        return self.get_model()._get_render_prepared_object(context, **option_values)


class MainMenuViewSet(MenuViewSetMixin, viewsets.ReadOnlyModelViewSet):
    base_name = "main_menu"
    model = settings.models.MAIN_MENU_MODEL
    serializer_class = serializers.MainMenuSerializer

    detail_view_serializer_class = serializers.MainMenuDetailSerializer
    detail_view_option_validator_form_class = forms.MainMenuOptionValidatorForm

    def get_queryset(self):
        # Only used for listing
        return self.get_model().objects.all()

    def retrieve(self, request, site_id):
        return super().retrieve(request, site_id=site_id)


class FlatMenuViewSet(MenuViewSetMixin, viewsets.ReadOnlyModelViewSet):
    base_name = "flat_menu"
    model = settings.models.FLAT_MENU_MODEL
    serializer_class = serializers.FlatMenuSerializer

    detail_view_serializer_class = serializers.FlatMenuDetailSerializer
    detail_view_option_validator_form_class = forms.FlatMenuOptionValidatorForm

    def retrieve(self, request, site_id, handle):
        return super().retrieve(request, site_id=site_id, handle=handle)

    def get_queryset(self):
        # Only used for listing
        return self.get_model().objects.all()


class DetailOnlyMenuViewSet(MenuViewSetMixin, viewsets.ViewSet):
    pass


class ChildrenMenuViewSet(DetailOnlyMenuViewSet):
    base_name = 'children_menu'
    model = settings.objects.CHILDREN_MENU_CLASS

    detail_view_serializer_class = serializers.ChildrenMenuSerializer
    detail_view_option_validator_form_class = forms.ChildrenMenuOptionValidatorForm

    # default option value overrides
    default_apply_active_classes = False
    default_max_levels = settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS
    default_use_specific = settings.DEFAULT_CHILDREN_MENU_USE_SPECIFIC

    def retrieve(self, request, site_id, parent_page_id):
        return super().retrieve(request, site_id=site_id, parent_page_id=parent_page_id)

    def clean_detail_url_kwargs(self, url_kwargs):
        url_kwargs = super().clean_detail_url_kwargs(url_kwargs)

        # Ensure 'parent_page' is a valid page
        parent_page_id = url_kwargs['parent_page']
        try:
            url_kwargs['parent_page'] = Page.objects.get(id=parent_page_id)
        except:
            raise exceptions.ValidationError(
                "No page could be found matching the ID '%s' supplied for "
                "'parent_page'." % parent_page_id
            )
        return url_kwargs


class SectionMenuViewSet(DetailOnlyMenuViewSet):
    base_name = 'section_menu'
    model = settings.objects.SECTION_MENU_CLASS

    detail_view_serializer_class = serializers.SectionMenuSerializer
    detail_view_option_validator_form_class = forms.SectionMenuOptionValidatorForm

    # default option value overrides
    default_max_levels = settings.DEFAULT_SECTION_MENU_MAX_LEVELS
    default_use_specific = settings.DEFAULT_SECTION_MENU_USE_SPECIFIC

    def retrieve(self, request, site_id, current_page_id):
        return super().retrieve(request, site_id=site_id, current_page_id=current_page_id)

    def clean_detail_url_kwargs(self, url_kwargs):
        url_kwargs = super().clean_detail_url_kwargs(url_kwargs)

        # Ensure 'current_page' is a valid page
        current_page_id = url_kwargs['current_page']
        try:
            current_page = Page.objects.get(id=current_page_id)
            url_kwargs['current_page'] = current_page
        except:
            raise exceptions.ValidationError(
                "No page could be found matching the ID '%s' supplied for "
                "'current_page'." % url_kwargs['current_page']
            )

        # Identify 'section_root_page' from the 'current_page'
        if current_page.depth >= settings.SECTION_ROOT_DEPTH:
            if current_page.depth == settings.SECTION_ROOT_DEPTH:
                section_root = current_page
            else:
                section_root = current_page.get_ancestors().filter(
                    depth__exact=settings.SECTION_ROOT_DEPTH).get()
            url_kwargs['section_root_page'] = section_root.specific()
        return url_kwargs
