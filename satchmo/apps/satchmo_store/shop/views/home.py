from django.views.generic import ListView

from livesettings.functions import config_value

from product.models import Product
from product.views import display_featured


class HomeListView(ListView):
    model = Product
    template_name = "shop/index.html"
    context_object_name = "all_products_list"

    def get_queryset(self):
        return Product.objects.featured_by_site()

    def get_paginate_by(self, queryset):
        return config_value('PRODUCT','NUM_PAGINATED')
    
    def get_context_data(self, **kwargs):
        kwargs['object_list'] = display_featured(queryset=self.object_list)
        return super(HomeListView, self).get_context_data(**kwargs)
