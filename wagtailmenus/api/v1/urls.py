
from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^main_menu/$', views.MainMenuGeneratorView.as_view()),
    url(r'^flat_menu/$', views.FlatMenuGeneratorView.as_view()),
    url(r'^children_menu/$', views.ChildrenMenuGeneratorView.as_view()),
    url(r'^section_menu/$', views.SectionMenuGeneratorView.as_view()),
]
