from django.urls import re_path

from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from payment.views.confirm import confirm_free_order
from . import views

ssl = get_satchmo_setting('SSL', default_value=False)

urlpatterns = [
    re_path(r'^$', views.pay_ship_info, {'SSL': ssl}, name='GOOGLE_satchmo_checkout-step2'),
    re_path(r'^confirm/$', views.confirm_info, {'SSL': ssl}, name='GOOGLE_satchmo_checkout-step3'),
    re_path(r'^success/$', views.success, {'SSL': ssl}, name='GOOGLE_satchmo_checkout-success'),
    re_path(r'^notification/$', views.notification, {'SSL': ssl}, name='GOOGLE_satchmo_checkout-notification'),
    re_path(r'^confirmorder/$', confirm_free_order, {'SSL': ssl, 'key': 'GOOGLE'}, name='GOOGLE_satchmo_checkout_free-confirm')
]
