from __future__ import absolute_import, unicode_literals
import warnings

from collections import defaultdict, namedtuple

from django.db import models
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.template import Context
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from modelcluster.models import ClusterableModel
from wagtail.wagtailadmin.edit_handlers import (
    FieldPanel, MultiFieldPanel, InlinePanel)
from wagtail.wagtailcore import hooks
from wagtail.wagtailcore.models import Page

from .. import app_settings
from ..forms import FlatMenuAdminForm
from ..utils.deprecation import (
    RemovedInWagtailMenus26Warning, RemovedInWagtailMenus27Warning)
from ..utils.inspection import accepts_kwarg
from ..utils.misc import get_site_from_request
from .menuitems import MenuItem
from .pages import AbstractLinkPage


# ########################################################
# Base classes
# ########################################################

class Menu(object):
    """A base class that all other 'menu' classes should inherit from."""

    max_levels = 1
    use_specific = app_settings.USE_SPECIFIC_AUTO
    pages_for_display = None
    root_page = None  # Not relevant for all menu classes
    request = None
    menu_type = ''  # provided to hook methods
    menu_short_name = ''  # used to find templates
    add_self_to_context = True
    sub_menu_class = None

    @classmethod
    def get_sub_menu_class(cls):
        return cls.sub_menu_class or SubMenu

    @classmethod
    def format_contextual_vals(cls, context, menu_tag_name):
        ContextualVals = namedtuple('ContextualVals', (
            'current_site', 'current_level', 'original_menu_tag',
            'current_page', 'current_section_root_page',
            'current_page_ancestor_ids', 'template_engine'
        ))
        context_processor_vals = context.get('wagtailmenus_vals', {})
        return ContextualVals(
            get_site_from_request(context['request']),
            context.get('current_level', 0) + 1,
            context.get('original_menu_tag', menu_tag_name),
            context_processor_vals.get('current_page'),
            context_processor_vals.get('section_root'),
            context_processor_vals.get('current_page_ancestor_ids', ()),
            context.template.engine,
        )

    @classmethod
    def format_option_vals(cls, options):
        OptionVals = namedtuple('OptionVals', (
            'max_levels', 'use_specific', 'apply_active_classes',
            'allow_repeating_parents', 'use_absolute_page_urls',
            'template_name', 'sub_menu_template_name', 'extra'
        ))
        return OptionVals(
            options.pop('max_levels'),
            options.pop('use_specific'),
            options.pop('apply_active_classes'),
            options.pop('allow_repeating_parents'),
            options.pop('use_absolute_page_urls'),
            options.pop('template_name', ''),
            options.pop('sub_menu_template_name', ''),
            options  # anything left over will be stored as 'extra'
        )

    def clear_page_cache(self):
        try:
            del self.pages_for_display
        except AttributeError:
            pass
        try:
            del self.page_children_dict
        except AttributeError:
            pass

    def get_common_hook_kwargs(self):
        return {
            'request': self.request,
            'menu_type': self.menu_type,
            'max_levels': self.max_levels,
            'use_specific': self.use_specific,
            'menu_instance': self,
        }

    def get_base_page_queryset(self):
        qs = Page.objects.filter(
            live=True, expired=False, show_in_menus=True)
        # allow hooks to modify the queryset
        for hook in hooks.get_hooks('menus_modify_base_page_queryset'):
            kwargs = self.get_common_hook_kwargs()
            kwargs['root_page'] = self.root_page
            qs = hook(qs, **kwargs)
        return qs

    def set_max_levels(self, max_levels):
        if self.max_levels != max_levels:
            """
            Set `self.max_levels` to the supplied value and clear any cached
            attribute values set for a different `max_levels` value.
            """
            self.max_levels = max_levels
            self.clear_page_cache()

    def set_use_specific(self, use_specific):
        if self.use_specific != use_specific:
            """
            Set `self.use_specific` to the supplied value and clear some
            cached values where appropriate.
            """
            if(
                use_specific >= app_settings.USE_SPECIFIC_TOP_LEVEL and
                self.use_specific < app_settings.USE_SPECIFIC_TOP_LEVEL
            ):
                self.clear_page_cache()
                try:
                    del self.top_level_items
                except AttributeError:
                    pass

            self.use_specific = use_specific

    def set_request(self, request):
        """
        Set `self.request` to the supplied HttpRequest, so that developers can
        make use of it in subclasses
        """
        self.request = request
        warning_msg = (
            "The 'set_request' method is deprecated in favour of the storing "
            "the request alongside other values in 'render_init' View the "
            "2.5 release notes for more info: "
            "http://wagtailmenus.readthedocs.io/en/stable/releases/2.5.0.html"
        )
        warnings.warn(warning_msg, RemovedInWagtailMenus27Warning)

    def get_pages_for_display(self):
        raise NotImplementedError(
            "Subclasses of 'Menu' must define their own "
            "'get_pages_for_display' method")

    @cached_property
    def pages_for_display(self):
        return self.get_pages_for_display()

    def get_page_children_dict(self):
        """Returns a dictionary of lists, where the keys are 'path' values for
        pages, and the value is a list of children pages for that page."""
        children_dict = defaultdict(list)
        for page in self.pages_for_display:
            children_dict[page.path[:-page.steplen]].append(page)
        return children_dict

    @cached_property
    def page_children_dict(self):
        return self.get_page_children_dict()

    def get_children_for_page(self, page):
        """Return a list of relevant child pages for a given page."""
        return self.page_children_dict.get(page.path, [])

    def page_has_children(self, page):
        """Return a boolean indicating whether a given page has any relevant
        child pages."""
        return page.path in self.page_children_dict

    def render(self, menu_tag_name, context, **options):
        self.render_init(menu_tag_name, context, **options)
        return self.render_to_template(
            self.get_context_data(),
            self.get_template(),
        )

    def render_init(self, menu_tag_name, context, **options):
        self._parent_context = context
        self.request = context['request']
        self.contextual_vals = self.format_contextual_vals(context,
                                                           menu_tag_name)
        self.option_vals = self.format_option_vals(options)
        # TODO: Remove the below in version 2.7
        self.set_request(context['request'])

    def get_context_data(self, **kwargs):
        data = self._parent_context.flatten()
        data.update(self.contextual_vals._asdict())
        data.update(self.option_vals._asdict())
        data.update({
            'section_root': data['current_section_root_page'],
            'current_ancestor_ids': data['current_page_ancestor_ids'],
            'sub_menu_class': self.get_sub_menu_class(),
        })
        if self.add_self_to_context:
            data.update({
                'menu_instance': self,
                self.menu_type: self,
            })
        if 'menu_items' not in kwargs:
            data['menu_items'] = self.get_primed_menu_items()
        data.update(kwargs)
        return data

    def get_primed_menu_items(self):
        items = self.get_raw_menu_items()
        hook_kwargs = self.get_menu_item_modify_hook_kwargs()
        for hook in hooks.get_hooks('menus_modify_raw_menu_items'):
            items = hook(items, **hook_kwargs)
        items = self.modify_menu_items(self.prime_menu_items(items))
        for hook in hooks.get_hooks('menus_modify_primed_menu_items'):
            items = hook(items, **hook_kwargs)
        return items

    def get_menu_item_modify_hook_kwargs(self):
        cvals = self.contextual_vals
        opts = self.option_vals
        return {
            'menu_instance': self,
            'request': self.request,
            'parent_page': self.root_page,
            'current_site': cvals.current_site,
            'original_menu_tag': cvals.original_menu_tag,
            'current_page': cvals.current_page,
            'current_page_ancestor_ids': cvals.current_page_ancestor_ids,
            'current_level': cvals.current_level,
            'max_levels': self.max_levels,
            'use_specific': self.max_levels,
            'apply_active_classes': opts.apply_active_classes,
            'allow_repeating_parents': opts.allow_repeating_parents,
            'use_absolute_page_urls': opts.use_absolute_page_urls,
        }

    def get_raw_menu_items(self):
        raise NotImplementedError("Subclasses of 'Menu' must define their own "
                                  "'get_raw_menu_items' method")

    def modify_menu_items(self, menu_items):
        return menu_items

    def prime_menu_items(self, menu_items):
        """
        Prepare a list of `MenuItem` or `Page` objects for rendering to a menu
        template.
        """
        cvals = self.contextual_vals
        current_site = cvals.current_site
        current_page = cvals.current_page
        opts = self.option_vals

        active_css_class = app_settings.ACTIVE_CLASS
        ancestor_css_class = app_settings.ACTIVE_ANCESTOR_CLASS

        stop_at_this_level = (cvals.current_level >= self.max_levels)
        primed_menu_items = []

        for item in menu_items:

            if isinstance(item, MenuItem):
                """
                `menu_items` is a list of `MenuItem` objects from
                `Menu.top_level_items`. Any `link_page` values will have been
                replaced with specific pages if necessary
                """
                page = item.link_page
                menuitem = item
                setattr(item, 'text', item.menu_text)

            elif issubclass(item.specific_class, AbstractLinkPage):
                """
                Special treatment for link pages
                """
                if type(item) is Page:
                    item = item.specific
                if item.show_in_menus_custom(
                    current_site,
                    self,
                    cvals.original_menu_tag
                ):
                    setattr(item, 'active_class', item.extra_classes)
                    setattr(item, 'text', item.menu_text(self.request))
                    if self.option_vals.use_absolute_page_urls:
                        url = item.get_full_url(request=self.request)
                    else:
                        url = item.relative_url(current_site, self.request)
                    setattr(item, 'href', url)
                    primed_menu_items.append(item)
                continue

            else:
                """
                `menu_items` is a list of `Page` objects
                """
                page = item
                menuitem = None
                text = getattr(
                    page,
                    app_settings.PAGE_FIELD_FOR_MENU_ITEM_TEXT,
                    page.title
                )
                setattr(item, 'text', text)

            if page:
                """
                Work out whether this item should be flagged as needing
                a sub-menu. It can be expensive, so we try to only do the
                working out when absolutely necessary.
                """
                has_children_in_menu = False
                if (
                    not stop_at_this_level and
                    page.depth >= app_settings.SECTION_ROOT_DEPTH and
                    (menuitem is None or menuitem.allow_subnav)
                ):
                    if (
                        self.use_specific and (
                            hasattr(page, 'has_submenu_items') or
                            hasattr(page.specific_class, 'has_submenu_items')
                        )
                    ):
                        if type(page) is Page:
                            page = page.specific
                        """
                        If the page has a `has_submenu_items` method, give
                        responsibilty for determining `has_children_in_menu`
                        to that.
                        """
                        has_children_in_menu = page.has_submenu_items(
                            menu_instance=self,
                            request=self.request,
                            allow_repeating_parents=opts.allow_repeating_parents,
                            current_page=cvals.current_page,
                            original_menu_tag=cvals.original_menu_tag,
                        )

                    else:
                        has_children_in_menu = self.page_has_children(page)

                setattr(item, 'has_children_in_menu', has_children_in_menu)

                if opts.apply_active_classes:
                    active_class = ''
                    if(current_page and page.pk == current_page.pk):
                        # This is the current page, so the menu item should
                        # probably have the 'active' class
                        active_class = active_css_class
                        if (
                            opts.allow_repeating_parents and
                            self.use_specific and
                            has_children_in_menu
                        ):
                            if type(page) is Page:
                                page = page.specific
                            if getattr(page, 'repeat_in_subnav', False):
                                active_class = ancestor_css_class
                    elif page.pk in cvals.current_page_ancestor_ids:
                        active_class = ancestor_css_class
                    setattr(item, 'active_class', active_class)

            elif page is None:
                """
                This is a `MenuItem` for a custom URL. It can be classed as
                'active' if the URL matches the request path.
                """
                request_path = self.request.path
                if opts.apply_active_classes and item.link_url == request_path:
                    setattr(item, 'active_class', app_settings.ACTIVE_CLASS)

            # In case the specific page was fetched during the above operations
            # We'll set `MenuItem.link_page` to that specific page.
            if menuitem and page:
                menuitem.link_page = page

            if opts.use_absolute_page_urls:
                # Pages only have `get_full_url` from Wagtail 1.11 onwards
                if hasattr(item, 'get_full_url'):
                    url = item.get_full_url(request=self.request)
                # Fallback for Wagtail versions prior to 1.11
                else:
                    url = item.full_url
            else:
                # Both `Page` and `MenuItem` objects have a `relative_url`
                # method that we can use to calculate a value for the `href`
                # attribute
                url = item.relative_url(current_site)
            setattr(item, 'href', url)
            primed_menu_items.append(item)

        return primed_menu_items

    def get_template(self):
        e = self.contextual_vals.template_engine
        specified = self.option_vals.template_name
        if specified:
            return e.get_template(specified)
        if hasattr(self, 'template_name'):
            return e.get_template(self.template_name)
        return e.select_template(self.get_template_names())

    def get_template_names(self):
        """Return a list (or tuple) of template names to search for when
        rendering an instance of this class. The list should be ordered
        with most specific names first, since the first template found to
        exist will be used for rendering"""
        site = self.contextual_vals.current_site
        template_names = []
        menu_str = self.menu_short_name
        if app_settings.SITE_SPECIFIC_TEMPLATE_DIRS and site:
            hostname = site.hostname
            template_names.extend([
                "menus/%s/%s/menu.html" % (hostname, menu_str),
                "menus/%s/%s_menu.html" % (hostname, menu_str),
            ])
        template_names.append("menus/%s/menu.html" % menu_str)
        lstn = self.get_least_specific_template_name()
        if lstn:
            template_names.append(lstn)
        return template_names

    @classmethod
    def get_least_specific_template_name(cls):
        """Return a template name to be added to the end of the list returned
        by 'get_template_names'. This is defined as a separate method because
        template lists tend to follow a similar pattern, except the last
        item, which typically comes from a setting"""
        return

    def render_to_template(self, context_data, template):
        context_data['current_template'] = template.name
        return template.render(Context(context_data))


class MultiLevelMenu(Menu):

    def get_context_data(self, **kwargs):
        smt = self.get_sub_menu_template()
        data = {
            'sub_menu_template_instance': smt,
            'sub_menu_template': smt.name,
        }
        data.update(kwargs)
        return super(MultiLevelMenu, self).get_context_data(**data)

    def get_sub_menu_template(self):
        e = self.contextual_vals.template_engine
        specified = self.option_vals.sub_menu_template_name
        if specified:
            return e.get_template(specified)
        if hasattr(self, 'sub_menu_template'):
            return e.get_template(self.sub_menu_template)
        return e.select_template(self.get_sub_menu_template_names())

    def get_sub_menu_template_names(self):
        """Return a list of template paths/names to search when
        rendering a sub menu for an instance of this class. The list should be
        ordered with most specific names first, since the first template found
        to exist will be used for rendering"""
        current_site = self.contextual_vals.current_site
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


class MenuFromRootPage(MultiLevelMenu):
    """A 'menu' that is instantiated with a 'root page', and whose 'menu items'
    consist solely of ancestors of that page."""

    root_page = None
    root_page_context_name = 'root_page'

    def __init__(self, root_page, max_levels, use_specific):
        self.root_page = root_page
        self.max_levels = max_levels
        self.use_specific = use_specific
        super(MenuFromRootPage, self).__init__()

    def get_pages_for_display(self):
        """Return all pages needed for rendering all sub-levels for the current
        menu"""
        pages = self.get_base_page_queryset().filter(
            depth__gt=self.root_page.depth,
            depth__lte=self.root_page.depth + self.max_levels,
            path__startswith=self.root_page.path,
        )

        # Return 'specific' page instances if required
        if self.use_specific == app_settings.USE_SPECIFIC_ALWAYS:
            return pages.specific()

        return pages

    def get_children_for_page(self, page):
        """Return a list of relevant child pages for a given page."""
        if self.max_levels == 1:
            # If there's only a single level of pages to display, skip the
            # dict creation / lookup and just return the QuerySet result
            return self.pages_for_display
        return super(MenuFromRootPage, self).get_children_for_page(page)

    def get_raw_menu_items(self):
        return list(self.get_children_for_page(self.root_page))

    def get_context_data(self, **kwargs):
        if (
            self.root_page and self.use_specific and
            type(self.root_page) is not Page and
            hasattr(self.root_page, 'specific_class') and
            hasattr(self.root_page.specific_class, 'modify_submenu_items')
        ):
            self.root_page = self.root_page.specific
        data = {self.root_page_context_name: self.root_page}
        data.update(**kwargs)
        return super(MenuFromRootPage, self).get_context_data(**data)

    def modify_menu_items(self, menu_items):
        # If root_page has a `modify_submenu_items` method, send menu_items
        # list to that method for further modification
        root = self.root_page
        if not self.use_specific or not hasattr(root, 'modify_submenu_items'):
            return menu_items

        cvals = self.contextual_vals
        opts = self.option_vals
        kwargs = {
            'request': self.request,
            'menu_instance': self,
            'original_menu_tag': cvals.original_menu_tag,
            'current_site': cvals.current_site,
            'current_page': cvals.current_page,
            'current_ancestor_ids': cvals.current_page_ancestor_ids,
            'allow_repeating_parents': opts.allow_repeating_parents,
            'apply_active_classes': opts.apply_active_classes,
            'use_absolute_page_urls': opts.use_absolute_page_urls,
        }
        # Backwards compatibility for 'modify_submenu_items' methods that
        # don't accept a 'use_absolute_page_urls' kwarg
        if not accepts_kwarg(
            root.modify_submenu_items, 'use_absolute_page_urls'
        ):
            kwargs.pop('use_absolute_page_urls')
            warning_msg = (
                "The 'modify_submenu_items' method on '%s' should be "
                "updated to accept a 'use_absolute_page_urls' keyword "
                "argument. View the 2.4 release notes for more info: "
                "https://github.com/rkhleics/wagtailmenus/releases/tag/v.2.4.0"
                % root.__class__.__name__,
            )
            warnings.warn(warning_msg, RemovedInWagtailMenus26Warning)

        # Call `modify_submenu_items` using the above kwargs dict
        return root.modify_submenu_items(menu_items, **kwargs)


class SectionMenu(MenuFromRootPage):
    menu_type = 'section_menu'  # provided to hook methods
    menu_short_name = 'section'  # used to find templates
    root_page_context_name = 'parent_page'

    @classmethod
    def get_least_specific_template_name(cls):
        return app_settings.DEFAULT_SECTION_MENU_TEMPLATE

    def render(self, *args, **kwargs):
        self.render_init(*args, **kwargs)
        if not self.contextual_vals.current_section_root_page:
            return ''
        self.root_page = self.contextual_vals.current_section_root_page
        return self.render_to_template(
            self.get_context_data(),
            self.get_template(),
        )

    def get_context_data(self, **kwargs):
        section_root = self.root_page
        cvals = self.contextual_vals
        current_page = cvals.current_page
        active_css_class = app_settings.ACTIVE_CLASS
        ancestor_css_class = app_settings.ACTIVE_ANCESTOR_CLASS
        opts = self.option_vals
        data = super(SectionMenu, self).get_context_data()
        data['show_section_root'] = opts.extra['show_section_root']

        if 'section_root' not in kwargs and data['show_section_root']:
            section_root.text = getattr(
                section_root, app_settings.PAGE_FIELD_FOR_MENU_ITEM_TEXT,
                section_root.title
            )
            if opts.use_absolute_page_urls:
                if hasattr(section_root, 'get_full_url'):
                    url = section_root.get_full_url(request=self.request)
                else:
                    url = section_root.full_url
            else:
                url = section_root.relative_url(cvals.current_site)
            section_root.href = url

            if opts.apply_active_classes:
                active_class = ancestor_css_class
                if current_page and section_root.pk == current_page.pk:
                    # `section_root` is the current page, so should probably
                    # have the 'active' class
                    active_class = active_css_class
                    menu_items = data['menu_items']
                    # Unless there's a 'repeated item' in menu_items that
                    # already has the 'active' class
                    if(
                        opts.allow_repeating_parents and self.use_specific
                    ):
                        for item in menu_items:
                            css_class = getattr(item, 'active_class', '')
                            if(
                                css_class == active_css_class and
                                getattr(item, 'pk', 0) == section_root.pk
                            ):
                                active_class = ancestor_css_class
                section_root.active_class = active_class

        data['section_root'] = section_root
        data.update(**kwargs)
        return data


class SubMenu(MenuFromRootPage):
    menu_type = 'sub_menu'  # provided to hook methods
    menu_short_name = 'sub'  # used to find templates
    add_self_to_context = False

    def render(self, template, *args, **kwargs):
        self.template = template
        return super(SubMenu, self).render(*args, **kwargs)

    def get_template(self):
        return self.template


class ChildrenMenu(MenuFromRootPage):
    menu_type = 'children_menu'  # provided to hook methods
    menu_short_name = 'children'  # used to find templates

    @classmethod
    def get_least_specific_template_name(cls):
        return app_settings.DEFAULT_CHILDREN_MENU_TEMPLATE


class MenuWithMenuItems(ClusterableModel, MultiLevelMenu):
    """A base model class for menus who's 'menu_items' are defined by
    a set of 'menu item' model instances."""

    class Meta:
        abstract = True

    def get_base_menuitem_queryset(self):
        qs = self.get_menu_items_manager().for_display()
        # allow hooks to modify the queryset
        for hook in hooks.get_hooks('menus_modify_base_menuitem_queryset'):
            qs = hook(qs, **self.get_common_hook_kwargs())
        return qs

    @cached_property
    def top_level_items(self):
        """Return a list of menu items with link_page objects supplemented with
        'specific' pages where appropriate."""
        menu_items = self.get_base_menuitem_queryset()

        # Identify which pages to fetch for the top level items. We use
        # 'get_base_page_queryset' here, so that if that's being overridden
        # or modified by hooks, any pages being excluded there are also
        # excluded at the top level
        top_level_pages = self.get_base_page_queryset().filter(
            id__in=menu_items.values_list('link_page_id', flat=True)
        )
        if self.use_specific >= app_settings.USE_SPECIFIC_TOP_LEVEL:
            """
            The menu is being generated with a specificity level of TOP_LEVEL
            or ALWAYS, so we use PageQuerySet.specific() to fetch specific
            page instances as efficiently as possible
            """
            top_level_pages = top_level_pages.specific()

        # Evaluate the above queryset to a dictionary, using the IDs as keys
        pages_dict = {p.id: p for p in top_level_pages}

        # Now build a list to return
        menu_item_list = []
        for item in menu_items:
            if not item.link_page_id:
                menu_item_list.append(item)
                continue  # skip to next
            if item.link_page_id in pages_dict.keys():
                # Only return menu items for pages where the page was included
                # in the 'get_base_page_queryset' result
                item.link_page = pages_dict.get(item.link_page_id)
                menu_item_list.append(item)
        return menu_item_list

    def get_pages_for_display(self):
        """Return all pages needed for rendering all sub-levels for the current
        menu"""

        # Start with an empty queryset, and expand as needed
        all_pages = Page.objects.none()

        if self.max_levels == 1:
            # If no additional sub-levels are needed, return empty queryset
            return all_pages

        for item in self.top_level_items:

            if item.link_page_id:
                # Fetch a 'branch' of suitable descendants for this item and
                # add to 'all_pages'
                page_depth = item.link_page.depth
                if(
                    item.allow_subnav and
                    page_depth >= app_settings.SECTION_ROOT_DEPTH
                ):
                    all_pages = all_pages | Page.objects.filter(
                        depth__gt=page_depth,
                        depth__lt=page_depth + self.max_levels,
                        path__startswith=item.link_page.path)

        # Filter the entire queryset to include only pages suitable for display
        all_pages = all_pages & self.get_base_page_queryset()

        # Return 'specific' page instances if required
        if self.use_specific == app_settings.USE_SPECIFIC_ALWAYS:
            return all_pages.specific()

        return all_pages

    def get_menu_items_manager(self):
        raise NotImplementedError(
            "Subclasses of 'MenuWithMenuItems' must define their own "
            "'get_menu_items_manager' method")

    def add_menu_items_for_pages(self, pagequeryset=None, allow_subnav=True):
        """Add menu items to this menu, linking to each page in `pagequeryset`
        (which should be a PageQuerySet instance)"""
        item_manager = self.get_menu_items_manager()
        item_class = item_manager.model
        item_list = []
        i = item_manager.count()
        for p in pagequeryset.all():
            item_list.append(item_class(
                menu=self, link_page=p, sort_order=i, allow_subnav=allow_subnav
            ))
            i += 1
        item_manager.bulk_create(item_list)

    def get_raw_menu_items(self):
        return list(self.top_level_items)

    def render_init(self, *args, **options):
        super(MenuWithMenuItems, self).render_init(*args, **options)
        self.set_max_levels(options['max_levels'])
        self.set_max_levels(options['use_specific'])


# ########################################################
# Abstract models
# ########################################################

@python_2_unicode_compatible
class AbstractMainMenu(MenuWithMenuItems):
    menu_type = 'main_menu'  # provided to hook methods
    menu_short_name = 'main'  # used to find templates

    site = models.OneToOneField(
        'wagtailcore.Site',
        verbose_name=_('site'),
        db_index=True,
        editable=False,
        on_delete=models.CASCADE,
        related_name="+",
    )
    max_levels = models.PositiveSmallIntegerField(
        verbose_name=_('maximum levels'),
        choices=app_settings.MAX_LEVELS_CHOICES,
        default=2,
        help_text=mark_safe(_(
            "The maximum number of levels to display when rendering this "
            "menu. The value can be overidden by supplying a different "
            "<code>max_levels</code> value to the <code>{% main_menu %}"
            "</code> tag in your templates."
        ))
    )
    use_specific = models.PositiveSmallIntegerField(
        verbose_name=_('specific page usage'),
        choices=app_settings.USE_SPECIFIC_CHOICES,
        default=app_settings.USE_SPECIFIC_AUTO,
        help_text=mark_safe(_(
            "Controls how 'specific' pages objects are fetched and used when "
            "rendering this menu. This value can be overidden by supplying a "
            "different <code>use_specific</code> value to the <code>"
            "{% main_menu %}</code> tag in your templates."
        ))
    )

    class Meta:
        abstract = True
        verbose_name = _("main menu")
        verbose_name_plural = _("main menu")

    @classmethod
    def get_for_site(cls, site):
        """Return the 'main menu' instance for the provided site"""
        instance, created = cls.objects.get_or_create(site=site)
        return instance

    @classmethod
    def get_least_specific_template_name(cls):
        return app_settings.DEFAULT_MAIN_MENU_TEMPLATE

    def __str__(self):
        return _('Main menu for %(site_name)s') % {
            'site_name': self.site.site_name or self.site
        }

    def get_menu_items_manager(self):
        try:
            return getattr(self, app_settings.MAIN_MENU_ITEMS_RELATED_NAME)
        except AttributeError:
            raise ImproperlyConfigured(
                "'%s' isn't a valid relationship name for accessing menu "
                "items from %s. Check that your "
                "`WAGTAILMENUS_MAIN_MENU_ITEMS_RELATED_NAME` setting matches "
                "the `related_name` used on your MenuItem model's "
                "`ParentalKey` field." % (
                    app_settings.MAIN_MENU_ITEMS_RELATED_NAME,
                    self.__class__.__name__
                )
            )

    panels = (
        InlinePanel(
            app_settings.MAIN_MENU_ITEMS_RELATED_NAME, label=_("menu items")
        ),
        MultiFieldPanel(
            heading=_("Advanced settings"),
            children=(FieldPanel('max_levels'), FieldPanel('use_specific')),
            classname="collapsible collapsed",
        ),
    )


@python_2_unicode_compatible
class AbstractFlatMenu(MenuWithMenuItems):
    menu_type = 'flat_menu'  # provided to hook methods
    menu_short_name = 'flat'  # used to find templates

    site = models.ForeignKey(
        'wagtailcore.Site',
        verbose_name=_('site'),
        db_index=True,
        on_delete=models.CASCADE,
        related_name='+'
    )
    title = models.CharField(
        verbose_name=_('title'),
        max_length=255,
        help_text=_("For internal reference only.")
    )
    handle = models.SlugField(
        verbose_name=_('handle'),
        max_length=100,
        help_text=_(
            "Used to reference this menu in templates etc. Must be unique "
            "for the selected site."
        )
    )
    heading = models.CharField(
        verbose_name=_('heading'),
        max_length=255,
        blank=True,
        help_text=_("If supplied, appears above the menu when rendered.")
    )
    max_levels = models.PositiveSmallIntegerField(
        verbose_name=_('maximum levels'),
        choices=app_settings.MAX_LEVELS_CHOICES,
        default=1,
        help_text=mark_safe(_(
            "The maximum number of levels to display when rendering this "
            "menu. The value can be overidden by supplying a different "
            "<code>max_levels</code> value to the <code>{% flat_menu %}"
            "</code> tag in your templates."
        ))
    )
    use_specific = models.PositiveSmallIntegerField(
        verbose_name=_('specific page usage'),
        choices=app_settings.USE_SPECIFIC_CHOICES,
        default=app_settings.USE_SPECIFIC_AUTO,
        help_text=mark_safe(_(
            "Controls how 'specific' pages objects are fetched and used when "
            "rendering this menu. This value can be overidden by supplying a "
            "different <code>use_specific</code> value to the <code>"
            "{% flat_menu %}</code> tag in your templates."
        ))
    )

    base_form_class = FlatMenuAdminForm

    class Meta:
        abstract = True
        unique_together = ("site", "handle")
        verbose_name = _("flat menu")
        verbose_name_plural = _("flat menus")

    @classmethod
    def get_for_site(cls, handle, site, fall_back_to_default_site_menus=False):
        """Get a FlatMenu instance with a matching `handle` for the `site`
        provided - or for the 'default' site if not found."""
        menu = cls.objects.filter(handle__exact=handle, site=site).first()
        if(
            menu is None and fall_back_to_default_site_menus and
            not site.is_default_site
        ):
            return cls.objects.filter(
                handle__exact=handle, site__is_default_site=True
            ).first()
        return menu

    @classmethod
    def get_least_specific_template_name(cls):
        return app_settings.DEFAULT_FLAT_MENU_TEMPLATE

    def __str__(self):
        return '%s (%s)' % (self.title, self.handle)

    def clean(self, *args, **kwargs):
        """Raise validation error for unique_together constraint, as it's not
        currently handled properly by wagtail."""

        clashes = self.__class__.objects.filter(site=self.site,
                                                handle=self.handle)
        if self.pk:
            clashes = clashes.exclude(pk__exact=self.pk)
        if clashes.exists():
            msg = _("Site and handle must create a unique combination. A menu "
                    "already exists with these same two values.")
            raise ValidationError({
                'site': [msg],
                'handle': [msg],
            })
        super(AbstractFlatMenu, self).clean(*args, **kwargs)

    def get_menu_items_manager(self):
        try:
            return getattr(self, app_settings.FLAT_MENU_ITEMS_RELATED_NAME)
        except AttributeError:
            raise ImproperlyConfigured(
                "'%s' isn't a valid relationship name for accessing menu "
                "items from %s. Check that your "
                "`WAGTAILMENUS_FLAT_MENU_ITEMS_RELATED_NAME` setting matches "
                "the `related_name` used on your MenuItem model's "
                "`ParentalKey` field." % (
                    app_settings.FLAT_MENU_ITEMS_RELATED_NAME,
                    self.__class__.__name__
                )
            )

    def get_context_data(self, **kwargs):
        data = {
            'show_menu_heading': self.option_vals.extra['show_menu_heading'],
        }
        data.update(kwargs)
        return super(AbstractFlatMenu, self).get_context_data(**data)

    def get_template_names(self):
        """Returns a list of template names to search for when rendering a
        a specific flat menu object (making use of self.handle)"""
        site = self.contextual_vals.current_site
        template_names = []
        if app_settings.SITE_SPECIFIC_TEMPLATE_DIRS and site:
            hn = site.hostname
            template_names.extend([
                "menus/%s/flat/%s/menu.html" % (hn, self.handle),
                "menus/%s/flat/%s.html" % (hn, self.handle),
                "menus/%s/%s/menu.html" % (hn, self.handle),
                "menus/%s/%s.html" % (hn, self.handle),
                "menus/%s/flat/menu.html" % hn,
                "menus/%s/flat/default.html" % hn,
                "menus/%s/flat_menu.html" % hn,
            ])
        template_names.extend([
            "menus/flat/%s/menu.html" % self.handle,
            "menus/flat/%s.html" % self.handle,
            "menus/%s/menu.html" % self.handle,
            "menus/%s.html" % self.handle,
            "menus/flat/default.html",
            "menus/flat/menu.html",
        ])
        lstn = self.get_least_specific_template_name()
        if lstn:
            template_names.append(lstn)
        return template_names

    def get_sub_menu_template_names(self):
        """Returns a list of template names to search for when rendering a
        a sub menu for a specific flat menu object (making use of self.handle)
        """
        site = self.contextual_vals.current_site
        template_names = []
        if app_settings.SITE_SPECIFIC_TEMPLATE_DIRS and site:
            hn = site.hostname
            template_names.extend([
                "menus/%s/flat/%s/sub_menu.html" % (hn, self.handle),
                "menus/%s/flat/%s_sub_menu.html" % (hn, self.handle),
                "menus/%s/%s/sub_menu.html" % (hn, self.handle),
                "menus/%s/%s_sub_menu.html" % (hn, self.handle),
                "menus/%s/flat/sub_menu.html" % hn,
                "menus/%s/sub_menu.html" % hn,
            ])
        template_names.extend([
            "menus/flat/%s/sub_menu.html" % self.handle,
            "menus/flat/%s_sub_menu.html" % self.handle,
            "menus/%s/sub_menu.html" % self.handle,
            "menus/%s_sub_menu.html" % self.handle,
            "menus/flat/sub_menu.html",
            app_settings.DEFAULT_SUB_MENU_TEMPLATE,
        ])
        return template_names

    panels = (
        MultiFieldPanel(
            heading=_("Settings"),
            children=(
                FieldPanel('title'),
                FieldPanel('site'),
                FieldPanel('handle'),
                FieldPanel('heading'),
            )
        ),
        InlinePanel(
            app_settings.FLAT_MENU_ITEMS_RELATED_NAME, label=_("menu items")
        ),
        MultiFieldPanel(
            heading=_("Advanced settings"),
            children=(FieldPanel('max_levels'), FieldPanel('use_specific')),
            classname="collapsible collapsed",
        ),
    )


# ########################################################
# Concrete models
# ########################################################

class MainMenu(AbstractMainMenu):
    """The default model for 'main menu' instances."""
    pass


class FlatMenu(AbstractFlatMenu):
    """The default model for 'flat menu' instances."""
    pass
