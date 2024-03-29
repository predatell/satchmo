from django.utils.translation import gettext_lazy as _
from livesettings.values import StringValue,DecimalValue
from livesettings.functions import config_register_list,config_get,config_get_group

SHIP_MODULES = config_get('SHIPPING', 'MODULES')
SHIP_MODULES.add_choice(('shipping.modules.flat', _('Flat rate')))
SHIPPING_GROUP = config_get_group('SHIPPING')

config_register_list(

    DecimalValue(SHIPPING_GROUP,
        'FLAT_RATE',
        description=_("Flat shipping"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.flat',
        default="4.00"),

    StringValue(SHIPPING_GROUP,
        'FLAT_SERVICE',
        description=_("Flat Shipping Service"),
        help_text=_("Shipping service used with Flat rate shipping"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.flat',
        default="U.S. Mail"),
    
    StringValue(SHIPPING_GROUP,
        'FLAT_DAYS',
        description=_("Flat Delivery Days"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.flat',
        default="3 - 4 business days")
)
