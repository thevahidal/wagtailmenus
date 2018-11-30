# NOTE: All supported app settings must be added here


# -----------------
# REST API settings
# -----------------

GENERAL_MENU_ITEM_SERIALIZER_FIELDS = ('text', 'href', 'page', 'children')

PAGE_SERIALIZER_FIELDS = ('id', 'title', 'slug')

MAIN_MENU_ITEM_SERIALIZER_FIELDS = ('text', 'href', 'handle', 'page', 'children')

FLAT_MENU_ITEM_SERIALIZER_FIELDS = ('text', 'href', 'handle', 'page', 'children')

PARENT_PAGE_SERIALIZER_FIELDS = ('id', 'title', 'slug')

MAIN_MENU_SERIALIZER_FIELDS = ('site', 'items')

FLAT_MENU_SERIALIZER_FIELDS = ('site', 'handle', 'title', 'heading', 'items')

# ----------
# Deprecated
# ----------
