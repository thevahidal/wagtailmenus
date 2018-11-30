from rest_framework import fields
from rest_framework.serializers import ListSerializer, ModelSerializer, Serializer
from rest_framework_recursive.fields import RecursiveField

from wagtail.core.models import Page
from wagtailmenus.conf import settings
from wagtailmenus.models.menuitems import AbstractMenuItem

CHILDREN_ATTR = '__children'
PAGE_ATTR = '__page'

main_menu_model = settings.models.MAIN_MENU_MODEL
flat_menu_model = settings.models.FLAT_MENU_MODEL


class SimplePageSerializer(ModelSerializer):

    class Meta:
        model = Page
        fields = settings.API_PAGE_SERIALIZER_FIELDS


class MenuItemSerializer(Serializer):
    href = fields.CharField(read_only=True)
    text = fields.CharField(read_only=True)
    handle = fields.CharField(read_only=True)
    active_class = fields.CharField(read_only=True)
    page_info = SimplePageSerializer(source=PAGE_ATTR)
    children = RecursiveField(many=True, source=CHILDREN_ATTR)

    def to_representation(self, instance):
        children_val = ()
        if getattr(instance, 'sub_menu', None):
            children_val = instance.sub_menu.items

        page_val = None
        if isinstance(instance, Page):
            page_val = instance
        elif isinstance(instance, AbstractMenuItem):
            page_val = instance.link_page

        if isinstance(instance, dict):
            instance[PAGE_ATTR] = page_val
            instance[CHILDREN_ATTR] = children_val
        else:
            setattr(instance, PAGE_ATTR, page_val)
            setattr(instance, CHILDREN_ATTR, children_val)

        return super().to_representation(instance)


class DefaultMainMenuItemSerializer(MenuItemSerializer):
    pass


class DefaultFlatMenuItemSerializer(MenuItemSerializer):
    pass


MainMenuItemSerializer = settings.objects.API_MAIN_MENU_ITEM_SERIALIZER_CLASS

FlatMenuItemSerializer = settings.objects.API_FLAT_MENU_ITEM_SERIALIZER_CLASS


class MainMenuSerializer(ModelSerializer):
    items = ListSerializer(child=MainMenuItemSerializer())

    class Meta:
        model = main_menu_model
        fields = ('items', ) + main_menu_model.api_fields


class FlatMenuSerializer(ModelSerializer):
    items = ListSerializer(child=FlatMenuItemSerializer())

    class Meta:
        model = flat_menu_model
        fields = ('items', ) + flat_menu_model.api_fields


class ChildrenMenuSerializer(Serializer):
    parent_page = SimplePageSerializer()
    items = ListSerializer(child=MenuItemSerializer())


class SectionMenuSerializer(Serializer):
    section_root = MenuItemSerializer(source='root_page')
    items = ListSerializer(child=MenuItemSerializer())
