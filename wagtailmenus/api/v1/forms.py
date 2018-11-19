from django import forms
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from wagtail.core.models import Page, Site

from wagtailmenus.conf import constants, settings
from wagtailmenus.utils.misc import make_dummy_request


class UseSpecificChoiceField(forms.TypedChoiceField):

    default_error_messages = {
        'invalid_choice': _(
            '%(value)s is not valid. The value must be one of: '
        ) + ','.join(str(v) for v in constants.USE_SPECIFIC_VALUES)
    }

    def __init__(self, *args, **kwargs):
        defaults = {
            'choices': constants.USE_SPECIFIC_CHOICES,
            'coerce': int,
            'empty_value': None,
        }
        kwargs.update({k: v for k, v in defaults.items() if k not in kwargs})
        super().__init__(*args, **kwargs)


class PageChoiceField(forms.ModelChoiceField):

    default_error_messages = {
        'invalid_choice': _('%(value)s is not a valid page ID')
    }

    def __init__(self, *args, **kwargs):
        if 'queryset' not in 'kwargs':
            kwargs['queryset'] = Page.objects.none()
        super().__init__(*args, **kwargs)


class SiteChoiceField(forms.ModelChoiceField):

    default_error_messages = {
        'invalid_choice': _('%(value)s is not a valid site ID')
    }

    def __init__(self, *args, **kwargs):
        if 'queryset' not in 'kwargs':
            kwargs['queryset'] = Site.objects.none()
        super().__init__(*args, **kwargs)


class ArgValidatorForm(forms.Form):
    apply_active_classes = forms.BooleanField(required=False)
    allow_repeating_parents = forms.BooleanField(required=False)
    use_absolute_page_urls = forms.BooleanField(required=False)
    current_url = forms.URLField(required=False)
    current_page = PageChoiceField(required=False)
    site = SiteChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        self._view = kwargs.pop('view', None)
        self._request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['current_page'].queryset = Page.objects.all()
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
        url = self.cleaned_data['current_url']
        if not url:
            return None
        self._dummy_request = make_dummy_request(url=url, original_request=self._request)
        return self._dummy_request

    def derive_site(self, data):
        error_msg = _(
            "This value was not provided and could not be derived from "
            "'current_url'."
        )
        if not data['current_url']:
            self.add_error('site', error_msg)
            return

        request = self.get_dummy_request()
        try:
            data['site'] = Site.find_for_request(request)
        except Site.DoesNotExist:
            self.add_error('site', error_msg)

    def derive_current_page(self, data, force_derivation=False):
        if not force_derivation and not data.get('apply_active_classes'):
            return

        # 'current_url' and 'site' values are required to derive a
        # 'current_page' value, so we only want to continue if both are present.

        # raising errors is only necessary if derivation if is crucial (e.g.
        # for deriving other values from) - in which case 'force_derivation'
        # will be True
        if not data['current_url']:
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
                    data['best_match_page'] = best_match
            except Http404:
                # Remove a path component and try again
                path_components.pop()
            first_run = False

        if force_derivation and not data['current_page']:
            self.add_error('current_page', _(
                "This value was not provided and could not be derived from "
                "'current_url'."
            ))

    def derive_ancestor_page_ids(self, data):
        page = data['current_page'] or data.get('best_match_page')
        if page:
            data['ancestor_page_ids'] = set(
                page.get_ancestors(inclusive=bool('best_match_page' in data))
                .filter(depth__gte=settings.SECTION_ROOT_DEPTH)
                .values_list('id', flat=True)
            )
        else:
            data['ancestor_page_ids'] = ()


class MenuModelArgValidatorForm(ArgValidatorForm):
    max_levels = forms.IntegerField(required=False, min_value=1, max_value=5)
    use_specific = UseSpecificChoiceField(required=False)


class MenuClassArgValidatorForm(ArgValidatorForm):
    max_levels = forms.IntegerField(min_value=1, max_value=5)
    use_specific = UseSpecificChoiceField()


class MainMenuArgValidatorForm(MenuModelArgValidatorForm):
    pass


class FlatMenuArgValidatorForm(MenuModelArgValidatorForm):
    handle = forms.SlugField()


class ChildrenMenuArgValidatorForm(MenuClassArgValidatorForm):
    parent_page = PageChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent_page'].queryset = Page.objects.all()

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
        if data['current_page']:
            data['parent_page'] = data['current_page']
        else:
            self.add_error('parent_page', _(
                "This value was not provided and could not be derived from "
                "'current_url' or 'current_page'.")
            )

    def derive_current_page(self, data, force_derivation=False):
        """
        Overrides ArgValidatorForm.derive_current_page(),
        because if neither 'parent_page' or 'current_page' have been
        provided, we want to force derivation of 'current_page', so that it
        can serve as a stand-in for 'parent_page'.
        """
        force_derivation = force_derivation or (
            not data['parent_page'] and not data['current_page']
        )
        super().derive_current_page(data, force_derivation)


class SectionMenuArgValidatorForm(MenuClassArgValidatorForm):
    section_root_page = PageChoiceField(required=False)

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
        page = data['current_page']
        section_root_depth = settings.SECTION_ROOT_DEPTH
        if page is None or page.depth < section_root_depth:
            self.add_error('section_root_page', _(
                "The value was not provided and cannot be derived from "
                "'current_url' or 'current_page'"
            ))
            return
        if page.depth > section_root_depth:
            data['section_root_page'] = page.get_ancestors().get(
                depth__exact=section_root_depth)
        else:
            data['section_root_page'] = page

    def derive_current_page(self, data, force_derivation=False):
        """
        Overrides ArgValidatorForm.derive_current_page(),
        because if neither 'section_root_page' or 'current_page' have been
        provided, we want to force derivation of 'current_page', so that we
        are able to derive 'section_root_page' from it.
        """
        force_derivation = force_derivation or (
            not data['section_root_page'] and not data['current_page']
        )
        super().derive_current_page(data, force_derivation)
