from django import forms
from django.conf import settings as django_settings
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from django.template import loader
from wagtail.core.models import Page, Site

from wagtailmenus.conf import settings
from wagtailmenus.utils.misc import make_dummy_request
from . import form_fields as fields


class BaseAPIViewArgumentForm(forms.Form):
    """
    A form class that looks for 'view' and 'request' arguments at initialisation,
    and is capable of rendering itself to a template (in a similar fashion to
    ``django_filters.rest_framework.DjangoFilterBackend``). Schema support
    may also have to be added in future.
    """
    def __init__(self, *args, **kwargs):
        self._view = kwargs.pop('view', None)
        self._request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

    @property
    def template(self):
        if 'crispy_forms' in django_settings.INSTALLED_APPS:
            return 'wagtailmenus/api/forms/crispy_form.html'
        return 'wagtailmenus/api/forms/form.html'

    def to_html(self, request, view):
        template = loader.get_template(self.template)
        context = {'form': self}
        return template.render(context, request)

    @property
    def helper(self):
        try:
            from crispy_forms.helper import FormHelper
            from crispy_forms.layout import Layout, Submit
        except ImportError:
            return

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
        label=_("Current URL"),
        help_text=_(
            "The full URL of the page you are generating the menu for. "
            "Used for deriving 'site' and 'current_page' values in cases "
            "where those values are unavailable or not applicable. For "
            "example, if the URL does not map to a Page object exactly."
        ),
    )
    site = fields.SiteChoiceField(
        required=False,
        help_text=_(
            "The site you are generating the menu for. Affects how URLs for "
            "page links are calculated (using relative or absolute URLs). "
            "Supply where possible for optimal performance. If not supplied, "
            "the view will attempt to derive this value from 'current_url'."
        ),
    )
    current_page = fields.PageChoiceField(
        required=False,
        help_text=_(
            "The page you are generating the menu for. Used to determine "
            "which 'active classes' are applied to menu items when using the "
            "'apply_active_classes' option, and for deriving other values "
            "from in some cases. If not supplied, the view will attempt to "
            "derive this value from 'current_url'."
        ),
    )
    apply_active_classes = forms.BooleanField(
        required=False,
        help_text=_(
            "Add 'active' and 'ancestor' classes to menu items to help "
            "indicate a user's current position within the menu structure."
        ),
    )
    allow_repeating_parents = forms.BooleanField(
        required=False,
        help_text=_(
            "Permit pages inheriting from MenuPage or MenuPageMixin "
            "to add duplicates of themselves to their 'children' when "
            "appearing as menu items."
        )
    )
    use_absolute_page_urls = forms.BooleanField(
        label=_('Use absolute page URLs'),
        required=False,
        help_text=_(
            "When calculating URLs for menu items that link to pages, use the "
            "full URL where possible. For example: "
            "'https://www.site.com/page-url'."
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['current_page'].queryset = Page.objects.filter(depth__gt=1)
        self.fields['site'].queryset = Site.objects.all()
        self._dummy_request = None

    def clean(self):
        """
        Allow 'site' and 'current_page' to be derived from other values if they
        were not provided as data.
        """
        data = self.cleaned_data

        if not data['site']:
            self.derive_site(data)

        if not data['current_page']:
            self.derive_current_page(data)

        if data.get('apply_active_classes'):
            self.derive_ancestor_page_ids(data)

        return data

    def get_dummy_request(self):
        if self._dummy_request:
            return self._dummy_request
        url = self.cleaned_data.get('current_url')
        if not url:
            return None
        self._dummy_request = make_dummy_request(url=url, original_request=self._request)
        return self._dummy_request

    def derive_site(self, data):
        if data.get('current_url'):
            request = self.get_dummy_request()
            try:
                data['site'] = Site.find_for_request(request)
            except Site.DoesNotExist:
                self.add_error('site', _(
                    "This value was not provided and could not be derived "
                    "from 'current_url'."
                ))

    def derive_current_page(self, data, force_derivation=False, accept_best_match=True):
        if not force_derivation and not data.get('apply_active_classes'):
            return

        # 'current_url' and 'site' values are required to derive a
        # 'current_page' value, so we only want to continue if both are present.

        # raising errors is only necessary if derivation if is crucial (e.g.
        # for deriving other values from) - in which case 'force_derivation'
        # will be True
        if not data.get('current_url'):
            if force_derivation:
                self.add_error('current_page', _(
                    "This value was not provided and could not be derived from "
                    "'current_url'."
                ))
            return
        elif not data['site']:
            if force_derivation:
                self.add_error('current_page', _(
                    "This value was not provided and could not be derived, "
                    "because 'site' cannot be determined."
                ))
            return

        site = data['site']
        request = self.get_dummy_request()
        path_components = [pc for pc in request.path.split('/') if pc]
        first_run = True
        best_match = None
        while path_components and best_match is None:
            try:
                best_match = site.root_page.specific.route(request, path_components)[0]
                if first_run:
                    # A page was found matching the exact path, so it's
                    # safe to assume it's the 'current page'
                    data['current_page'] = best_match
                else:
                    # This could still be useful for deriving 'ancestor_ids'
                    # or 'section_root_page'
                    data['best_match_page'] = best_match
            except Http404:
                if not accept_best_match:
                    break  # give up
                # Remove a path component and try again
                path_components.pop()
            first_run = False

        if not accept_best_match and not data['current_page']:
            self.add_error('current_page', _(
                "This value was not provided and could not be derived from "
                "'current_url'."
            ))

    def derive_ancestor_page_ids(self, data):
        page = data.get('current_page') or data.get('best_match_page')
        if page:
            data['ancestor_page_ids'] = set(
                page.get_ancestors(inclusive=data.get('current_page') is None)
                .filter(depth__gte=settings.SECTION_ROOT_DEPTH)
                .values_list('id', flat=True)
            )
        else:
            data['ancestor_page_ids'] = ()


class BaseMenuModelGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):
    max_levels = fields.MaxLevelsChoiceField(
        required=False,
        empty_label=_('Default: Use the value set for the menu object'),
    )
    use_specific = fields.UseSpecificChoiceField(
        required=False,
        empty_label=_('Default: Use the value set for the menu object'),
    )


class MainMenuGeneratorArgumentForm(BaseMenuModelGeneratorArgumentForm):
    site = fields.SiteChoiceField(
        required=False,
        help_text=_(
            "The site you are generating a menu for. Used to retrieve "
            "the relevant menu object from the database. If not supplied, the "
            "view will attempt to derive this value from 'current_url'. "
            "However, for optimal performance, it's recommended that you "
            "supply it where possible."
        ),
    )

    field_order = (
        'current_url',
        'site',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
    )


class FlatMenuGeneratorArgumentForm(BaseMenuModelGeneratorArgumentForm):
    handle = forms.SlugField(
        help_text=_(
            "The 'handle' for the flat menu you wish to generate. For "
            "example: 'info' or 'contact'."
        )
    )
    fall_back_to_default_site_menus = forms.BooleanField(
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
        'site',
        'fall_back_to_default_site_menus',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
    )


class ChildrenMenuGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):
    parent_page = fields.PageChoiceField(
        required=False,
        help_text=_(
            "The page you wish to show children page links for (if different "
            "to 'current_page')."
        )
    )
    max_levels = fields.MaxLevelsChoiceField()
    use_specific = fields.UseSpecificChoiceField()

    field_order = (
        'current_url',
        'parent_page',
        'site',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent_page'].queryset = Page.objects.filter(depth__gt=1)

    def clean(self):
        """
        Allow 'parent_page' to be derived from other values if it was not
        provided.
        """
        data = super().clean()

        if not data['parent_page']:
            self.derive_parent_page(data)

        return data

    def derive_parent_page(self, data):
        """
        If possible, derive a value for 'parent_page' and update the supplied
        ``data`` dictionary to include it.
        """
        if data.get('current_page'):
            data['parent_page'] = data['current_page']
        else:
            self.add_error('parent_page', _(
                "This value was not provided and could not be derived from "
                "'current_page' or 'current_url'."
            ))

    def derive_current_page(self, data, force_derivation=False, accept_best_match=False):
        """
        Overrides ArgValidatorForm.derive_current_page(),
        because if neither 'parent_page' or 'current_page' have been
        provided, we want to force derivation of 'current_page', so that it
        can serve as a stand-in for 'parent_page'.

        A 'best match' is not a good enough stand-in for 'parent_page', so we
        the 'accept_best_match' is False by default.
        """
        force_derivation = force_derivation or (
            not data['parent_page'] and not data.get('current_page')
        )
        super().derive_current_page(data, force_derivation, accept_best_match)


class SectionMenuGeneratorArgumentForm(BaseMenuGeneratorArgumentForm):
    section_root_page = fields.PageChoiceField(
        required=False,
        help_text=_(
            "The root page for the current 'section', whose children and "
            "other decendents you want show menu items for. If not supplied, "
            "the view will attempt to derive this value from 'current_page' "
            "or 'current_url'."
        )
    )
    max_levels = fields.MaxLevelsChoiceField()
    use_specific = fields.UseSpecificChoiceField()

    field_order = (
        'current_url',
        'section_root_page',
        'site',
        'current_page',
        'max_levels',
        'use_specific',
        'apply_active_classes',
        'allow_repeating_parents',
        'use_absolute_page_urls',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['section_root_page'].queryset = Page.objects.filter(
            depth__exact=settings.SECTION_ROOT_DEPTH)

    def clean(self):
        """
        Allow 'section_root_page' to be derived from other values if it was not
        provided.
        """
        data = super().clean()

        if not data['section_root_page']:
            self.derive_section_root_page(data)

        return data

    def derive_section_root_page(self, data):
        """
        If possible, derive a value for 'section_root_page' and update the
        supplied ``data`` dictionary to include it.
        """
        page = data.get('current_page') or data.get('best_match_page')
        section_root_depth = settings.SECTION_ROOT_DEPTH
        if page is None or page.depth < section_root_depth:
            self.add_error('section_root_page', _(
                "This value was not provided and could not be derived from "
                "'current_page' or 'current_url'."
            ))
            return
        if page.depth > section_root_depth:
            data['section_root_page'] = page.get_ancestors().get(
                depth__exact=section_root_depth)
        else:
            data['section_root_page'] = page

    def derive_current_page(self, data, force_derivation=False, accept_best_match=True):
        """
        Overrides ArgValidatorForm.derive_current_page(),
        because if neither 'section_root_page' or 'current_page' have been
        provided, we want to force derivation of 'current_page', so that we
        are able to derive 'section_root_page' from it.

        A 'best match' might be good enough to derive 'section_root_page', so
        we'll leave 'accept_best_match' as True by default.
        """
        force_derivation = force_derivation or (
            not data['section_root_page'] and not data.get('current_page')
        )
        super().derive_current_page(data, force_derivation, accept_best_match)
