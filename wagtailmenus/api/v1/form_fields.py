from django import forms
from django.utils.translation import ugettext_lazy as _
from wagtail.core.models import Page, Site

from wagtailmenus.conf import constants


class JavascriptStyleBooleanSelect(forms.Select):
    def __init__(self, attrs=None):
        choices = (
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super().__init__(attrs, choices)

    def format_value(self, value):
        return {
            True: 'true',
            False: 'false',
            'true': 'true',
            'false': 'false',
        }[value]

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        return {
            True: True,
            'True': True,
            'False': False,
            False: False,
            'true': True,
            'false': False,
        }.get(value)


class BooleanChoiceField(forms.BooleanField):
    widget = JavascriptStyleBooleanSelect


class UseSpecificChoiceField(forms.TypedChoiceField):

    default_error_messages = {
        'invalid_choice': _(
            '%(value)s is not valid. The value must be one of: '
        ) + ','.join(str(v) for v in constants.USE_SPECIFIC_VALUES)
    }

    def __init__(self, *args, **kwargs):
        empty_label = kwargs.pop('empty_label', '-----')
        choices = (('', empty_label),) + constants.USE_SPECIFIC_CHOICES
        defaults = {
            'choices': choices,
            'coerce': int,
            'empty_value': None,
            'help_text': _(
                "How 'specific' page objects should be utilised when "
                "generating the result."
            )
        }
        kwargs.update({k: v for k, v in defaults.items() if k not in kwargs})
        super().__init__(*args, **kwargs)


class MaxLevelsChoiceField(forms.TypedChoiceField):

    default_error_messages = {
        'invalid_choice': _(
            '%(value)s is not valid. The value must be one of: '
        ) + ','.join(str(v) for v, l in constants.MAX_LEVELS_CHOICES)
    }

    def __init__(self, *args, **kwargs):
        empty_label = kwargs.pop('empty_label', '-----')
        choices = (('', empty_label),) + constants.MAX_LEVELS_CHOICES
        defaults = {
            'choices': choices,
            'coerce': int,
            'empty_value': None,
            'help_text': _(
                "The maximum number of levels of menu items that should be "
                "included in the result."
            )
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
