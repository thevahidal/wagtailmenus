from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response

from wagtailmenus.conf import settings

from . import forms
from . import serializers


class RenderMenuView(APIView):
    menu_class = None
    arg_validator_form_class = None
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
                "For subclasses of RenderMenuView, you must set the "
                "'menu_class' attribute or override the "
                "get_menu_class() class method."
            )
        return self.menu_class

    def get_arg_validator_form_class(self):
        if self.arg_validator_form_class is None:
            raise NotImplementedError(
                "For subclasses of RenderMenuView, you must set the "
                "'arg_validator_form_class' attribute or override the "
                "get_arg_validator_form_class) class method."
            )
        return self.arg_validator_form_class

    def get_arg_validator_form(self, request, *args, **kwargs):
        init_kwargs = self.get_arg_validator_form_kwargs(request)
        return self.get_arg_validator_form_class()(**init_kwargs)

    def get_arg_validator_form_kwargs(self, request):
        return {
            'data': request.GET,
            'initial': self.get_arg_validator_form_initial(request),
            'request': request,
            'view': self,
        }

    def get_arg_validator_form_initial(self, request):
        return {
            'max_levels': self.max_levels_default,
            'use_specific': self.use_specific_default,
            'apply_active_classes': self.apply_active_classes_default,
            'allow_repeating_parents': self.allow_repeating_parents_default,
            'use_absolute_page_urls': self.use_absolute_page_urls_default,
        }

    def get_menu_serializer_class(self):
        if self.menu_serializer_class is None:
            raise NotImplementedError(
                "For subclasses of RenderMenuView, you must set the "
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
        form = self.get_arg_validator_form(request, *args, **kwargs)

        if not form.is_valid():
            raise ValidationError(form.errors)

        # Get a menu instance using the valid data
        menu_instance = self.get_menu_instance(request, form)

        # Create a serializer for this menu instance
        menu_serializer = self.get_menu_serializer(menu_instance, *args, **kwargs)
        return Response(menu_serializer.data)

    def get_menu_instance(self, request, form):
        """
        The Menu classes themselves are responsible for getting/creating menu
        instances and preparing them for rendering. So, the role of this
        method is to bundle up all available data into a format that
        ``Menu._get_render_prepared_object()`` will understand, and call that.
        """

        data = dict(form.cleaned_data)

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


class RenderMainMenuView(RenderMenuView):
    menu_class = settings.models.MAIN_MENU_MODEL
    arg_validator_form_class = forms.MainMenuArgValidatorForm
    menu_serializer_class = serializers.MainMenuSerializer


class RenderFlatMenuView(RenderMenuView):
    menu_class = settings.models.MAIN_MENU_MODEL
    arg_validator_form_class = forms.FlatMenuArgValidatorForm
    menu_serializer_class = serializers.FlatMenuSerializer


class RenderChildrenMenuView(RenderMenuView):
    menu_class = settings.objects.CHILDREN_MENU_CLASS
    arg_validator_form_class = forms.ChildrenMenuArgValidatorForm
    menu_serializer_class = serializers.ChildrenMenuSerializer

    # argument default overrides
    max_levels_default = settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS
    use_specific_default = settings.DEFAULT_CHILDREN_MENU_USE_SPECIFIC
    apply_active_classes_default = False


class RenderSectionMenuView(RenderMenuView):
    menu_class = settings.objects.SECTION_MENU_CLASS
    arg_validator_form_class = forms.SectionMenuArgValidatorForm
    menu_serializer_class = serializers.SectionMenuSerializer

    # argument default overrides
    max_levels_default = settings.DEFAULT_SECTION_MENU_MAX_LEVELS
    use_specific_default = settings.DEFAULT_SECTION_MENU_USE_SPECIFIC
