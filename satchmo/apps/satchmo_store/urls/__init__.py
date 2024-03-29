"""
The simplest possible satchmo url configuration, which loads the shop at whatever
you've put in your SATCHMO_SETTING['SHOP_BASE'], or "shop/" by default.

To customize for your store, make an url module, and load the patterns you need.

Example 1, loading a store at the root, rather than at "shop/"::

    from satchmo_store.urls import basepatterns, defaultpatterns
    from satchmo_store.shop.urls import urlpatterns as shoppatterns

    urlpatterns = basepatterns + defaultpatterns + shoppatterns

Example 2, loading a store, where you are calling admin.autodiscover()
earlier in your custom urls.py file, and you want the shop at "store/"::

    # at the top of the file
    from satchmo_store.urls import basepatterns

    [ ... your code here, which includes admin.autodiscover() ... ]

    urlpatterns += basepatterns + [
        url(r'^store/', include('satchmo_store.shop.urls')),
    ]

"""
from django.urls import include, re_path

from satchmo_utils import urlhelper
from satchmo_store.shop import get_satchmo_setting

from .base import urlpatterns as basepatterns
from .default import urlpatterns as defaultpatterns


shop_base = get_satchmo_setting('SHOP_BASE')
if shop_base in ('', '/'):
    from satchmo_store.shop.urls import urlpatterns as shoppatterns
else:
    shopregex = '^' + shop_base[1:] + '/'
    shoppatterns = [
        re_path(shopregex, include('satchmo_store.shop.urls')),
    ]

urlpatterns = basepatterns + shoppatterns + defaultpatterns
urlhelper.remove_duplicate_urls(urlpatterns, [])
