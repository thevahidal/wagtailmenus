from __future__ import unicode_literals
import warnings

from django.template import Library
from wagtail.wagtailcore import hooks
from wagtail.wagtailcore.models import Page

from wagtailmenus import app_settings
from ..models import AbstractLinkPage, MenuItem, SubMenu
from ..utils.deprecation import (
    RemovedInWagtailMenus26Warning, RemovedInWagtailMenus27Warning)
from ..utils.misc import get_site_from_request, validate_supplied_values
from wagtailmenus.utils.inspection import accepts_kwarg
flat_menus_fbtdsm = app_settings.FLAT_MENUS_FALL_BACK_TO_DEFAULT_SITE_MENUS

register = Library()


@register.simple_tag(takes_context=True)
def main_menu(
    context, max_levels=None, use_specific=None, apply_active_classes=True,
    allow_repeating_parents=True, show_multiple_levels=True,
    template='', sub_menu_template='', use_absolute_page_urls=False,
):
    validate_supplied_values('main_menu', max_levels=max_levels,
                             use_specific=use_specific)

    # Find a matching menu
    site = get_site_from_request(context['request'])
    menu = app_settings.MAIN_MENU_MODEL_CLASS.get_for_site(site)

    if not show_multiple_levels:
        max_levels = 1

    return menu.render(
        'main_menu', context,
        max_levels=max_levels,
        use_specific=use_specific,
        apply_active_classes=apply_active_classes,
        allow_repeating_parents=allow_repeating_parents,
        use_absolute_page_urls=use_absolute_page_urls,
        template_name=template,
        sub_menu_template_name=sub_menu_template,
    )


@register.simple_tag(takes_context=True)
def flat_menu(
    context, handle, max_levels=None, use_specific=None,
    show_menu_heading=False, apply_active_classes=False,
    allow_repeating_parents=True, show_multiple_levels=True,
    template='', sub_menu_template='',
    fall_back_to_default_site_menus=flat_menus_fbtdsm,
    use_absolute_page_urls=False,
):
    validate_supplied_values('flat_menu', max_levels=max_levels,
                             use_specific=use_specific)

    # Find a matching menu
    site = get_site_from_request(context['request'])
    menu = app_settings.FLAT_MENU_MODEL_CLASS.get_for_site(
        handle, site, fall_back_to_default_site_menus
    )

    if not menu:
        # No menu was found matching `handle`, so gracefully render nothing.
        return ''

    if not show_multiple_levels:
        max_levels = 1

    return menu.render(
        'flat_menu', context,
        max_levels=max_levels,
        use_specific=use_specific,
        apply_active_classes=apply_active_classes,
        allow_repeating_parents=allow_repeating_parents,
        use_absolute_page_urls=use_absolute_page_urls,
        template_name=template,
        sub_menu_template_name=sub_menu_template,
        show_menu_heading=show_menu_heading,
    )


@register.simple_tag(takes_context=True)
def section_menu(
    context, show_section_root=True, show_multiple_levels=True,
    apply_active_classes=True, allow_repeating_parents=True,
    max_levels=app_settings.DEFAULT_SECTION_MENU_MAX_LEVELS,
    template='', sub_menu_template='',
    use_specific=app_settings.DEFAULT_SECTION_MENU_USE_SPECIFIC,
    use_absolute_page_urls=False,
):
    """Render a section menu for the current section."""

    validate_supplied_values('section_menu', max_levels=max_levels,
                             use_specific=use_specific)

    if not show_multiple_levels:
        max_levels = 1

    menu = app_settings.SECTION_MENU_CLASS(None, max_levels, use_specific)

    return menu.render(
        'section_menu', context,
        max_levels=max_levels,
        use_specific=use_specific,
        apply_active_classes=apply_active_classes,
        allow_repeating_parents=allow_repeating_parents,
        use_absolute_page_urls=use_absolute_page_urls,
        template_name=template,
        sub_menu_template_name=sub_menu_template,
        show_section_root=show_section_root,
    )


@register.simple_tag(takes_context=True)
def children_menu(
    context, parent_page=None, allow_repeating_parents=True,
    apply_active_classes=False,
    max_levels=app_settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS,
    template='', sub_menu_template='',
    use_specific=app_settings.DEFAULT_CHILDREN_MENU_USE_SPECIFIC,
    use_absolute_page_urls=False,
):
    validate_supplied_values(
        'children_menu', max_levels=max_levels, use_specific=use_specific,
        parent_page=parent_page)

    # Use current page as parent_page if no value supplied
    if parent_page is None:
        parent_page = context.get('self')
    if not parent_page:
        return ''

    # Create a menu instance that can fetch all pages at once and return
    # for subpages for each branch as they are needed
    menu = app_settings.CHILDREN_MENU_CLASS(parent_page, max_levels,
                                            use_specific)

    return menu.render(
        'children_menu', context,
        max_levels=max_levels,
        use_specific=use_specific,
        apply_active_classes=apply_active_classes,
        allow_repeating_parents=allow_repeating_parents,
        use_absolute_page_urls=use_absolute_page_urls,
        template_name=template,
        sub_menu_template_name=sub_menu_template,
    )


@register.simple_tag(takes_context=True)
def sub_menu(
    context, menuitem_or_page, stop_at_this_level=None, use_specific=None,
    allow_repeating_parents=None, apply_active_classes=None, template='',
    use_absolute_page_urls=None,
):
    """
    Retrieve the children pages for the `menuitem_or_page` provided, turn them
    into menu items, and render them to a template.
    """
    validate_supplied_values('sub_menu', use_specific=use_specific,
                             menuitem_or_page=menuitem_or_page)

    if stop_at_this_level is not None:
        warning_msg = (
            "The 'stop_at_this_level' argument for 'sub_menu' no longer "
            "has any effect on output and is deprecated. View the 2.5 release "
            "notes for more info: "
            "http://wagtailmenus.readthedocs.io/en/stable/releases/2.5.0.html"
        )
        warnings.warn(warning_msg, RemovedInWagtailMenus27Warning)

    max_levels = context.get(
        'max_levels', app_settings.DEFAULT_CHILDREN_MENU_MAX_LEVELS
    )

    if use_specific is None:
        use_specific = context.get(
            'use_specific', app_settings.USE_SPECIFIC_AUTO)

    if apply_active_classes is None:
        apply_active_classes = context.get('apply_active_classes', True)

    if allow_repeating_parents is None:
        allow_repeating_parents = context.get('allow_repeating_parents', True)

    if use_absolute_page_urls is None:
        use_absolute_page_urls = context.get('use_absolute_page_urls', False)

    if template:
        template = context.template.engine.get_template(template)
    else:
        template = context.get('sub_menu_template_instance')

    if isinstance(menuitem_or_page, Page):
        parent_page = menuitem_or_page
    else:
        parent_page = menuitem_or_page.link_page

    menu_class = context.get('sub_menu_class') or SubMenu
    menu = menu_class(parent_page, max_levels, use_specific)
    return menu.render(
        context.get('menu_instance'), template, 'sub_menu', context,
        max_levels=max_levels,
        use_specific=use_specific,
        apply_active_classes=apply_active_classes,
        allow_repeating_parents=allow_repeating_parents,
        use_absolute_page_urls=use_absolute_page_urls,
    )


def get_sub_menu_items_for_page(
    page, request, original_menu_tag, menu_instance, current_level, max_levels,
    current_site, current_page, current_ancestor_ids, use_specific,
    allow_repeating_parents=True, apply_active_classes=True,
    use_absolute_page_urls=False
):
    warning_msg = (
        "The 'get_sub_menu_items_for_page' method in menu_tags is deprecated "
        "in favour of rendering behaviour being implemented into menu "
        "classes. Read the 2.5 release notes for more info: "
        "http://wagtailmenus.readthedocs.io/en/stable/releases/2.5.0.html"
    )
    warnings.warn(warning_msg, RemovedInWagtailMenus27Warning)

    # The menu items will be the children of the provided `page`
    children_pages = menu_instance.get_children_for_page(page)

    # If we're going to fetch a specific instance, do it now so that the
    # specific page can be passed elsewhere
    if (
        use_specific and (
            hasattr(page, 'modify_submenu_items') or
            hasattr(page.specific_class, 'modify_submenu_items')
        )
    ):
        if type(page) is Page:
            page = page.specific

    # Define common kwargs for calls to 'prime_menu_items', methods using the
    # 'menus_modify_menu_items' hook, or page's 'modify_sub_menu_items' method
    kwargs = {
        'request': request,
        'original_menu_tag': original_menu_tag,
        'menu_instance': menu_instance,
        'current_site': current_site,
        'current_page': current_page,
        'current_ancestor_ids': current_ancestor_ids,
        'allow_repeating_parents': allow_repeating_parents,
        'apply_active_classes': apply_active_classes,
        'use_absolute_page_urls': use_absolute_page_urls,
    }
    # additional kwargs, not needed for 'modify_sub_menu_items'
    kwargs_extra = {
        'parent_page': page,
        'current_level': current_level,
        'max_levels': max_levels,
        'use_specific': use_specific,
    }
    kwargs_extra.update(kwargs)

    # allow hooks to modify menu items before priming
    menu_items = list(children_pages)
    for hook in hooks.get_hooks('menus_modify_raw_menu_items'):
        menu_items = hook(menu_items, **kwargs_extra)

    # prime the menu items
    menu_items = prime_menu_items(menu_items, **kwargs_extra)

    # If `page` has a `modify_submenu_items` method, send the primed
    # menu_items list to that for further modification
    if use_specific and hasattr(page, 'modify_submenu_items'):

        # Backwards compatibility for 'modify_submenu_items' methods that
        # don't accept a 'use_absolute_page_urls' kwarg
        if not accepts_kwarg(
            page.modify_submenu_items, 'use_absolute_page_urls'
        ):
            kwargs.pop('use_absolute_page_urls')
            warning_msg = (
                "The 'modify_submenu_items' method on '%s' should be "
                "updated to accept a 'use_absolute_page_urls' keyword "
                "argument. View the 2.4 release notes for more info: "
                "https://github.com/rkhleics/wagtailmenus/releases/tag/v.2.4.0"
                % page.__class__.__name__,
            )
            warnings.warn(warning_msg, RemovedInWagtailMenus26Warning)

        # Call `modify_submenu_items` using the above kwargs dict
        menu_items = page.modify_submenu_items(menu_items, **kwargs)

    # allow hooks to modify the final menu items list
    for hook in hooks.get_hooks('menus_modify_primed_menu_items'):
        menu_items = hook(menu_items, **kwargs_extra)

    return page, menu_items


def prime_menu_items(
    menu_items, request, parent_page, original_menu_tag, current_level,
    max_levels, menu_instance, current_site, current_page,
    current_ancestor_ids, use_specific, allow_repeating_parents=True,
    apply_active_classes=True, use_absolute_page_urls=False,
):
    """
    Prepare a list of `MenuItem` or `Page` objects for rendering to a menu
    template.
    """
    warning_msg = (
        "The 'prime_menu_items' method in menu_tags is deprecated in favour "
        "of rendering behaviour being implemented into menu classes. Read the "
        "2.5 release notes for more info: "
        "http://wagtailmenus.readthedocs.io/en/stable/releases/2.5.0.html"
    )
    warnings.warn(warning_msg, RemovedInWagtailMenus27Warning)

    stop_at_this_level = (current_level >= max_levels)
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
                request, current_site, menu_instance, original_menu_tag
            ):
                setattr(item, 'active_class', item.extra_classes)
                setattr(item, 'text', item.menu_text(request))
                if use_absolute_page_urls:
                    url = item.get_full_url(request=request)
                else:
                    url = item.relative_url(current_site, request)
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
                page, app_settings.PAGE_FIELD_FOR_MENU_ITEM_TEXT, page.title
            )
            setattr(item, 'text', text)

        if page:
            """
            Work out whether this item should be flagged as needing
            a sub-menu. It can be expensive, so we try to only do the working
            out when absolutely necessary.
            """
            has_children_in_menu = False
            if (
                not stop_at_this_level and
                page.depth >= app_settings.SECTION_ROOT_DEPTH and
                (menuitem is None or menuitem.allow_subnav)
            ):
                if (
                    use_specific and (
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

                    # Create dict of kwargs to send to `has_submenu_items`
                    method_kwargs = {
                        'current_page': current_page,
                        'allow_repeating_parents': allow_repeating_parents,
                        'original_menu_tag': original_menu_tag,
                        'menu_instance': menu_instance,
                        'request': request,
                    }
                    # Call `has_submenu_items` using the above kwargs dict
                    has_children_in_menu = page.has_submenu_items(
                        **method_kwargs)

                else:
                    has_children_in_menu = menu_instance.page_has_children(
                        page)

            setattr(item, 'has_children_in_menu', has_children_in_menu)

            if apply_active_classes:
                active_class = ''
                if(current_page and page.pk == current_page.pk):
                    # This is the current page, so the menu item should
                    # probably have the 'active' class
                    active_class = app_settings.ACTIVE_CLASS
                    if (
                        allow_repeating_parents and use_specific and
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
            request_path = getattr(request, 'path', '')
            if apply_active_classes and item.link_url == request_path:
                setattr(item, 'active_class', app_settings.ACTIVE_CLASS)

        # In case the specific page was fetched during the above operations
        # We'll set `MenuItem.link_page` to that specific page.
        if menuitem and page:
            menuitem.link_page = page

        if use_absolute_page_urls:
            # Pages only have `get_full_url` from Wagtail 1.11 onwards
            if hasattr(item, 'get_full_url'):
                url = item.get_full_url(request=request)
            # Fallback for Wagtail versions prior to 1.11
            else:
                url = item.full_url
        else:
            # Both `Page` and `MenuItem` objects have a `relative_url` method
            # that we can use to calculate a value for the `href` attribute.
            url = item.relative_url(current_site)
        setattr(item, 'href', url)
        primed_menu_items.append(item)

    return primed_menu_items
