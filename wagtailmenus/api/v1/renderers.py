from django.template import loader
from rest_framework.renderers import BrowsableAPIRenderer


class BrowsableAPIRendererWithParamValidatorForm(BrowsableAPIRenderer):

    def get_filter_form(self, data, view, request):
        form = view._param_validator_form
        template = loader.get_template(self.filter_template)
        context = {'elements': [form.to_html(request, view)]}
        return template.render(context)
