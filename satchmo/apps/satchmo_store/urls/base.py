"""Base urls used by Satchmo.

Split out from urls.py to allow much easier overriding and integration with larger apps.
"""
from django.urls import include, re_path
from satchmo_utils.signals import collect_urls
from product.urls.base import adminpatterns as prodpatterns
from shipping.urls import adminpatterns as shippatterns
import logging
import satchmo_store

log = logging.getLogger('shop.urls')

urlpatterns = [
    re_path(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    re_path(r'^accounts/', include('satchmo_store.accounts.urls')),
    re_path(r'^settings/', include('livesettings.urls')),
    re_path(r'^cache/', include('keyedcache.urls')),
] + prodpatterns + shippatterns

collect_urls.send(sender=satchmo_store, patterns=urlpatterns)
