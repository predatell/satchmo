from django.urls import re_path
from django.views.i18n import set_language

urlpatterns = [
    re_path(r'^setlang/$', set_language, name='satchmo_set_language'),
]
