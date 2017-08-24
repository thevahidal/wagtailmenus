from __future__ import absolute_import, unicode_literals

from django.test import TestCase
from wagtail.wagtailcore import hooks


class TestHooks(TestCase):
    fixtures = ['test.json']

    def test_menus_modify_menu_items(self):

        # Using positional kwargs to ensure all args remain present
        @hooks.register('menus_modify_menu_items')
        def modify_menu_items(
            menu_items, request, parent_page, original_menu_tag, menu_instance,
            current_level, max_levels, stop_at_this_level, current_site,
            current_page, use_specific, apply_active_classes,
            allow_repeating_parents, use_absolute_page_urls
        ):
            if original_menu_tag == 'main_menu' and current_level == 1:
                menu_items.append({
                    'href': 'https://rkh.co.uk',
                    'text': 'VISIT RKH.CO.UK',
                    'active_class': 'external',
                })
            return menu_items

        # Let's render the test homepage to see what happens!
        response = self.client.get('/')

        # unhook asap to prevent knock-on effects on failure
        del hooks._hooks['menus_modify_menu_items']

        # If the the hook failed to recieve any of the arguments defined
        # on `modify_menu_items` above, there will be an error
        self.assertEqual(response.status_code, 200)

        # There are 4 main menus being output, and because our hook only adds
        # the additional item to the first level of each of those, the
        # 'VISIT RKH.CO.UK' text should appear exactly 4 times
        self.assertContains(response, 'VISIT RKH.CO.UK', 4)
