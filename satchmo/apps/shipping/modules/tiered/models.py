"""
Tiered shipping models
"""
from __future__ import unicode_literals
import datetime
import logging
import operator
from six.moves import reduce
from six import python_2_unicode_compatible
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import get_language, gettext_lazy as _

from shipping.modules.base import BaseShipper
from livesettings.functions import config_value

log = logging.getLogger('shipping.Tiered')


class TieredPriceException(Exception):
    def __init__(self, reason):
        self.reason = reason


class Shipper(BaseShipper):

    def __init__(self, carrier):
        self.id = carrier.key
        self.carrier = carrier
        super(BaseShipper, self).__init__()

    def __str__(self):
        """
        This is mainly helpful for debugging purposes
        """
        return "Tiered_Shipper: %s" % self.id

    def description(self):
        """
        A basic description that will be displayed to the user when selecting their shipping options
        """
        return self.carrier.description

    def cost(self):
        """
        Complex calculations can be done here as long as the return value is a dollar figure
        """
        assert(self._calculated)
        if config_value('SHIPPING_TIERED', 'MIN_PRICE_FOR') == 'NOT_DISCOUNTABLE':
            total = self.cart.undiscounted_total
        else:
            total = Decimal("0.00")
            for cartitem in self.cart.cartitem_set.all():
                if cartitem.product.is_shippable:
                    total += cartitem.line_total
        return self.carrier.price(total)

    def method(self):
        """
        Describes the actual delivery service (Mail, FedEx, DHL, UPS, etc)
        """
        return self.carrier.method

    def expectedDelivery(self):
        """
        Can be a plain string or complex calcuation returning an actual date
        """
        return self.carrier.delivery

    def valid(self, order=None):
        """
        Can do complex validation about whether or not this option is valid.
        For example, may check to see if the recipient is in an allowed country
        or location.
        """
        if order:
            if config_value('SHIPPING_TIERED', 'MIN_PRICE_FOR') == 'NOT_DISCOUNTABLE':
                sub_total = order.sub_total
            else:
                itemprices = [item.sub_total for item in order.orderitem_set.all() if item.product.is_shippable]
                if itemprices:
                    sub_total = reduce(operator.add, itemprices)
                else:
                    sub_total = Decimal('0.00')

            try:
                price = self.carrier.price(sub_total)

            except TieredPriceException:
                return False

        elif self.cart:
            try:
                price = self.cost()
            except TieredPriceException:
                return False

        return True


@python_2_unicode_compatible
class Carrier(models.Model):
    key = models.SlugField(_('Key'))
    ordering = models.IntegerField(_('Ordering'), default=0)
    active = models.BooleanField(_('Active'), default=True)

    def _find_translation(self, language_code=None):
        if not language_code:
            language_code = get_language()

        c = self.translations.filter(languagecode__exact=language_code)
        ct = c.count()

        if not c or ct == 0:
            pos = language_code.find('-')
            if pos > -1:
                short_code = language_code[:pos]
                log.debug("Carrier: Trying to find root language content for: [%s]", short_code)
                c = self.translations.filter(languagecode__exact=short_code)
                ct = c.count()
                if ct > 0:
                    log.debug("Carrier: Found root language content for: [%s]", short_code)

        if not c or ct == 0:
            # log.debug("Trying to find default language content for: %s", self)
            c = self.translations.filter(languagecode__istartswith=settings.LANGUAGE_CODE)
            ct = c.count()

        if not c or ct == 0:
            # log.debug("Trying to find *any* language content for: %s", self)
            c = self.translations.all()
            ct = c.count()

        if ct > 0:
            trans = c[0]
        else:
            trans = None

        return trans

    def delivery(self):
        """Get the delivery, looking up by language code, falling back intelligently.
        """
        trans = self._find_translation()

        if trans:
            return trans.delivery
        else:
            return ""

    delivery = property(delivery)

    def description(self):
        """Get the description, looking up by language code, falling back intelligently.
        """
        trans = self._find_translation()

        if trans:
            return trans.description
        else:
            return ""

    description = property(description)

    def method(self):
        """Get the description, looking up by language code, falling back intelligently.
        """
        trans = self._find_translation()

        if trans:
            return trans.method
        else:
            return ""

    method = property(method)

    def name(self):
        """Get the name, looking up by language code, falling back intelligently.
        """
        trans = self._find_translation()

        if trans:
            return trans.name
        else:
            return ""

    name = property(name)

    def price(self, total):
        """Get a price for this total."""
        if total == 0:
            total = Decimal('0.00')  # total was "0E-8", which breaks mysql

        # first check for special discounts
        prices = self.tiers.filter(expires__isnull=False, min_total__lte=total).exclude(expires__lt=datetime.date.today())

        if not prices.count() > 0:
            prices = self.tiers.filter(expires__isnull=True, min_total__lte=total)

        if prices.count() > 0:
            # Get the price with the quantity closest to the one specified without going over
            return Decimal(prices.order_by('-min_total')[0].price)

        else:
            log.debug("No tiered price found for %s: total=%s", self, total)
            raise TieredPriceException('No price available')

    def __str__(self):
        return "Carrier: %s" % self.name

    class Meta:
        ordering = ('ordering',)


class CarrierTranslation(models.Model):
    carrier = models.ForeignKey('Carrier', related_name='translations', on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES, )
    name = models.CharField(_('Carrier'), max_length=50, )
    description = models.CharField(_('Description'), max_length=200)
    method = models.CharField(_('Method'), help_text=_("i.e. US Mail"), max_length=200)
    delivery = models.CharField(_('Delivery Days'), max_length=200)

    class Meta:
        ordering = ('languagecode', 'name')


@python_2_unicode_compatible
class ShippingTier(models.Model):
    carrier = models.ForeignKey('Carrier', related_name='tiers', on_delete=models.CASCADE)
    min_total = models.DecimalField(_("Min Price"), max_digits=10, decimal_places=2,
                                    help_text=_('The minimum price for this tier to apply'))
    price = models.DecimalField(_("Shipping Price"), max_digits=10, decimal_places=2, )
    expires = models.DateField(_("Expires"), null=True, blank=True)

    def __str__(self):
        return "ShippingTier: %s @ %s" % (self.price, self.min_total)

    class Meta:
        ordering = ('carrier', 'price')


from . import config
