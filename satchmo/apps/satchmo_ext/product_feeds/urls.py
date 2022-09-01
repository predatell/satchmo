"""
Urls for product feeds, note that this does not have to get added manually to the urls, it will be added automatically by satchmo core if this app is installed.
"""
from django.urls import re_path, include

from . import views
import logging
log = logging.getLogger('product_feeds.urls')

urlpatterns = [
    re_path(r'atom/$', views.product_feed, name='satchmo_atom_feed'),
    re_path(r'atom/(?P<category>([-\w])*)/$', views.product_feed, name='satchmo_atom_category_feed'),
    re_path(r'products.csv$', views.admin_product_feed, {'template': "product_feeds/product_feed.csv"}, name='satchmo_product_feed'),
]

feedpatterns = [
    re_path(r'^feed/', include('satchmo_ext.product_feeds.urls'))
]


def add_feed_urls(sender, patterns=[], **kwargs):
    log.debug("Adding product_feed urls")
    patterns += feedpatterns
