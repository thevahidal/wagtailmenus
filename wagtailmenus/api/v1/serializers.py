from rest_framework import serializers
from wagtailmenus.conf import settings

main_menu_model = settings.models.MAIN_MENU_MODEL
flat_menu_model = settings.models.FLAT_MENU_MODEL


class MainMenuSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = main_menu_model
        fields = main_menu_model.api_fields


class MainMenuDetailSerializer(MainMenuSerializer):
    pass


class FlatMenuSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = flat_menu_model
        fields = flat_menu_model.api_fields


class FlatMenuDetailSerializer(FlatMenuSerializer):
    pass


class ChildrenMenuSerializer(serializers.Serializer):
    pass


class SectionMenuSerializer(serializers.Serializer):
    pass
