from wagtailmenus.views import (
    MainMenuEditView, FlatMenuCreateView, FlatMenuCopyView, FlatMenuEditView
)


class LanguageSpecificMainMenuEditView(MainMenuEditView):

    def get_template_names(self):
        return ['wagtailmenus/wagtailtrans_integration/mainmenu_edit.html']


class LanguageSpecificFlatMenuCreateView(FlatMenuCreateView):

    def get_template_names(self):
        return ['wagtailmenus/wagtailtrans_integration/flatmenu_create.html']


class LanguageSpecificFlatMenuEditView(FlatMenuEditView):

    def get_template_names(self):
        return ['wagtailmenus/wagtailtrans_integration/flatmenu_edit.html']


class LanguageSpecificFlatMenuCopyView(FlatMenuCopyView):

    def get_template_names(self):
        return ['wagtailmenus/wagtailtrans_integration/flatmenu_copy.html']
