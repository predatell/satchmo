#
#   SERMEPA / ServiRed payments module for Satchmo
#
#   Author: Michal Salaban <michal (at) salaban.info>
#   with a great help of Fluendo S.A., Barcelona
#
#   Based on "Guia de comercios TPV Virtual SIS" ver. 5.18, 15/11/2008, SERMEPA
#   For more information about integration look at http://www.sermepa.es/
#
#   TODO: SERMEPA interface provides possibility of recurring payments, which
#   could be probably used for SubscriptionProducts. This module doesn't support it.
#
from django.urls import re_path

from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from payment.views.confirm import confirm_free_order
from payment.views.checkout import success, failure
from . import views

ssl = get_satchmo_setting('SSL', default_value=False)

urlpatterns = [
    re_path(r'^$', views.pay_ship_info, {'SSL': ssl}, name='SERMEPA_satchmo_checkout-step2'),
    re_path(r'^confirm/$', views.confirm_info, {'SSL': ssl}, name='SERMEPA_satchmo_checkout-step3'),
    re_path(r'^success/$', success, {'SSL': ssl}, name='SERMEPA_satchmo_checkout-success'),
    re_path(r'^failure/$', failure, {'SSL': ssl}, name='SERMEPA_satchmo_checkout-failure'),
    re_path(r'^notify/$', views.notify_callback, {'SSL': ssl}, name='SERMEPA_satchmo_checkout-notify_callback'),
    re_path(r'^confirmorder/$', confirm_free_order, {'SSL': ssl, 'key': 'SERMEPA'}, name='SERMEPA_satchmo_checkout_free-confirm')
]
