from django.urls import re_path

from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from payment.views.checkout import success
from . import views

ssl = get_satchmo_setting('SSL', default_value=False)

urlpatterns = [
    re_path(r'^$', views.pay_ship_info, {'SSL': ssl}, name='SAGEPAY_satchmo_checkout-step2'),
    re_path(r'^confirm/$', views.confirm_info, {'SSL': ssl}, name='SAGEPAY_satchmo_checkout-step3'),
    re_path(r'^secure3d/$', views.confirm_secure3d, {'SSL': ssl}, name='SAGEPAY_satchmo_checkout-secure3d'),
    re_path(r'^success/$', success, {'SSL': ssl}, name='SAGEPAY_satchmo_checkout-success'),
]
