from django import forms
from django.conf import settings as django_settings
from django.utils.translation import ugettext_lazy as _
from django.template import loader
from wagtail.core.models import Page, Site

from wagtailmenus.conf import settings
from wagtailmenus.api import form_fields as api_form_fields


class BaseAPIViewArgumentForm(forms.Form):
    """
    A form class that accepts 'view' and 'request' arguments at initialisation,
    is capable of rendering itself to a template (in a similar fashion to
    ``django_filters.rest_framework.DjangoFilterBackend``), and has some
    custom cleaning behaviour to better handle missing values.
    """
    def __init__(self, **kwargs):
        self._view = kwargs.pop('view')
        self._request = kwargs.pop('request')
        super().__init__(**kwargs)

    def full_clean(self):
        """
        Because non-required arguments are often not provided for API requests,
        and because request values are not 'posted' by the form, initial data
        misses it's usual opportunity to become a default value. This override
        changes that by supplementing ``self.data`` with initial values before
        the usual cleaning happens.
        """
        self.supplement_missing_data_with_initial_values()
        return super().full_clean()

    def supplement_missing_data_with_initial_values(self):
        supplementary_vals = {}
        for name, field in self.fields.items():
            if not field.required and self.data.get(name) in ('', None):
                val = self.get_initial_for_field(field, name)
                if val is not None:
                    supplementary_vals[name] = val

        if supplementary_vals:
            if not getattr(self.data, '_mutable', True):
                self.data = self.data.copy()
            self.data.update(supplementary_vals)
        return self.data

    @property
    def template_name(self):
        if 'crispy_forms' in django_settings.INSTALLED_APPS:
            return 'wagtailmenus/api/forms/crispy_form.html'
        return 'wagtailmenus/api/forms/form.html'

    def to_html(self, request):
        template = loader.get_template(self.template_name)
        context = {'form': self}
        return template.render(context, request)

    @property
    def helper(self):
        if 'crispy_forms' not in django_settings.INSTALLED_APPS:
            return

        from crispy_forms.helper import FormHelper
        from crispy_forms.layout import Layout, Submit

        layout_components = list(self.fields.keys()) + [
            Submit('', _('Submit'), css_class='btn-default'),
        ]
        obj = FormHelper()
        obj.form_method = 'GET'
        obj.template_pack = 'bootstrap3'
        obj.layout = Layout(*layout_components)
        return obj


class BaseMenuGeneratorArgumentForm(BaseAPIViewArgumentForm):
    current_url = forms.URLField(
        max_length=500,
        label=_("Current URL"),
        help_text=_(
            "The URL of the page you are generating the menu for, "
            "including scheme and domain). For example: "
            "'https://www.example.com/about-us/'."
        ),
    )
    current_page = api_form_fields.PageChoiceField(
        label=_('Current page'),
        required=False,
        help_text=_(
            "The ID of the Wagtail Page you are generating the menu for. "
            "If not provided, the endpoint will attempt to derive this "
            "from 'current_url', but providing this value (if available) "
            "will improve efficiency."
        ),
    )
    max_levels = api_form_fields.MaxLevelsChoiceField(
        label=_('Maximum levels'),
        required=False,
        help_text=_(
            "The maximum number of levels of menu items that should be "
            "included in the result. Defaults to the relevant setting value "
            "for this menu type."
        )
    )
    use_specific = api_form_fields.UseSpecificChoiceField(
        label=_('Specific page usage'),
        required=False,
        help_text=_(
            "How 'specific' page objects should be utilised when generating "
            "the result. Defaults to the relevant setting value for this menu "
            "type."
        )
    )
    apply_active_classes = api_form_fields.BooleanChoiceField(
        label=_('Apply active classes'),
        required=False,
        help_text=_(
            "Whether the view should set 'active_class' attributes on menu "
            "items to help indicate a user's current position within the menu "
            "structure. Defaults to the relevant setting value for this menu "
            "type."
        ),
    )
    allow_repeating_parents = api_form_fields.BooleanChoiceField(
        label=_('Allow repeating parents'),
        required=False,
        help_text=_(
            "Whether the view should allow pages inheriting from MenuPage or "
            "MenuPageMixin to add duplicates of themselves to their "
            "'children' when appearing as menu items. Defaults to the "
            "relevant setting value for this menu type."
        )
    )
    use_absolute_page_urls = api_form_fields.BooleanChoiceField(
        label=_('Use absolute page URLs'),
        required=False,
        help_text=_(
            "Whether the view should use absolute page URLs instead of "
            "relative ones for menu items that link to pages, regardless "
            "of whether the page is within the same 'site'. Defaults "
            "to False."
        )
    )
    language = forms.ChoiceField(
        label=_('Language'),
        required=False,
        choices=django_settings.LANGUAGES,
        initial=django_settings.LANGUAGE_CODE,
        help_text=_(
            "The language you wish to rendering the menu in. Must be one of "
            "the languages defined in your LANGUAGES setting. Will only "
            "affect the result if USE_I18N is True. Defaults to LANGUAGE_CODE."
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['current_page'].queryset = Page.objects.filter(depth__gt=1)
        if not django_settings.USE_I18N:
            self.fields['language'].widget = forms.HiddenInput()


class BaseMenuModelGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):
    max_levels = api_form_fields.MaxLevelsChoiceField(
        label=_('Maximum levels'),
        required=False,
        empty_label=_('Default: Use the value set for the menu object'),
        help_text=_(
            "The maximum number of levels of menu items that should be "
            "included in the result. Defaults to the 'max_levels' field value "
            "on the matching menu object."
        ),
    )
    use_specific = api_form_fields.UseSpecificChoiceField(
        label=_('Specific page usage'),
        required=False,
        empty_label=_('Default: Use the value set for the menu object'),
        help_text=_(
            "How 'specific' page objects should be utilised when generating "
            "the result. Defaults to the 'use_specific' field value on the "
            "matching menu object."
        ),
    )


class MainMenuGeneratorArgumentForm(BaseMenuModelGeneratorArgumentForm):
    field_order = (
        'current_url',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
        'language',
    )


class FlatMenuGeneratorArgumentForm(BaseMenuModelGeneratorArgumentForm):
    handle = api_form_fields.FlatMenuHandleField(
        label=_('Handle'),
        help_text=_(
            "The 'handle' for the flat menu you wish to generate. For "
            "example: 'info' or 'contact'."
        )
    )
    fall_back_to_default_site_menus = api_form_fields.BooleanChoiceField(
        label=_('Fall back to default site menus'),
        required=False,
        help_text=_(
            "If a menu cannot be found matching the provided 'handle' for the "
            "supplied (or derived) site, use the flat menu defined for the "
            "'default' site (if available)."
        )
    )

    field_order = (
        'current_url',
        'handle',
        'fall_back_to_default_site_menus',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
        'language',
    )


class ChildrenMenuGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):

    parent_page = api_form_fields.PageChoiceField(
        label=_("Parent page"),
        required=False,
        help_text=_(
            "The page you wish to show children page links for (if different "
            "to 'current_page')."
        )
    )

    field_order = (
        'current_url',
        'current_page',
        'parent_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
        'language',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent_page'].queryset = Page.objects.filter(depth__gt=1)


class SectionMenuGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):

    section_root_page = api_form_fields.PageChoiceField(
        label=_("Section root page"),
        required=False,
        help_text=_(
            "The root page for the 'section', whose children and other "
            "decendents you want show menu items for. If not supplied, the "
            "view will attempt to derive this from 'current_page' or "
            "'current_url'."
        )
    )

    field_order = (
        'current_url',
        'current_page',
        'section_root_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
        'language',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['section_root_page'].queryset = Page.objects.filter(
            depth__exact=settings.SECTION_ROOT_DEPTH)
