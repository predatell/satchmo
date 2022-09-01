from django.urls import re_path

from product.views import CategoryView, CategoryIndexView

urlpatterns = [
    re_path(r'^(?P<parent_slugs>([-\w]+/)*)?(?P<slug>[-\w]+)/$', CategoryView.as_view(), name='satchmo_category'),
    re_path(r'^$', CategoryIndexView.as_view(), name='satchmo_category_index'),
]
