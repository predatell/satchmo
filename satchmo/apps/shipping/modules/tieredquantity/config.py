from django.utils.translation import gettext_lazy as _
from shipping.config import SHIPPING_ACTIVE

SHIPPING_ACTIVE.add_choice(('shipping.modules.tieredquantity', _('Tiered Quantity')))

