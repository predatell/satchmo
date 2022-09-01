from django.urls import include, re_path

import product
from satchmo_utils.signals import collect_urls
from satchmo_store.shop import get_satchmo_setting

from .category import urlpatterns as catpatterns
from .products import urlpatterns as prodpatterns


catbase = r'^' + get_satchmo_setting('CATEGORY_SLUG') + '/'
prodbase = r'^' + get_satchmo_setting('PRODUCT_SLUG') + '/'

urlpatterns = [
    re_path(prodbase, include('product.urls.products')),
    re_path(catbase, include('product.urls.category')),
]

collect_urls.send(product, section="__init__", patterns=urlpatterns)
