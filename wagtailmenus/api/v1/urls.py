
from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^main/$', views.RenderMainMenuView.as_view()),
    url(r'^flat/$', views.RenderFlatMenuView.as_view()),
    url(r'^children/$', views.RenderChildrenMenuView.as_view()),
    url(r'^section/$', views.RenderSectionMenuView.as_view()),
]
