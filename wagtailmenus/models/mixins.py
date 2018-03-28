import warnings
from django.utils.functional import cached_property
from django.template.loader import get_template, select_template

from .. import app_settings
from ..utils.deprecation import RemovedInWagtailMenus211Warning


def get_template_name_for_level(template_name_list, level):
    assert level >= 2
    if not template_name_list:
        return
    try:
        return template_name_list[level - 2]
    except KeyError:
        return template_name_list[-1]


class DefinesSubMenuTemplatesMixin:
    # Use to specify a single sub menu template for all levels
    sub_menu_template_name = None
    # Use to specify sub menu templates for each level
    sub_menu_template_names = None

    def _get_specified_sub_menu_template_name(self, level):
        """
        Called by get_sub_menu_template(). Iterates through the various ways in
        which developers can specify sub menu templates to be used, and returns
        the name of the most suitable template for the provided ``level``. It's
        possible that no template has been specified, in which case, a ``None``
        value will be returned. Values are checked in the following order:

        1.  The ``sub_menu_template`` value passed to the template tag (if
            provided)
        2.  The most suitable template from the ``sub_menu_templates`` list
            passed to the template tag (if provided)
        3.  The ``sub_menu_template_name`` attribute set on the menu class (if
            set)
        4.  The most suitable template from a list of templates set as the
            ``sub_menu_template_names`` attribute on the menu class (if set)
        5.  The most suitable template from a list of templates returned by
            self.get_sub_menu_template_names_from_setting()
        """
        return self._option_vals.sub_menu_template_name or \
            get_template_name_for_level(
                self._option_vals.sub_menu_template_names, level
            ) or \
            self.sub_menu_template_name or \
            get_template_name_for_level(
                self.sub_menu_template_names, level
            ) or \
            get_template_name_for_level(
                self.get_sub_menu_template_names_from_setting(), level
            )

    def get_sub_menu_template(self, level=2):
        if not hasattr(self, '_sub_menu_templates_by_level'):
            # Initialise cache for this menu instance
            self._sub_menu_templates_by_level = {}
        elif level in self._sub_menu_templates_by_level:
            # Return a cached template instance
            return self._sub_menu_templates_by_level[level]
        # Get a new template instance for the provided `level`
        template_name = self._get_specified_sub_menu_template_name(level)
        if template_name:
            # A template was specified somehow
            t = get_template(template_name)
        else:
            # A template wasn't specified, so search the filesystem for one
            t = select_template(self.get_sub_menu_template_names())
        # Cache the template instance before returning
        self._sub_menu_templates_by_level[level] = t
        return t

    @cached_property
    def sub_menu_template(self):
        warnings.warn(
            "The 'sub_menu_template' property method is deprecated in favour "
            "of always calling get_sub_menu_template() with the 'level' "
            "argument to return level-specific templates.",
            category=RemovedInWagtailMenus211Warning
        )
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
