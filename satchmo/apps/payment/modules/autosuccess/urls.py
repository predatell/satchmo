from django.urls import re_path

from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from payment.views.checkout import success
from payment.modules.autosuccess.views import one_step

ssl = get_satchmo_setting('SSL', default_value=False)

urlpatterns = [
    re_path(r'^$', one_step, {'SSL': ssl}, name='AUTOSUCCESS_satchmo_checkout-step2'),
    re_path(r'^success/$', success, {'SSL': ssl}, name='AUTOSUCCESS_satchmo_checkout-success'),
]
