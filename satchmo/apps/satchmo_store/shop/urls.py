from django.urls import include, re_path
from django.views.generic.base import TemplateView
from django.contrib.sitemaps.views import sitemap

from product.urls import urlpatterns as productpatterns
from satchmo_store import shop
from satchmo_store.shop.views.sitemaps import sitemaps
from satchmo_utils.signals import collect_urls
from satchmo_store.shop.views import home, smart, cart, contact, orders, search

urlpatterns = shop.get_satchmo_setting('SHOP_URLS')

urlpatterns += [
    re_path(r'^$', home.HomeListView.as_view(), name='satchmo_shop_home'),
    re_path(r'^add/$', smart.smart_add, name='satchmo_smart_add'),
    re_path(r'^cart/$', cart.display, name='satchmo_cart'),
    re_path(r'^cart/accept/$', cart.agree_terms, name='satchmo_cart_accept_terms'),
    re_path(r'^cart/add/$', cart.add, name='satchmo_cart_add'),
    re_path(r'^cart/add/ajax/$', cart.add_ajax, name='satchmo_cart_add_ajax'),
    re_path(r'^cart/qty/$', cart.set_quantity, name='satchmo_cart_set_qty'),
    re_path(r'^cart/qty/ajax/$', cart.set_quantity_ajax, name='satchmo_cart_set_qty_ajax'),
    re_path(r'^cart/remove/$', cart.remove, name='satchmo_cart_remove'),
    re_path(r'^cart/remove/ajax/$', cart.remove_ajax, name='satchmo_cart_remove_ajax'),
    re_path(r'^checkout/', include('payment.urls')),
    re_path(r'^contact/$', contact.ContactFormView.as_view(), name='satchmo_contact'),
    re_path(r'^history/$', orders.order_history, name='satchmo_order_history'),
    re_path(r'^quickorder/$', cart.add_multiple, name='satchmo_quick_order'),
    re_path(r'^tracking/(?P<order_id>\d+)/$', orders.order_tracking, name='satchmo_order_tracking'),
    re_path(r'^search/$', search.search_view, name='satchmo_search'),
    re_path(r'^l10n/', include('l10n.urls')),
]

# here we add product patterns directly into the root url
urlpatterns += productpatterns

urlpatterns += [
    re_path(r'^contact/thankyou/$', TemplateView.as_view(template_name='shop/contact_thanks.html'), name='satchmo_contact_thanks'),
    re_path(r'^sitemap\.xml$', sitemap, {'sitemaps': sitemaps}, name='satchmo_sitemap_xml'),
]

# here we are sending a signal to add patterns to the base of the shop.
collect_urls.send(sender=shop, patterns=urlpatterns)
