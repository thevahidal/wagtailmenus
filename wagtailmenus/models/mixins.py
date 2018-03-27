from django.utils.functional import cached_property
from django.template.loader import get_template, select_template

from .. import app_settings


class DefinesSubMenuTemplatesMixin:
    sub_menu_template_name = None  # set to use a specific default template

    def get_sub_menu_template(self, level=1):
        if not hasattr(self, '_sub_menu_templates_by_level'):
            # This will be used to cache fetched template instance
            self._sub_menu_templates_by_level = {}
        elif level in self._sub_menu_templates_by_level:
            # Return a cached template instance
            return self._sub_menu_templates_by_level[level]
        # Identify a fetch a new template instance for `level`
        template_name = self.get_sub_menu_template_name_for_level(level)
        if template_name:
            t = get_template(template_name)
        else:
            t = select_template(self.get_sub_menu_template_names())
        # Cache the template instance before returning
        self._sub_menu_templates_by_level[level] = t
        return t

    def get_sub_menu_template_name_for_level(self, level):
        # Prefer the 'sub_menu_template_name' passed as an option value,
        # followed by a 'sub_menu_template_name' attribute on the menu class
        template_name = self._option_vals.sub_menu_template_name or \
            self.sub_menu_template_name
        if template_name:
            return template_name

        # Then prefer 'sub_menu_template_names' passed as an option value,
        # followed by default template names (if values have been specified via
        # the relevant app settings)
        template_names = self._option_vals.sub_menu_template_names or \
            self.get_default_sub_menu_template_names()
        if template_names:
            # Use the sub_menu template specified for this exact level if
            # there is one. Otherwise, use the last item in the list
            try:
                return template_names[level - 1]
            except KeyError:
                return template_names[-1]

    @cached_property
    def sub_menu_template(self):
        return self.get_sub_menu_template()

    def get_sub_menu_template_names(self):
        """Return a list of template paths/names to search when
        rendering a sub menu for an instance of this class. The list should be
        ordered with most specific names first, since the first template found
        to exist will be used for rendering"""
        current_site = self._contextual_vals.current_site
        template_names = []
        menu_str = self.menu_short_name
        if app_settings.SITE_SPECIFIC_TEMPLATE_DIRS and current_site:
            hostname = current_site.hostname
            template_names.extend([
                "menus/%s/%s/sub_menu.html" % (hostname, menu_str),
                "menus/%s/%s_sub_menu.html" % (hostname, menu_str),
                "menus/%s/sub_menu.html" % hostname,
            ])
        template_names.extend([
            "menus/%s/sub_menu.html" % menu_str,
            "menus/%s_sub_menu.html" % menu_str,
            app_settings.DEFAULT_SUB_MENU_TEMPLATE,
        ])
        return template_names

    def get_context_data(self, **kwargs):
        """
        Include the name of the sub-menu template in the context. This is
        purely for backwards compatibility. Any sub menus rendered as part of
        this menu will call `sub_menu_template` on the original menu instance
        to get an actual `Template`
        """
        data = {}
        if self._contextual_vals.current_level == 1 and self.max_levels > 1:
            data['sub_menu_template'] = self.sub_menu_template.template.name
        data.update(kwargs)
        return super().get_context_data(**data)
