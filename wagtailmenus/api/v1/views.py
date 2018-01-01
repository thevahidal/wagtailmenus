from rest_framework.views import APIView
from rest_framework.response import Response

from wagtailmenus.conf import settings

from . import serializers


class MenuRenderView(APIView):
    menu_class = None
    # serializers
    argument_serializer_class = None
    menu_serializer_class = None
    # argument default values
    max_levels_default = None
    use_specific_default = None
    apply_active_classes_default = True
    allow_repeating_parents_default = True
    use_absolute_page_urls_default = False

    def get_menu_class(self):
        if self.menu_class is None:
            raise NotImplementedError(
                "For subclasses of MenuRenderView, you must set the "
                "'menu_class' attribute or override the "
                "get_menu_class() class method."
            )
        return self.menu_class

    def get_argument_serializer_class(self):
        if self.argument_serializer_class is None:
            raise NotImplementedError(
                "For subclasses of MenuRenderView, you must set the "
                "'argument_serializer_class' attribute or override the "
                "get_argument_serializer_class) class method."
            )
        return self.argument_serializer_class

    def get_argument_serializer(self, request, *args, **kwargs):
        cls = self.get_argument_serializer_class()
        kwargs['context'] = self.get_argument_serializer_context()

        # Mix default argument values into GET where not specified
        data = request.GET.copy()
        for key, val in self.get_default_argument_values():
            if key not in data:
                data[key] = val

        return cls(data=data, *args, **kwargs)

    def get_argument_serializer_context(self):
        return {
            'request': self.request,
            'view': self,
        }

    def get_default_argument_values(self):
        defaults = {
            'max_levels': self.max_levels_default,
            'use_specific': self.use_specific_default,
            'apply_active_classes': self.apply_active_classes_default,
            'allow_repeating_parents': self.allow_repeating_parents_default,
            'use_absolute_page_urls': self.use_absolute_page_urls_default,
        }
        return {key: val for key, val in defaults if val is not None}

    def get_menu_serializer_class(self):
        if self.menu_serializer_class is None:
            raise NotImplementedError(
                "For subclasses of MenuRenderView, you must set the "
                "'menu_serializer_class' attribute or override the "
                "get_menu_serializer_class() class method."
            )
        return self.menu_serializer_class

    def get_menu_serializer(self, instance, *args, **kwargs):
        cls = self.get_menu_serializer_class()
        kwargs['context'] = self.get_menu_serializer_context()
        return cls(instance=instance, *args, **kwargs)

    def get_menu_serializer_context(self):
        return {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self,
        }

    def get(self, request, *args, **kwargs):
        # Ensure all necessary argument values are present and valid
        arg_serializer = self.get_argument_serializer(request, *args, **kwargs)

        # Raise errors if option values are invalid
        arg_serializer.is_valid(raise_exception=True)

        # Get a menu instance using the valid data
        menu_instance = self.get_menu_instance(request, arg_serializer.data)

        # Create a serializer for this menu instance
        menu_serializer = self.get_menu_serializer(menu_instance, *args, **kwargs)
        return Response(menu_serializer.data)

    def get_menu_instance(self, request, data):
        """
        The Menu classes themselves are responsible for getting/creating menu
        instances and preparing them for rendering. So, the role of this
        method is to bundle up all available data into a format that
        ``Menu._get_render_prepared_object()`` will understand, and call that.
        """

        # Menus are typically rendered from an existing ``RequestContext``
        # object, which we do not have. However, we can provide a dictionary
        # with a similar-looking data structure.
        dummy_context = {
            'request': request,
            'current_site': data.pop('site'),
            'wagtailmenus_vals': {
                'current_page': data.pop('current_page', None),
                'section_root': data.pop('section_root', None),
                'current_page_ancestor_ids': data.pop('ancestor_page_ids', ()),
            }
        }
        cls = self.get_menu_class()
        data['add_sub_menus_inline'] = True
        return cls._get_render_prepared_object(dummy_context, **data)

    def derive_option_values_from_arg_data(self, arg_data, site, current_page):
        # Any remaining values can safely be considered as 'option values'
        option_values = arg_data.copy()
        # Setting this to allow the serializer to render multi-level menu items
        option_values['add_sub_menus_inline'] = True
        return option_values


class MainMenuRenderView(MenuRenderView):
    menu_class = settings.models.MAIN_MENU_MODEL
    # serializers
    argument_serializer_class = serializers.MainMenuArgumentSerializer
    menu_serializer_class = serializers.MainMenuSerializer


class FlatMenuRenderView(MenuRenderView):
    menu_class = settings.models.MAIN_MENU_MODEL
    # serializers
    argument_serializer_class = serializers.FlatMenuArgumentSerializer
    menu_serializer_class = serializers.FlatMenuSerializer


class ChildrenMenuRenderView(MenuRenderView):
    menu_class = settings.objects.CHILDREN_MENU_CLASS
    # serializers
    argument_serializer_class = serializers.ChildrenMenuArgumentSerializer
    menu_serializer_class = serializers.ChildrenMenuSerializer
    # argument default overrides
    max_levels_default = settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS
    use_specific_default = settings.DEFAULT_CHILDREN_MENU_USE_SPECIFIC
    apply_active_classes_default = False

    def derive_option_values_from_arg_data(self, arg_data, site, current_page):
        option_values = super().derive_option_values_from_arg_data(arg_data)
        if not option_values.get('parent_page'):
            option_values['parent_page'] = current_page


class SectionMenuRenderView(MenuRenderView):
    menu_class = settings.objects.SECTION_MENU_CLASS
    # serializers
    argument_serializer_class = serializers.SectionMenuArgumentSerializer
    menu_serializer_class = serializers.SectionMenuSerializer
    # argument default overrides
    max_levels_default = settings.DEFAULT_SECTION_MENU_MAX_LEVELS
    use_specific_default = settings.DEFAULT_SECTION_MENU_USE_SPECIFIC
