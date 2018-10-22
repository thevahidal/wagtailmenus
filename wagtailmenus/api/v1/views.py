from rest_framework import exceptions
from rest_framework import viewsets
from rest_framework.response import Response
from wagtail.core.models import Page

from wagtailmenus.conf import settings

from . import serializers


class MenuViewSetMixin:
    default_max_levels = None
    default_use_specific = None
    default_apply_active_classes = True
    default_allow_repeating_parents = True
    default_use_absolute_page_urls = False
    detail_url_kwargs = None
    detail_view_serializer_class = None
    model = None

    def get_default_render_options(self):
        values = self.default_render_options.copy()
        return values

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
        url_kwargs = self.clean_detail_url_kwargs(kwargs)
        option_kwargs = self.clean_detail_option_kwargs(request)
        instance = self.get_object(request, url_kwargs, option_kwargs)
        serializer = self.get_detail_view_serializer(instance)
        return Response(serializer.data)

    def clean_detail_url_kwargs(self, url_kwargs):
        """
        By defalt, each item in the classes 'required_detail_url_kwargs'
        attribute (list) must be present in kwargs. If further validation is
        required by a particular subclass (such as ensuring page ids match
        up to real pages), override this method in the subclass and apply the
        validation there.
        """
        if not self.detail_url_kwargs:
            raise NotImplementedError(
                "You must set the 'detail_url_kwargs' attribute for "
                "subclasses of MenuViewSetMixin."
            )
        for item in self.detail_url_kwargs:
            if item not in url_kwargs:
                raise exceptions.ValidationError(
                    "No '%s' value could be ascertained from the request URL"
                    % item
                )
        return url_kwargs

    def clean_detail_option_kwargs(self, request):
        defaults = {
            'max_levels': self.default_max_levels,
            'use_specific': self.default_use_specific,
            'apply_active_classes': self.default_apply_active_classes,
            'allow_repeating_parents': self.default_allow_repeating_parents,
            'use_absolute_page_urls': self.default_use_absolute_page_urls,
            'current_page': None,
            'current_site': None,
        }
        # validate request.GET kwargs here using a validator/form class
        # or something, and return a clean dictionary of option kwargs
        return defaults

    def get_object(self, request, url_kwargs, option_kwargs):
        """
        Some menu types require more than one argument to identify an existing
        object (e.g. FlatMenu). Plus, detail views also support a number of
        additional rendering options, which affect how the object is
        'prepared' for rendering. The responsibility of this method is to
        take the cleaned sets of arguments, and use them to get an instance
        of ``self.model`` that has been 'prepared' for rendering.
        """
        pass


class MainMenuViewSet(MenuViewSetMixin, viewsets.ReadOnlyModelViewSet):
    base_name = "main_menu"
    model = settings.models.MAIN_MENU_MODEL
    serializer_class = serializers.MainMenuSerializer
    detail_view_serializer_class = serializers.MainMenuDetailSerializer
    detail_url_kwargs = ('site',)

    def get_queryset(self):
        # Only used for listing
        return self.get_model().objects.all()


class FlatMenuViewSet(MenuViewSetMixin, viewsets.ReadOnlyModelViewSet):
    base_name = "flat_menu"
    model = settings.models.FLAT_MENU_MODEL
    serializer_class = serializers.FlatMenuSerializer
    detail_view_serializer_class = serializers.FlatMenuDetailSerializer
    detail_url_kwargs = ('site', 'handle')

    def get_queryset(self):
        # Only used for listing
        return self.get_model().objects.all()


class DetailOnlyMenuViewSet(MenuViewSetMixin, viewsets.ViewSet):
    pass


class ChildrenMenuViewSet(DetailOnlyMenuViewSet):
    base_name = 'children_menu'
    model = settings.objects.CHILDREN_MENU_CLASS
    detail_view_serializer_class = serializers.ChildrenMenuSerializer
    detail_url_kwargs = ('parent_page',)

    # default option value overrides
    default_apply_active_classes = False
    default_max_levels = settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS
    default_use_specific = settings.DEFAULT_CHILDREN_MENU_USE_SPECIFIC

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
    detail_url_kwargs = ('current_page',)

    # default option value overrides
    default_max_levels = settings.DEFAULT_SECTION_MENU_MAX_LEVELS
    default_use_specific = settings.DEFAULT_SECTION_MENU_USE_SPECIFIC

    def clean_detail_url_kwargs(self, url_kwargs):
        url_kwargs = super().clean_detail_url_kwargs(url_kwargs)

        # Ensure 'current_page' is a valid page
        current_page_id = url_kwargs['current_page']
        try:
            current_page = Page.objects.get(id=current_page_id)
        except:
            raise exceptions.ValidationError(
                "No page could be found matching the ID '%s' supplied for "
                "'current_page'." % url_kwargs['current_page']
            )

        # Identify the 'section_root' from the 'current_page'
        url_kwargs['section_root'] = current_page
        return url_kwargs
