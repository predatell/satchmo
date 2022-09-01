import logging

from django.utils.translation import gettext_lazy as _


log = logging.getLogger('tieredweight.config')

from shipping.config import SHIPPING_ACTIVE

SHIPPING_ACTIVE.add_choice(('shipping.modules.tieredweight', _('Tiered Weight Shipping')))

log.debug('loaded')