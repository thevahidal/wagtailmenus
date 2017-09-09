from __future__ import absolute_import, unicode_literals

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
from ..utils.misc import get_site_from_request


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

    @property
    def pages_for_display(self):
        raise NotImplementedError(
            "Subclasses of 'Menu' must define their own 'pages_for_display' "
            "method")

    @cached_property
    def page_children_dict(self):
        """Returns a dictionary of lists, where the keys are 'path' values for
        pages, and the value is a list of children pages for that page."""
        children_dict = defaultdict(list)
        for page in self.pages_for_display:
            children_dict[page.path[:-page.steplen]].append(page)
        return children_dict

    def get_children_for_page(self, page):
        """Return a list of relevant child pages for a given page."""
        return self.page_children_dict.get(page.path, [])

    def page_has_children(self, page):
        """Return a boolean indicating whether a given page has any relevant
        child pages."""
        return page.path in self.page_children_dict

    def render(self, context, menu_tag, **kwargs):
        self.pre_render_operations(context, menu_tag, **kwargs)
        return self.render_to_template(
            self.get_context_data(), self.get_template()
        )

    def pre_render_operations(self, context, menu_tag, **kwargs):
        self._parent_context = context
        self.set_contextual_vals(context, menu_tag)
        self.set_render_option_vals(kwargs)
        self.set_request(context['request'])
        if 'max_levels' in kwargs:
            self.set_max_levels(kwargs['max_levels'])
        if 'use_specific' in kwargs:
            self.set_use_specific(kwargs['use_specific'])

    def set_contextual_vals(self, context, menu_tag, **extra):
        ContextualVals = namedtuple('ContextualVals', (
            'current_level', 'current_site', 'original_menu_tag',
            'current_page', 'current_section_root_page',
            'current_page_ancestor_ids', 'template_engine', 'extra'
        ))
        current_site = get_site_from_request(context['request'])
        context_processor_vals = context.get('wagtailmenus_vals', {})
        self.contextual_vals = ContextualVals(
            self.get_current_level(),
            current_site,
            menu_tag,
            context_processor_vals.get('current_page'),
            context_processor_vals.get('section_root'),
            context_processor_vals.get('current_page_ancestor_ids', ()),
            context.template.engine,
            extra
        )

    def get_current_level(self):
        return 1

    def set_render_option_vals(self, option_vals):
        RenderOptionVals = namedtuple('RenderOptionVals', (
            'max_levels', 'use_specific', 'apply_active_classes',
            'allow_repeating_parents', 'use_absolute_page_urls',
            'template_name', 'sub_menu_template_name', 'extra'
        ))
        self.render_option_vals = RenderOptionVals(
            option_vals.pop('max_levels'),
            option_vals.pop('use_specific'),
            option_vals.pop('apply_active_classes'),
            option_vals.pop('allow_repeating_parents'),
            option_vals.pop('use_absolute_page_urls'),
            option_vals.pop('template_name'),
            option_vals.pop('sub_menu_template_name'),
            option_vals
        )

    def get_context_data(self, **kwargs):
        data = self._parent_context.flatten()
        data.update(self.contextual_vals._as_dict())
        data.update(self.render_option_vals._asdict())
        data.update({
            'menu_instance': self,
            'menu_items': self.get_primed_menu_items(),
            'section_root': data['current_section_root_page'],
            'current_ancestor_ids': data['current_page_ancestor_ids'],
        })
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
        kwargs = self.contextual_vals._asdict()
        kwargs.update(self.render_option_vals._as_dict())
        kwargs.update({
            'parent_page': None,
            'menu_instance': self,
        })
        kwargs.pop('template_name')
        kwargs.pop('sub_menu_template')
        kwargs.pop('template_engine')
        kwargs.pop('extra')
        return kwargs

    def get_raw_menu_items(self):
        raise NotImplementedError("Subclasses of 'Menu' must define their own "
                                  "'get_raw_menu_items' method")

    def modify_menu_items(self):
        raise NotImplementedError("Subclasses of 'Menu' must define their own "
                                  "'modify_menu_items' method")

    def prime_menu_items(self, menu_items):
        """
        Prepare a list of `MenuItem` or `Page` objects for rendering to a menu
        template.
        """
        from .menuitems import MenuItem
        from .pages import AbstractLinkPage
        current_site = self.contextual_vals.current_site
        current_page = self.contextual_vals.current_page
        current_ancestor_ids = self.contextual_vals.current_page_ancestor_ids
        original_menu_tag = self.contextual_vals.original_menu_tag
        apply_active_classes = self.render_option_vals.apply_active_classes
        allow_repeating_parents = self.render_option_vals.allow_repeating_parents
        use_absolute_page_urls = self.render_option_vals.use_absolute_page_urls
        stop_at_this_level = (self.get_current_level() >= self.max_levels)
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
                    self.contextual_data.original_menu_tag
                ):
                    setattr(item, 'active_class', item.extra_classes)
                    setattr(item, 'text', item.menu_text(self.request))
                    if self.render_option_vals.use_absolute_page_urls:
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
                            current_page=current_page,
                            allow_repeating_parents=allow_repeating_parents,
                            original_menu_tag=original_menu_tag,
                            menu_instance=self,
                            request=self.request,
                        )

                    else:
                        has_children_in_menu = self.page_has_children(page)

                setattr(item, 'has_children_in_menu', has_children_in_menu)

                if apply_active_classes:
                    active_class = ''
                    if(current_page and page.pk == current_page.pk):
                        # This is the current page, so the menu item should
                        # probably have the 'active' class
                        active_class = app_settings.ACTIVE_CLASS
                        if (
                            allow_repeating_parents and self.use_specific and
                            has_children_in_menu
                        ):
                            if type(page) is Page:
                                page = page.specific
                            if getattr(page, 'repeat_in_subnav', False):
                                active_class = app_settings.ACTIVE_ANCESTOR_CLASS
                    elif page.pk in current_ancestor_ids:
                        active_class = app_settings.ACTIVE_ANCESTOR_CLASS
                    setattr(item, 'active_class', active_class)

            elif page is None:
                """
                This is a `MenuItem` for a custom URL. It can be classed as
                'active' if the URL matches the request path.
                """
                request_path = self.request.path
                if apply_active_classes and item.link_url == request_path:
                    setattr(item, 'active_class', app_settings.ACTIVE_CLASS)

            # In case the specific page was fetched during the above operations
            # We'll set `MenuItem.link_page` to that specific page.
            if menuitem and page:
                menuitem.link_page = page

            if use_absolute_page_urls:
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
        specified = self.render_option_vals.template_name
        if specified:
            return e.get_template(specified)
        return e.select_template(self.get_template_names())

    def get_template_names(self):
        """Return a list (or tuple) of template names to search for when
        rendering an instance of this class. The list should be ordered
        with most specific names first, since the first template found to
        exist will be used for rendering"""
        raise NotImplementedError(
            "Subclasses of 'Menu' must define their own 'get_template_names' "
            "implementation")

    @classmethod
    def get_least_specific_template_name(cls):
        """Return a template name to be added to the end of the list returned
        by 'get_template_names'. This is defined as a separate method because
        template lists tend to follow a similar pattern, except the last
        item, which typically comes from a setting"""
        raise NotImplementedError(
            "Subclasses of 'Menu' must define their own "
            "'get_least_specific_template_name' implementation")

    def render_to_template(self, data, template):
        data['current_template'] = template.name
        return template.render(Context(data))


class MultiLevelMenu(Menu):

    def get_template_names(self):
        site = self.contextual_vals.current_site
        template_names = []
        menu_str = self.menu_short_name
        if app_settings.SITE_SPECIFIC_TEMPLATE_DIRS and site:
            hostname = site.hostname
            template_names.extend([
                "menus/%s/%s/menu.html" % (hostname, menu_str),
                "menus/%s/%s_menu.html" % (hostname, menu_str),
            ])
        template_names.extend([
            "menus/%s/menu.html" % menu_str,
            self.get_least_specific_template_name(),
        ])
        return template_names

    def get_sub_menu_template(self):
        e = self.contextual_vals.template_engine
        specified = self.render_option_vals.sub_menu_template_name
        if specified:
            return e.get_template(specified)
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

    @cached_property
    def pages_for_display(self):
        return self.get_pages_for_display()

    def get_children_for_page(self, page):
        """Return a list of relevant child pages for a given page."""
        if self.max_levels == 1:
            # If there's only a single level of pages to display, skip the
            # dict creation / lookup and just return the QuerySet result
            return self.pages_for_display
        return super(MenuFromRootPage, self).get_children_for_page(page)


class SectionMenu(MenuFromRootPage):
    menu_type = 'section_menu'  # provided to hook methods
    menu_short_name = 'section'  # used to find templates

    def get_raw_menu_items(self):
        return self.get_children_for_page(
            self.contextual_vals.current_section_root_page)

    @classmethod
    def get_least_specific_template_name(cls):
        return app_settings.DEFAULT_SECTION_MENU_TEMPLATE


class ChildrenMenu(MenuFromRootPage):
    menu_type = 'children_menu'  # provided to hook methods
    menu_short_name = 'children'  # used to find templates

    def render(self, context, menu_tag, **kwargs):
        self.parent_page = kwargs.pop('parent_page')
        return super(ChildrenMenu, self).render(context, menu_tag, **kwargs)

    def get_raw_menu_items(self):
        return self.get_children_for_page(self.parent_page)

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

    @cached_property
    def pages_for_display(self):
        return self.get_pages_for_display()

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
        return self.top_level_items


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

    def get_template(self, context, template_name='', site=None):
        e = context.template.engine
        if template_name:
            return e.get_template(template_name)
        return e.select_template(self.get_template_names(site))

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
            self.get_fallback_template_name(),
        ])
        return template_names

    def get_sub_menu_template_names(self, site=None):
        """Returns a list of template names to search for when rendering a
        a sub menu for a specific flat menu object (making use of self.handle)
        """
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
