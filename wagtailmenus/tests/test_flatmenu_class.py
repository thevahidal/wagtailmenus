from django.test import TestCase, override_settings

from wagtailmenus.models import FlatMenu
from wagtailmenus.tests import utils

Page = utils.get_page_model()
Site = utils.get_site_model()

TEMPLATE_LIST_DEFAULT = ('default_1.html', 'default_2.html')
TEMPLATE_LIST_TEST_1 = ('test-1a.html', 'test-1b.html')
TEMPLATE_LIST_TEST_2 = ('test-2a.html', 'test-2b.html')
TEMPLATES_BY_HANDLE_DICT = {
    'default': TEMPLATE_LIST_DEFAULT,
    'test-1': TEMPLATE_LIST_TEST_1,
    'test-2': TEMPLATE_LIST_TEST_2,
}


class TestFlatMenuClass(TestCase):

    def setUp(self):
        site = Site.objects.get()
        self.menus = (
            FlatMenu.objects.create(
                site=site, handle='test-1', title="Test Menu 1"
            ),
            FlatMenu.objects.create(
                site=site, handle='test-2', title="Test Menu 2"
            ),
            FlatMenu.objects.create(
                site=site, handle='test-3', title="Test Menu 3"
            )
        )
        for menu in self.menus:
            menu._option_vals = utils.make_optionvals_instance()

    def test_get_sub_menu_template_names_from_setting_returns_none_if_setting_not_set(self):
        for menu in self.menus:
            self.assertEqual(
                menu.get_sub_menu_template_names_from_setting(), None
            )

    @override_settings(
        WAGTAILMENUS_DEFAULT_FLAT_MENU_SUB_MENU_TEMPLATES=TEMPLATE_LIST_DEFAULT
    )
    def test_get_sub_menu_template_names_from_setting_returns_same_value_for_all_menus_when_setting_is_list(self):
        for menu in self.menus:
            self.assertEqual(
                menu.get_sub_menu_template_names_from_setting(), TEMPLATE_LIST_DEFAULT
            )

    @override_settings(
        WAGTAILMENUS_DEFAULT_FLAT_MENU_SUB_MENU_TEMPLATES=TEMPLATES_BY_HANDLE_DICT
    )
    def test_get_sub_menu_template_names_from_setting_returns_different_templates_when_setting_is_dict(self):
        menu = self.menus[0]
        self.assertEqual(TEMPLATES_BY_HANDLE_DICT[menu.handle], TEMPLATE_LIST_TEST_1)
        self.assertEqual(menu.get_sub_menu_template_names_from_setting(), TEMPLATE_LIST_TEST_1)

        menu = self.menus[1]
        self.assertEqual(TEMPLATES_BY_HANDLE_DICT[menu.handle], TEMPLATE_LIST_TEST_2)
        self.assertEqual(menu.get_sub_menu_template_names_from_setting(), TEMPLATE_LIST_TEST_2)

        menu = self.menus[2]
        self.assertNotIn(menu.handle, TEMPLATES_BY_HANDLE_DICT.keys())
        self.assertEqual(menu.get_sub_menu_template_names_from_setting(), TEMPLATE_LIST_DEFAULT)
