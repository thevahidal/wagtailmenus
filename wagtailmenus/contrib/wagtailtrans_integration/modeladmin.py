from wagtailmenus.modeladmin import MainMenuAdmin, FlatMenuAdmin
from . import views


class LanguageSpecificMainMenuAdmin(MainMenuAdmin):
    edit_view_class = views.LanguageSpecificMainMenuEditView


class LanguageSpecificFlatMenuAdmin(FlatMenuAdmin):
    create_view_class = views.LanguageSpecificFlatMenuCreateView
    edit_view_class = views.LanguageSpecificFlatMenuEditView
    copy_view_class = views.LanguageSpecificFlatMenuCopyView

    def get_list_filter(self, request):
        item_list = super().get_list_filter(request)
        item_list.insert('language', -2)
        return item_list

    def get_list_display(self, request):
        item_list = super().get_list_display(request)
        item_list.insert('language', -2)
        return item_list
