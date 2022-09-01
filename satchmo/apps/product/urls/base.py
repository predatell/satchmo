"""Urls which need to be loaded at root level."""
from django.urls import re_path

from product.views import get_configurable_product_options
from product.views import adminviews

adminpatterns = [
    re_path(r'^admin/product/configurableproduct/(?P<id>\d+)/getoptions/',
            get_configurable_product_options, name='satchmo_admin_configurableproduct'),
]

adminpatterns += [
    re_path(r'^admin/inventory/edit/$', adminviews.edit_inventory, name='satchmo_admin_edit_inventory'),
    re_path(r'^inventory/export/$', adminviews.export_products, name='satchmo_admin_product_export'),
    re_path(r'^inventory/import/$', adminviews.import_products, name='satchmo_admin_product_import'),
    # re_path(r'^inventory/report/$', adminviews.product_active_report, {}, 'satchmo_admin_product_report'),
    re_path(r'^admin/(?P<product_id>\d+)/variations/$', adminviews.variation_manager, name='satchmo_admin_variation_manager'),
    re_path(r'^admin/variations/$', adminviews.VariationListView.as_view(), name='satchmo_admin_variation_list'),
]
