from django.utils.translation import gettext_lazy as _
import logging
log = logging.getLogger('shipping.modules.productshipping')
from shipping.config import SHIPPING_ACTIVE

SHIPPING_ACTIVE.add_choice(('shipping.modules.productshipping', _('Shipping By Product')))

log.debug('loaded')
