from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from satchmo_store.shop.models import Config, Cart, CartItem, CartItemDetails, Order, OrderItem, OrderItemDetail, OrderStatus, OrderPayment, OrderPaymentFailure, OrderAuthorization, OrderVariable, OrderTaxDetail
from satchmo_store.shop.forms import OrderPaymentBaseAdminForm
from satchmo_utils.admin import AutocompleteAdmin


class CartItem_Inline(admin.TabularInline):
    model = CartItem
    extra = 3
    raw_id_fields = ('product',)

    
class CartItemDetails_Inline(admin.StackedInline):
    model = CartItemDetails
    extra = 1

    
class ConfigOptions(admin.ModelAdmin):
    list_display = ('site', 'store_name')
    filter_horizontal = ('shipping_countries',)
    fieldsets = (
        (None, {'fields': (
            'site', 'store_name', 'store_description')
            }),
        (_('Store Contact'), {'fields' : (
            'store_email', 'phone', 'street1', 'street2',
            'city', 'state', 'postal_code', 'country',)
            }),
        (_('Shipping Countries'), {'fields' : (
            'in_country_only', 'sales_country', 'shipping_countries')
            })
    )

    
class CartOptions(admin.ModelAdmin):
    list_display = ('date_time_created','numItems','total')
    inlines = [CartItem_Inline]

    
class CartItemOptions(admin.ModelAdmin):
    inlines = [CartItemDetails_Inline]

    
class OrderItem_Inline(admin.TabularInline):
    model = OrderItem
    extra = 3
    raw_id_fields = ('product',)
    list_select_related = True
    fields = ('product', 'product_sku', 'quantity', 'unit_price', 'unit_tax', 'line_item_price', 'tax', 'expire_date', 'completed', 'discount')
    readonly_fields = ('product_sku',)

    def product_sku(self, order_item):
        return order_item.product.sku

        
class OrderItemDetail_Inline(admin.TabularInline):
    model = OrderItemDetail
    extra = 3

    
class OrderAuthorizationDetail_Inline(admin.TabularInline):
    model = OrderAuthorization
    extra = 0
    #form = OrderAuthorizationAdminForm
    form = OrderPaymentBaseAdminForm
    
    
class OrderPaymentDetail_Inline(admin.TabularInline):
    model = OrderPayment
    extra = 0
    #form = OrderPaymentAdminForm
    form = OrderPaymentBaseAdminForm
    
    
class OrderPaymentFailureDetail_Inline(admin.TabularInline):
    model = OrderPaymentFailure
    extra = 0
    #form = OrderPaymentFailureAdminForm
    form = OrderPaymentBaseAdminForm
    
    
class OrderStatus_Inline(admin.StackedInline):
    model = OrderStatus
    extra = 1

    
class OrderVariable_Inline(admin.TabularInline):
    model = OrderVariable
    extra = 1

    
class OrderTaxDetail_Inline(admin.TabularInline):
    model = OrderTaxDetail
    extra = 1

    
class OrderOptions(admin.ModelAdmin):
    fieldsets = (
        (None, {'fields': ('site', 'contact', 'method', 'status', 'discount_code', 'notes')}), (_('Shipping Method'), {'fields':
            ('shipping_method', 'shipping_description')}), (_('Shipping Address'), {'classes': ('collapse',), 'fields':
            ('ship_street1', 'ship_street2', 'ship_city', 'ship_state', 'ship_postal_code', 'ship_country')}), (_('Billing Address'), {'classes': ('collapse',), 'fields':
            ('bill_street1', 'bill_street2', 'bill_city', 'bill_state', 'bill_postal_code', 'bill_country')}), (_('Totals'), {'fields':
            ('sub_total', 'shipping_cost', 'shipping_discount', 'tax', 'discount', 'total', 'time_stamp')}))
    list_display = ('id', 'contact', 'time_stamp', 'order_total', 'balance_forward', 'status', 'invoice', 'packingslip', 'shippinglabel')
    list_filter = ['time_stamp', 'status']
    date_hierarchy = 'time_stamp'
    search_fields = ('contact__first_name', 'contact__last_name', 'contact__email')
    # related_search_fields = {'contact': ('first_name', 'last_name', 'email')}
    # related_string_functions = {'contact': lambda c: "%s &lt;%s&gt;" % (c.full_name, c.email)}
    inlines = [OrderItem_Inline, OrderStatus_Inline, OrderVariable_Inline,
        OrderTaxDetail_Inline, OrderAuthorizationDetail_Inline,
        OrderPaymentDetail_Inline, OrderPaymentFailureDetail_Inline]
    readonly_fields = ('status',)

    
class OrderItemOptions(admin.ModelAdmin):
    inlines = [OrderItemDetail_Inline]

    
class OrderPaymentOptions(admin.ModelAdmin):
    list_filter = ['payment']
    list_display = ['id', 'order', 'payment', 'amount_total', 'time_stamp']
    fieldsets = (
        (None, {'fields': ('order', 'payment', 'amount', 'transaction_id', 'time_stamp')}), )
    raw_id_fields = ['order']
    form = OrderPaymentBaseAdminForm


class OrderAuthorizationOptions(OrderPaymentOptions):
    form = OrderPaymentBaseAdminForm
    list_display = ['id', 'order', 'capture', 'payment', 'amount_total', 'complete', 'time_stamp']
    fieldsets = (
        (None, {'fields': ('order', 'capture', 'payment', 'amount', 'transaction_id', 'complete', 'time_stamp')}), )

    
admin.site.register(Cart, CartOptions)
admin.site.register(CartItem, CartItemOptions)
admin.site.register(Config, ConfigOptions)
admin.site.register(Order, OrderOptions)
admin.site.register(OrderItem, OrderItemOptions)
admin.site.register(OrderPayment, OrderPaymentOptions)
admin.site.register(OrderAuthorization, OrderAuthorizationOptions)
