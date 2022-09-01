from django.urls import re_path

import product
from satchmo_utils.signals import collect_urls
from product.views.filters import RecentListView, BestsellersListView

urlpatterns = [
    re_path(r'^(?P<product_slug>[-\w]+)/$', product.views.get_product, name='satchmo_product'),
    re_path(r'^(?P<product_slug>[-\w]+)/prices/$', product.views.get_price, name='satchmo_product_prices'),
    re_path(r'^(?P<product_slug>[-\w]+)/price_detail/$', product.views.get_price_detail, name='satchmo_product_price_detail'),
]

urlpatterns += [
    re_path(r'^view/recent/$', RecentListView.as_view(), name='satchmo_product_recently_added'),
    re_path(r'^view/bestsellers/$', BestsellersListView.as_view(), name='satchmo_product_best_selling'),
]

# here we are sending a signal to add patterns to the base of the shop.
collect_urls.send(sender=product, patterns=urlpatterns, section="product")
