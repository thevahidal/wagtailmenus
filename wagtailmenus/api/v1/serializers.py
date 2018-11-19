from rest_framework.serializers import Serializer
from wagtailmenus.conf import settings


class MenuSerializer(Serializer):
    pass


class MainMenuSerializer(MenuSerializer):
    pass


class FlatMenuSerializer(MenuSerializer):
    pass


class ChildrenMenuSerializer(MenuSerializer):
    pass


class SectionMenuSerializer(MenuSerializer):
    pass
