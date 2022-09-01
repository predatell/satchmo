"""
Urls for wishlists, note that this does not have to get added manually to the urls, it will be added automatically by satchmo core if this app is installed.
"""
from django.urls import re_path, include

from livesettings.functions import config_value_safe
from . import views
import logging

log = logging.getLogger('wishlist.urls')

urlpatterns = [
    re_path(r'^$', views.wishlist_view, name='satchmo_wishlist_view'),
    re_path(r'^add/$', views.wishlist_add, name='satchmo_wishlist_add'),
    re_path(r'^add/ajax/$', views.wishlist_add_ajax, name='satchmo_wishlist_add_ajax'),
    re_path(r'^remove/$', views.wishlist_remove, name='satchmo_wishlist_remove'),
    re_path(r'^remove/ajax$', views.wishlist_remove_ajax, name='satchmo_wishlist_remove_ajax'),
    re_path(r'^add_cart/$', views.wishlist_move_to_cart, name='satchmo_wishlist_move_to_cart'),
]


def add_wishlist_urls(sender, patterns=(), **kwargs):
    wishbase = r'^' + config_value_safe('SHOP', 'WISHLIST_SLUG', "wishlist") + '/'
    log.debug('adding wishlist urls at %s', wishbase)
    wishpatterns = [
        re_path(wishbase, include('satchmo_ext.wishlist.urls'))
    ]
    patterns += wishpatterns
