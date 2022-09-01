"""
URLConf for Satchmo Contacts.
"""
from django.urls import re_path

from satchmo_utils.signals import collect_urls
from satchmo_store import contact
from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from satchmo_store.contact import views

ssl = get_satchmo_setting('SSL', default_value=False)

urlpatterns = [
    re_path(r'^$', views.view, name='satchmo_account_info'),
    re_path(r'^update/$', views.update, name='satchmo_profile_update'),
    re_path(r'^address/create/$', views.address_create_edit, name='satchmo_address_create'),
    re_path(r'^address/edit/(?P<id>\d+)/$', views.address_create_edit, name='satchmo_address_edit'),
    re_path(r'^address/delete/(?P<id>\d+)/$', views.address_delete, name='satchmo_address_delete'),
    re_path(r'^ajax_state/$', views.ajax_get_state, {'SSL': ssl}, 'satchmo_contact_ajax_state'),
]

collect_urls.send(sender=contact, patterns=urlpatterns)
