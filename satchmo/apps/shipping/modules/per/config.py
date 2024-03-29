from django.utils.translation import gettext_lazy as _
from livesettings.values import StringValue,DecimalValue
from livesettings.functions import config_register_list,config_get,config_get_group

SHIP_MODULES = config_get('SHIPPING', 'MODULES')

# No need to add the choice, since it is in by default
# SHIP_MODULES.add_choice(('shipping.modules.per', _('Per piece')))

SHIPPING_GROUP = config_get_group('SHIPPING')

config_register_list(

    DecimalValue(SHIPPING_GROUP,
        'PER_RATE',
        description=_("Per item price"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.per',
        default="4.00"),

    StringValue(SHIPPING_GROUP,
        'PER_SERVICE',
        description=_("Per Item Shipping Service"),
        help_text=_("Shipping service used with per item shipping"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.per',
        default="U.S. Mail"),

    StringValue(SHIPPING_GROUP,
        'PER_DAYS',
        description=_("Per Item Delivery Days"),
        requires=SHIP_MODULES,
        requiresvalue='shipping.modules.per',
        default="3 - 4 business days")
)
