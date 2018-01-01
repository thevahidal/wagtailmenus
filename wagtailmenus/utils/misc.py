from io import StringIO
from urllib.parse import urlparse

from django.conf import settings
from django.core.handlers.base import BaseHandler
from django.core.handlers.wsgi import WSGIRequest
from wagtail.core.models import Page, Site

from wagtailmenus.models.menuitems import MenuItem


def get_site_from_request(request, fallback_to_default=True):
    if getattr(request, 'site', None):
        return request.site
    if fallback_to_default:
        return Site.objects.filter(is_default_site=True).first()
    return None


def make_dummy_request(url, original_request, **metadata):
    """
    Construct a HttpRequest object that is, as far as possible,
    representative of the original request - only for the provided ``url``
    instead of the one that was originally requested.
    """
    url_info = urlparse(url)
    hostname = url_info.hostname
    path = url_info.path
    port = url_info.port or 80
    scheme = url_info.scheme

    dummy_values = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': path,
        'SERVER_NAME': hostname,
        'SERVER_PORT': port,
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'HTTP_HOST': hostname,
        'wsgi.version': (1, 0),
        'wsgi.input': StringIO(),
        'wsgi.errors': StringIO(),
        'wsgi.url_scheme': scheme,
        'wsgi.multithread': True,
        'wsgi.multiprocess': True,
        'wsgi.run_once': False,
    }

    # Add important values from the original request object
    headers_to_copy = [
        'REMOTE_ADDR', 'HTTP_X_FORWARDED_FOR', 'HTTP_COOKIE',
        'HTTP_USER_AGENT', 'HTTP_AUTHORIZATION', 'wsgi.version',
        'wsgi.multithread', 'wsgi.multiprocess', 'wsgi.run_once',
    ]
    if settings.SECURE_PROXY_SSL_HEADER:
        headers_to_copy.append(settings.SECURE_PROXY_SSL_HEADER[0])
    for header in headers_to_copy:
        if header in original_request.META:
            dummy_values[header] = original_request.META[header]

    # Add additional custom metadata sent by the caller.
    dummy_values.update(**metadata)

    request = WSGIRequest(dummy_values)

    # Add a flag to let middleware know that this is a dummy request.
    request.is_dummy = True

    # Apply middleware to the request
    handler = BaseHandler()
    handler.load_middleware()
    handler._middleware_chain(request)

    return request


def validate_supplied_values(tag, max_levels=None, use_specific=None,
                             parent_page=None, menuitem_or_page=None):
    if max_levels is not None:
        if max_levels not in (1, 2, 3, 4, 5):
            raise ValueError(
                "The `%s` tag expects `max_levels` to be an integer value "
                "between 1 and 5. Please review your template." % tag
            )
    if use_specific is not None:
        if use_specific not in (0, 1, 2, 3):
            raise ValueError(
                "The `%s` tag expects `use_specific` to be an integer value "
                "between 0 and 3. Please review your template." % tag
            )
    if parent_page is not None:
        if not isinstance(parent_page, Page):
            raise ValueError(
                "The `%s` tag expects `parent_page` to be a `Page` instance. "
                "A value of type `%s` was supplied." %
                (tag, parent_page.__class__)
            )
    if menuitem_or_page is not None:
        if not isinstance(menuitem_or_page, (Page, MenuItem)):
            raise ValueError(
                "The `%s` tag expects `menuitem_or_page` to be a `Page` or "
                "`MenuItem` instance. A value of type `%s` was supplied." %
                (tag, menuitem_or_page.__class__)
            )
