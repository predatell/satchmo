from django.urls import re_path

from shipping.views import displayDoc

# Urls which need to be loaded at root level.
adminpatterns = [
    re_path(r'^admin/print/(?P<doc>[-\w]+)/(?P<id>\d+)', displayDoc, name='satchmo_print_shipping'),
]
