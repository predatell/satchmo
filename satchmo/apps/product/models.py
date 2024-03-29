"""
Base model used for products.  Stores hierarchical categories
as well as individual product level information which includes
options.
"""
from __future__ import unicode_literals
from __future__ import print_function
from six import python_2_unicode_compatible
from decimal import Context, Decimal, ROUND_FLOOR

from django import forms
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q
from django.utils.encoding import smart_str
from django.utils.translation import get_language, gettext, gettext_lazy as _
from django.utils.functional import cached_property
try:
    from django.core.urlresolvers import reverse
except ImportError:
    from django.urls import reverse

from l10n.utils import moneyfmt, lookup_translation
from livesettings.functions import config_value, config_value_safe
from livesettings.models import SettingNotSet
from .prices import get_product_quantity_price, get_product_quantity_adjustments
from product import active_product_types
from product.prices import PriceAdjustmentCalc
from satchmo_utils import get_flat_list
from satchmo_utils.fields import CurrencyField
from satchmo_utils.satchmo_thumbnail.field import ImageWithThumbnailField
from satchmo_utils.unique_id import slugify
from . import config   # This import is required to make sure livesettings picks up the config values
import datetime
import keyedcache
import logging
import operator
from . import signals
import six
from six.moves import reduce

log = logging.getLogger('product.models')

dimension_units = (('cm', 'cm'), ('in', 'in'))

weight_units = (('kg', 'kg'), ('lb', 'lb'))

DISCOUNT_SHIPPING_CHOICES = (
    ('NONE', _('None')),
    ('FREE', _('Free Shipping')),
    ('FREECHEAP', _('Cheapest shipping option is free')),
    ('APPLY', _('Apply the discount above to shipping'))
)

SHIP_CLASS_CHOICES = (
    ('DEFAULT', _('Default')),
    ('YES', _('Shippable')),
    ('NO', _('Not Shippable'))
)


def default_dimension_unit():
    val = config_value_safe('PRODUCT', 'MEASUREMENT_SYSTEM', (None, None))[0]
    if val == 'metric':
        return 'cm'
    else:
        return 'in'


def default_weight_unit():
    val = config_value_safe('PRODUCT', 'MEASUREMENT_SYSTEM', (None, None))[0]
    if val == 'metric':
        return 'kg'
    else:
        return 'lb'


class CategoryManager(models.Manager):
    def active(self, **kwargs):
        return self.filter(is_active=True, **kwargs)

    def by_site(self, site=None, **kwargs):
        """Get all categories for this site"""
        if not site:
            site = Site.objects.get_current()

        site = site.id

        return self.active(site__id__exact=site, **kwargs)

    def get_by_site(self, site=None, **kwargs):
        if not site:
            site = Site.objects.get_current()
        return self.active().get(site=site, **kwargs)

    def root_categories(self, site=None, **kwargs):
        """Get all root categories."""

        if not site:
            site = Site.objects.get_current()

        return self.active(parent__isnull=True, site=site, **kwargs)

    def search_by_site(self, keyword, site=None, include_children=False):
        """Search for categories by keyword.
        Note, this does not return a queryset."""

        if not site:
            site = Site.objects.get_current()

        cats = self.active().filter(
            Q(name__icontains=keyword) |
            Q(meta__icontains=keyword) |
            Q(description__icontains=keyword),
            site=site)

        if include_children:
            # get all the children of the categories found
            cats = [cat.get_active_children(include_self=True) for cat in cats]

        # sort properly
        if cats:
            fastsort = [(c.ordering, c.name, c) for c in get_flat_list(cats)]
            fastsort.sort()
            # extract the cat list
            cats = zip(*fastsort)[2]
        return cats


@python_2_unicode_compatible
class Category(models.Model):
    """
    Basic hierarchical category model for storing products
    """
    site = models.ManyToManyField(Site, verbose_name=_('Site'))
    name = models.CharField(_("Name"), max_length=200)
    slug = models.SlugField(_("Slug"), help_text=_("Used for URLs, auto-generated from name if blank"), blank=True)
    parent = models.ForeignKey('self', blank=True, null=True, related_name='child', on_delete=models.SET_NULL)
    meta = models.TextField(_("Meta Description"), blank=True, null=True,
                            help_text=_("Meta description for this category"))
    description = models.TextField(_("Description"), blank=True, help_text="Optional")
    ordering = models.IntegerField(_("Ordering"), default=0, help_text=_("Override alphabetical order in category display"))
    is_active = models.BooleanField(_("Active"), default=True, blank=True)
    related_categories = models.ManyToManyField('self', blank=True, verbose_name=_('Related Categories'))
    objects = CategoryManager()

    @cached_property
    def main_image(self):
        img = False
        images = self.images.order_by('sort')
        if images:
            img = images[0]
        else:
            if self.parent_id and self.parent != self:
                img = self.parent.main_image

        if not img and config_value('PRODUCT', 'SHOW_NO_PHOTO_IN_CATEGORY'):
            # This should be a "Image Not Found" placeholder image
            try:
                img = CategoryImage.objects.filter(category__isnull=True).order_by('sort')[0]
            except IndexError:
                import sys
                print('Warning: default category image not found', file=sys.stderr)
        return img

    def active_products(self, variations=False, include_children=False, **kwargs):
        """Variations determines whether or not product variations are included
        in most templates we are not returning all variations, just the parent product.
        """
        site = Site.objects.get_current()

        if not include_children:
            qry = self.product_set.filter(site=site)
        else:
            cats = self.get_all_children(include_self=True)
            qry = Product.objects.filter(site=site, category__in=cats)

        if variations:
            slugs = qry.filter(site=site, active=True, **kwargs).values_list('slug', flat=True)
            return Product.objects.filter(Q(productvariation__parent__product__slug__in=slugs) | Q(slug__in=slugs)).prefetch_related('productimage_set')
        else:
            return qry.filter(site=site, active=True, productvariation__parent__isnull=True, **kwargs).prefetch_related('productimage_set')

    def translated_attributes(self, language_code=None):
        if not language_code:
            language_code = get_language()
        q = self.categoryattribute_set.filter(languagecode__exact=language_code)
        if q.count() == 0:
            q = self.categoryattribute_set.filter(Q(languagecode__isnull=True) | Q(languagecode__exact=""))
        return q

    def translated_description(self, language_code=None):
        return lookup_translation(self, 'description', language_code)

    def translated_name(self, language_code=None):
        return lookup_translation(self, 'name', language_code)

    def _recurse_for_parents(self, cat_obj):
        p_list = []
        if cat_obj.parent_id:
            p = cat_obj.parent
            p_list.append(p)
            if p != self:
                more = self._recurse_for_parents(p)
                p_list.extend(more)
        if cat_obj == self and p_list:
            p_list.reverse()
        return p_list

    def parents(self):
        return self._recurse_for_parents(self)

    def get_absolute_url(self):
        parents = self._recurse_for_parents(self)
        slug_list = [cat.slug for cat in parents]
        if slug_list:
            slug_list = "/".join(slug_list) + "/"
        else:
            slug_list = ""
        return reverse('satchmo_category', kwargs={'parent_slugs': slug_list, 'slug': self.slug})

    def get_separator(self):
        return ' :: '

    def _parents_repr(self):
        name_list = [cat.name for cat in self._recurse_for_parents(self)]
        return self.get_separator().join(name_list)
    _parents_repr.short_description = "Category parents"

    def get_url_name(self):
        # Get all the absolute URLs and names for use in the site navigation.
        name_list = []
        url_list = []
        for cat in self._recurse_for_parents(self):
            name_list.append(cat.translated_name())
            url_list.append(cat.get_absolute_url())
        name_list.append(self.translated_name())
        url_list.append(self.get_absolute_url())
        return zip(name_list, url_list)

    def __str__(self):
        name_list = [cat.name for cat in self._recurse_for_parents(self)]
        name_list.append(self.name)
        return self.get_separator().join(name_list)

    def save(self, **kwargs):
        if self.id:
            if self.parent and self.parent_id == self.id:
                raise forms.ValidationError(_("You must not save a category in itself!"))

            for p in self._recurse_for_parents(self):
                if self.id == p.id:
                    raise forms.ValidationError(_("You must not save a category in itself!"))

        if not self.slug:
            self.slug = slugify(self.name, instance=self)
        super(Category, self).save(**kwargs)
        for site in self.site.all().only('id'):
            cache_key = "cat-%s" % site.id
            cache.delete(cache_key)

    def _flatten(self, L):
        """
        Taken from a python newsgroup post
        """
        if type(L) != type([]): return [L]
        if L == []: return L
        return self._flatten(L[0]) + self._flatten(L[1:])

    def _recurse_for_children(self, node, only_active=False):
        children = []
        children.append(node)
        for child in node.child.active():
            if child != self:
                if (not only_active) or child.active_products().count() > 0:
                    children_list = self._recurse_for_children(child, only_active=only_active)
                    children.append(children_list)
        return children

    def get_active_children(self, include_self=False):
        """
        Gets a list of all of the children categories which have active products.
        """
        return self.get_all_children(only_active=True, include_self=include_self)

    def get_all_children(self, only_active=False, include_self=False):
        """
        Gets a list of all of the children categories.
        """
        children_list = self._recurse_for_children(self, only_active=only_active)
        if include_self:
            ix = 0
        else:
            ix = 1
        flat_list = self._flatten(children_list[ix:])
        return flat_list

    class Meta:
        ordering = ['parent__ordering', 'parent__name', 'ordering', 'name']
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        # unique_together = ('site', 'slug')


@python_2_unicode_compatible
class CategoryTranslation(models.Model):
    """A specific language translation for a `Category`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    category = models.ForeignKey(Category, related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    name = models.CharField(_("Translated Category Name"), max_length=255, )
    description = models.TextField(_("Description of category"), default='', blank=True)
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Category Translation')
        verbose_name_plural = _('Category Translations')
        ordering = ('category', 'name', 'languagecode')
        unique_together = ('category', 'languagecode', 'version')

    def __str__(self):
        return "CategoryTranslation: [%s] (ver #%i) %s Name: %s" % (self.languagecode, self.version, self.category, self.name)


@python_2_unicode_compatible
class CategoryImage(models.Model):
    """
    A picture of an item.  Can have many pictures associated with an item.
    Thumbnails are automatically created.
    """
    category = models.ForeignKey(Category, null=True, blank=True, related_name="images", on_delete=models.CASCADE)
    picture = ImageWithThumbnailField(verbose_name=_('Picture'),
                                      upload_to="__DYNAMIC__",
                                      name_field="_filename",
                                      max_length=200)  # Media root is automatically prepended
    caption = models.CharField(_("Optional caption"), max_length=100, null=True, blank=True)
    sort = models.IntegerField(_("Sort Order"), default=0)

    def translated_caption(self, language_code=None):
        return lookup_translation(self, 'caption', language_code)

    @cached_property
    def _filename(self):
        if self.category:
            return '%s-%s' % (self.category.slug, self.id)
        else:
            return 'default'

    def __str__(self):
        if self.category:
            return "Image of Category %s" % self.category.slug
        elif self.caption:
            return "Image with caption \"%s\"" % self.caption
        else:
            return "%s" % self.picture

    class Meta:
        ordering = ['sort']
        unique_together = (('category', 'sort'),)
        verbose_name = _("Category Image")
        verbose_name_plural = _("Category Images")


@python_2_unicode_compatible
class CategoryImageTranslation(models.Model):
    """A specific language translation for a `CategoryImage`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    categoryimage = models.ForeignKey(CategoryImage, related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    caption = models.CharField(_("Translated Caption"), max_length=255, )
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Category Image Translation')
        verbose_name_plural = _('Category Image Translations')
        ordering = ('categoryimage', 'caption', 'languagecode')
        unique_together = ('categoryimage', 'languagecode', 'version')

    def __str__(self):
        return "CategoryImageTranslation: [%s] (ver #%i) %s Name: %s" % (self.languagecode, self.version, self.categoryimage, self.name)


class OptionGroupManager(models.Manager):
    def get_sortmap(self):
        """Returns a dictionary mapping ids to sort order"""

        work = {}
        for uid, order in self.values_list('id', 'sort_order'):
            work[uid] = order

        return work


class NullDiscount(object):

    def __init__(self):
        self.description = _("No Discount")
        self.total = Decimal("0.00")
        self.item_discounts = {}
        self.discounted_prices = []
        self.automatic = False

    def calc(self, *args):
        return Decimal("0.00")

    def is_valid(self):
        return False

    def valid_for_product(self, product):
        return False


class DiscountManager(models.Manager):
    def by_code(self, code, raises=False):
        discount = None

        if code:
            try:
                return self.get(code=code, active=True)

            except Discount.DoesNotExist:
                if raises:
                    raise

        return NullDiscount()

    def get_sale(self):
        """Get the current 'sale' discount."""
        today = datetime.date.today()
        sale = None
        site = Site.objects.get_current()
        try:
            sale = keyedcache.cache_get('discount', 'sale', site, today)
        except keyedcache.NotCachedError as nce:
            discs = self.filter(automatic=True,
                                active=True,
                                site=site,
                                startDate__lte=today,
                                endDate__gt=today).order_by('-percentage')
            try:
                sale = discs[0]
            except IndexError:
                pass

            keyedcache.cache_set(nce.key, value=sale)

        if sale is None:
            raise Discount.DoesNotExist
        else:
            return sale


@python_2_unicode_compatible
class Discount(models.Model):
    """
    Allows for multiple types of discounts including % and dollar off.
    Also allows finite number of uses.
    """
    site = models.ManyToManyField(Site, verbose_name=_('site'))
    description = models.CharField(_("Description"), max_length=100)
    code = models.CharField(_("Discount Code"), max_length=20, unique=True, help_text=_("Coupon Code"))
    active = models.BooleanField(_("Active"), default=False)
    amount = CurrencyField(_("Discount Amount"), decimal_places=2, max_digits=8, blank=True, null=True,
                           help_text=_("Enter absolute discount amount OR percentage."))
    percentage = models.DecimalField(_("Discount Percentage"), decimal_places=2, max_digits=5, blank=True, null=True,
                                     help_text=_("Enter absolute discount amount OR percentage.  Percents are given in whole numbers, and can be up to 100%."))
    automatic = models.BooleanField(_("Is this an automatic discount?"), default=False, blank=True, null=True,
                                    help_text=_("Use this field to advertise the discount on all products to which it applies.  Generally this is used for site-wide sales."))
    allowedUses = models.IntegerField(_("Number of allowed uses"), blank=True, null=True,
                                      help_text=_('Set this to a number greater than 0 to have the discount expire after that many uses.'))
    numUses = models.IntegerField(_("Number of times already used"), blank=True, null=True)
    minOrder = CurrencyField(_("Minimum order value"), decimal_places=2, max_digits=8, blank=True, null=True)
    startDate = models.DateField(_("Start Date"))
    endDate = models.DateField(_("End Date"))
    shipping = models.CharField(_("Shipping"), choices=DISCOUNT_SHIPPING_CHOICES, default='NONE', blank=True, null=True, max_length=10)
    allValid = models.BooleanField(_("All products?"), default=False,
                                   help_text=_('Apply this discount to all discountable products? If this is false you must select products below in the "Valid Products" section.'))
    valid_products = models.ManyToManyField('Product', verbose_name=_("Valid Products"), blank=True)
    valid_categories = models.ManyToManyField('Category', verbose_name=_("Valid Categories"), blank=True)

    objects = DiscountManager()

    class Meta:
        verbose_name = _("Discount")
        verbose_name_plural = _("Discounts")

    def __init__(self, *args, **kwargs):
        self._calculated = False
        super(Discount, self).__init__(*args, **kwargs)

    def __str__(self):
        return self.description

    def save(self, **kwargs):
        super(Discount, self).save(**kwargs)
        if self.automatic:
            today = datetime.date.today()
            for site in self.site.all():
                keyedcache.cache_delete('discount', 'sale', site, today)

    def clean(self):
        if self.amount and self.automatic:
            raise forms.ValidationError(_("Automatic discounts may only be percentages"))

    def isValid(self, cart=None, contact=None):
        """
        Make sure this discount still has available uses and is in the current date range.
        If a cart has been populated, validate that it does apply to the products we have selected.
        If this is a "FREECHEAP" discount, then error if the cheapest shipping hasn't been chosen.
        """
        if not self.active:
            return (False, gettext('This coupon is disabled.'))
        if self.startDate > datetime.date.today():
            return (False, gettext('This coupon is not active yet.'))
        if self.endDate < datetime.date.today():
            return (False, gettext('This coupon has expired.'))
        if self.numUses and self.allowedUses and self.allowedUses > 0 and self.numUses >= self.allowedUses:
            return (False, gettext('This discount has exceeded the number of allowed uses.'))

        if cart:
            minOrder = self.minOrder or 0
            if cart.total < minOrder:
                return (False, gettext('This discount only applies to orders of at least %s.' % moneyfmt(minOrder)))

            if not (self.allValid or (len(self._valid_products(cart.cartitem_set)) > 0)):
                return (False, gettext('This discount cannot be applied to the products in your cart.'))

        # last minute check to make sure discount is valid
        success = {'valid': True, 'message': gettext('Valid.')}
        signals.discount_validate.send(
            sender=Discount,
            discount=self,
            cart=cart,
            contact=contact,
            success=success)
        return (success['valid'], success['message'])

    @cached_property
    def _valid_products_in_categories(self):
        slugs = set()
        for cat in Category.objects.filter(id__in=self.valid_categories.values_list('id', flat=True)):
            slugs.update([p.slug for p in cat.active_products(variations=True, include_children=True)])
        return slugs

    def _valid_products(self, item_query):
        slugs_from_cat = self._valid_products_in_categories
        validslugs = self.valid_products.values_list('slug', flat=True)
        itemslugs = item_query.values_list('product__slug', flat=True)
        return ProductPriceLookup.objects.filter(
            Q(discountable=True) & Q(productslug__in=itemslugs),
            Q(productslug__in=validslugs) | Q(productslug__in=slugs_from_cat)
        ).values_list('productslug', flat=True)

    def calc(self, order):
        # Use the order details and the discount specifics to calculate the actual discount
        discounted = {}
        if self.allValid:
            allvalid = True
        else:
            allvalid = False
            validproducts = self._valid_products(order.orderitem_set)

        for lineitem in order.orderitem_set.all():
            lid = lineitem.id
            price = lineitem.line_item_price
            if lineitem.product.is_discountable and (allvalid or lineitem.product.slug in validproducts):
                discounted[lid] = price
        signals.discount_filter_items.send(
            sender=self,
            discounted=discounted,
            order=order
        )

        if not self.shipping:
            self.shipping = "NONE"
            self.save()

        if self.shipping == "APPLY":
            shipcost = order.shipping_cost
            discounted['Shipping'] = shipcost

        if self.amount:
            # perform a flat rate discount, applying evenly to all items
            # in cart
            discounted = Discount.apply_even_split(discounted, self.amount)

        elif self.percentage:
            discounted = Discount.apply_percentage(discounted, self.percentage)

        else:
            # no discount, probably shipping-only
            zero = Decimal("0.00")
            for key in discounted.keys():
                discounted[key] = zero

        if self.shipping in ('FREE', 'FREECHEAP'):
            shipcost = order.shipping_cost
            discounted['Shipping'] = shipcost

        self._item_discounts = discounted
        self._calculated = True

    @cached_property
    def total(self):
        assert(self._calculated)
        return reduce(operator.add, self.item_discounts.values())

    @cached_property
    def item_discounts(self):
        """Get the dictionary of orderitem -> discounts."""
        assert(self._calculated)
        return self._item_discounts

    @cached_property
    def percentage_text(self):
        """Get the human readable form of the sale percentage."""
        return "%d%%" % self.percentage if self.percentage else self.amount

    def valid_for_product(self, product):
        """Tests if discount is valid for a single product"""
        if not product.is_discountable:
            return False
        elif self.allValid:
            return True
        p = self.valid_products.filter(id__exact=product.id)
        return p.exists() or (product.slug in self._valid_products_in_categories)

    def apply_even_split(cls, discounted, amount):
        """Splits ``amount`` to the most even values,
        but none of them is greater then the value in the dict ``discounted``.
        > > > cls.apply_even_split({1: Decimal('3.00'), 2: Decimal('8.00'), 3: Decimal('9.00')}, Decimal('10.00'))
        {1: Decimal('3.00'), 2: Decimal('3.50'), 3: Decimal('3.50')}
        """
        context = Context(rounding=ROUND_FLOOR)
        eps = Decimal('0.01')
        zero = 0 * eps
        amount = context.quantize(amount, eps)
        lastct = None
        ct = sentinel = len(discounted)
        work = {}
        applied = delta = zero
        # "eps"     : precision, rounding of every input and the smallest increment for splitting of remainder
        # "ct"      : how many item from the previous round can be splitted even from the previous round
        # "applied" : how much has been applied total in the previous round
        # "delta"   : how much has been applied for limited values in the previous round

        while ct > 0 and applied < amount and ct != lastct and sentinel:
            split_discount = context.quantize((amount - delta) / ct, eps)
            remainder = amount - delta - split_discount * ct
            lastct = ct

            ct = len(discounted)
            work = {}
            applied = delta = zero
            for lid, price in discounted.items():
                if price > split_discount:
                    if remainder:
                        to_apply = split_discount + eps
                        remainder -= eps
                    else:
                        to_apply = split_discount
                else:
                    to_apply = context.quantize(price, eps)
                    delta += to_apply
                    ct -= 1
                work[lid] = to_apply
                applied += to_apply
            sentinel -= 1

        assert sentinel >= 0, "Infinite loop in 'apply_even_split'"
        assert applied == amount or applied <= amount and applied == delta, "Internal error in 'apply_even_split'"
        round_cents(work)
        return work

    apply_even_split = classmethod(apply_even_split)

    def apply_percentage(cls, discounted, percentage):
        work = {}

        for lid, price in discounted.items():
            work[lid] = price * percentage / 100
        round_cents(work)
        return work

    apply_percentage = classmethod(apply_percentage)


@python_2_unicode_compatible
class OptionGroup(models.Model):
    """
    A set of options that can be applied to an item.
    Examples - Size, Color, Shape, etc
    """
    site = models.ManyToManyField(Site, verbose_name=_('Site'))
    name = models.CharField(_("Name of Option Group"), max_length=50,
                            help_text=_("This will be the text displayed on the product page."))
    description = models.CharField(_("Detailed Description"), max_length=100, blank=True,
                                   help_text=_("Further description of this group (i.e. shirt size vs shoe size)."))
    sort_order = models.IntegerField(_("Sort Order"), default=0,
                                     help_text=_("The display order for this group."))

    objects = OptionGroupManager()

    def translated_description(self, language_code=None):
        return lookup_translation(self, 'description', language_code)

    def translated_name(self, language_code=None):
        return lookup_translation(self, 'name', language_code)

    def __str__(self):
        if self.description:
            return "%s - %s" % (self.name, self.description)
        else:
            return self.name

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _("Option Group")
        verbose_name_plural = _("Option Groups")


@python_2_unicode_compatible
class OptionGroupTranslation(models.Model):
    """A specific language translation for an `OptionGroup`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    optiongroup = models.ForeignKey(OptionGroup, related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    name = models.CharField(_("Translated OptionGroup Name"), max_length=255, )
    description = models.TextField(_("Description of OptionGroup"), default='', blank=True)
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Option Group Translation')
        verbose_name_plural = _('Option Groups Translations')
        ordering = ('optiongroup', 'name', 'languagecode')
        unique_together = ('optiongroup', 'languagecode', 'version')

    def __str__(self):
        return "OptionGroupTranslation: [%s] (ver #%i) %s Name: %s" % (self.languagecode, self.version, self.optiongroup, self.name)


class OptionManager(models.Manager):
    def from_unique_id(self, unique_id):
        group_id, option_value = split_option_unique_id(unique_id)
        group = OptionGroup.objects.get(id=group_id)
        return Option.objects.get(option_group=group_id, value=option_value)


@python_2_unicode_compatible
class Option(models.Model):
    """
    These are the actual items in an OptionGroup.  If the OptionGroup is Size, then an Option
    would be Small.
    """
    objects = OptionManager()
    option_group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE)
    name = models.CharField(_("Display value"), max_length=50, )
    value = models.CharField(_("Stored value"), max_length=50)
    price_change = CurrencyField(_("Price Change"), null=True, blank=True, max_digits=14, decimal_places=6,
                                 help_text=_("This is the price differential for this option."))
    sort_order = models.IntegerField(_("Sort Order"), default=0)

    def translated_name(self, language_code=None):
        return lookup_translation(self, 'name', language_code)

    class Meta:
        ordering = ('option_group', 'sort_order', 'name')
        unique_together = (('option_group', 'value'),)
        verbose_name = _("Option Item")
        verbose_name_plural = _("Option Items")

    def _get_unique_id(self):
        return make_option_unique_id(self.option_group_id, self.value)
    unique_id = property(_get_unique_id)

    def __repr__(self):
        return "<Option: %s>" % repr(self.name)

    def __str__(self):
        return '%s: %s' % (self.option_group.name, self.name)


@python_2_unicode_compatible
class OptionTranslation(models.Model):
    """A specific language translation for an `Option`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    option = models.ForeignKey(Option, related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    name = models.CharField(_("Translated Option Name"), max_length=255, )
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Option Translation')
        verbose_name_plural = _('Option Translations')
        ordering = ('option', 'name', 'languagecode')
        unique_together = ('option', 'languagecode', 'version')

    def __str__(self):
        return "OptionTranslation: [%s] (ver #%i) %s Name: %s" % (self.languagecode, self.version, self.option, self.name)


class ProductManager(models.Manager):

    def active(self, variations=True, **kwargs):
        if not variations:
            kwargs['productvariation__parent__isnull'] = True
        return self.filter(active=True, **kwargs)

    def active_by_site(self, variations=True, **kwargs):
        return self.by_site(active=True, variations=variations, **kwargs)

    def by_site(self, site=None, variations=True, **kwargs):
        if not site:
            site = Site.objects.get_current()

        site = site.id

        # log.debug("by_site: site=%s", site)
        if not variations:
            kwargs['productvariation__parent__isnull'] = True
        return self.filter(site__id__exact=site, **kwargs)

    def featured_by_site(self, site=None, **kwargs):
        return self.by_site(site=site, active=True, featured=True, **kwargs)

    def get_by_site(self, site=None, **kwargs):
        if not site:
            site = Site.objects.get_current()
        return self.get(site=site, **kwargs)

    def recent_by_site(self, **kwargs):
        query = self.active_by_site(**kwargs)
        if query.count() == 0:
            query = self.active_by_site()

        query = query.order_by('-date_added', '-id')
        return query


def get_taxable():
    return config_value('TAX', 'PRODUCTS_TAXABLE_BY_DEFAULT')


@python_2_unicode_compatible
class Product(models.Model):
    """
    Root class for all Products
    """
    site = models.ManyToManyField(Site, verbose_name=_('Site'))
    name = models.CharField(_("Full Name"), max_length=255, blank=False,
                            help_text=_("This is what the product will be called in the default site language.  To add non-default translations, use the Product Translation section below."))
    slug = models.SlugField(_("Slug Name"), blank=True, max_length=255,
                            help_text=_("Used for URLs, auto-generated from name if blank"))
    sku = models.CharField(_("SKU"), max_length=255, blank=True, null=True,
                           help_text=_("Defaults to slug if left blank"))
    short_description = models.TextField(_("Short description of product"), help_text=_("This should be a 1 or 2 line description in the default site language for use in product listing screens"), default='', blank=True)
    description = models.TextField(_("Description of product"), help_text=_("This field can contain HTML and should be a few paragraphs in the default site language explaining the background of the product, and anything that would help the potential customer make their purchase."), default='', blank=True)
    category = models.ManyToManyField(Category, blank=True, verbose_name=_("Category"))
    items_in_stock = models.DecimalField(_("Number in stock"), max_digits=18, decimal_places=6, default='0')
    meta = models.TextField(_("Meta Description"), max_length=200, blank=True, null=True, help_text=_("Meta description for this product"))
    date_added = models.DateField(_("Date added"), null=True, blank=True)
    active = models.BooleanField(_("Active"), default=True, help_text=_("This will determine whether or not this product will appear on the site"))
    featured = models.BooleanField(_("Featured"), default=False, help_text=_("Featured items will show on the front page"))
    ordering = models.IntegerField(_("Ordering"), default=0, help_text=_("Override alphabetical order in category display"))
    weight = models.DecimalField(_("Weight"), max_digits=8, decimal_places=2, null=True, blank=True)
    weight_units = models.CharField(_("Weight units"), max_length=3, null=True, blank=True)
    length = models.DecimalField(_("Length"), max_digits=6, decimal_places=2, null=True, blank=True)
    length_units = models.CharField(_("Length units"), max_length=3, null=True, blank=True)
    width = models.DecimalField(_("Width"), max_digits=6, decimal_places=2, null=True, blank=True)
    width_units = models.CharField(_("Width units"), max_length=3, null=True, blank=True)
    height = models.DecimalField(_("Height"), max_digits=6, decimal_places=2, null=True, blank=True)
    height_units = models.CharField(_("Height units"), max_length=3, null=True, blank=True)
    related_items = models.ManyToManyField('self', blank=True, verbose_name=_('Related Items'))
    also_purchased = models.ManyToManyField('self', blank=True, verbose_name=_('Previously Purchased'))
    total_sold = models.DecimalField(_("Total sold"), max_digits=18, decimal_places=6, default='0')
    taxable = models.BooleanField(_("Taxable"), default=get_taxable)
    taxClass = models.ForeignKey('TaxClass', verbose_name=_('Tax Class'), blank=True, null=True, help_text=_("If it is taxable, what kind of tax?"), on_delete=models.SET_NULL)
    shipclass = models.CharField(_('Shipping'), choices=SHIP_CLASS_CHOICES, default="DEFAULT", max_length=10,
                                 help_text=_("If this is 'Default', then we'll use the product type to determine if it is shippable."))

    objects = ProductManager()

    @cached_property
    def main_category(self):
        """Return the first category for the product"""
        try:
            return self.category.all()[0]
        except IndexError:
            return None

    @cached_property
    def main_image(self):
        img = False
        try:
            img = self.productimage_set.order_by('sort')[0]
        except IndexError:
            # try to get a main image by looking at the parent if this has one
            p = self.get_subtype_with_attr('parent', 'product')
            if p:
                img = p.parent.product.main_image

        if not img:
            # This should be a "Image Not Found" placeholder image
            try:
                img = ProductImage.objects.filter(product__isnull=True).order_by('sort')[0]
            except IndexError:
                import sys
                print('Warning: default product image not found - try syncdb', file=sys.stderr)

        return img

    def _is_discountable(self):
        p = self.get_subtype_with_attr('discountable')
        if p:
            return p.discountable
        else:
            return True

    is_discountable = property(_is_discountable)

    def translated_attributes(self, language_code=None):
        if not language_code:
            language_code = get_language()
        q = self.productattribute_set.filter(languagecode__exact=language_code)
        if not q.exists():
            q = self.productattribute_set.filter(Q(languagecode__isnull=True) | Q(languagecode__exact=""))
        return q

    def translated_description(self, language_code=None):
        return lookup_translation(self, 'description', language_code)

    def translated_name(self, language_code=None):
        return lookup_translation(self, 'name', language_code)

    def translated_short_description(self, language_code=None):
        return lookup_translation(self, 'short_description', language_code)

    def _get_fullPrice(self):
        """
        returns price as a Decimal
        """

        subtype = self.get_subtype_with_attr('unit_price')

        if subtype and subtype is not self:
            price = subtype.unit_price
        else:
            price = get_product_quantity_price(self, Decimal('1'))

        if not price:
            price = Decimal("0.00")
        return price

    unit_price = property(_get_fullPrice)

    def get_qty_price(self, qty, include_discount=True):
        """
        If QTY_DISCOUNT prices are specified, then return the appropriate discount price for
        the specified qty.  Otherwise, return the unit_price
        returns price as a Decimal
        """
        subtype = self.get_subtype_with_attr('get_qty_price')
        if subtype and subtype is not self:
            price = subtype.get_qty_price(qty, include_discount=include_discount)

        else:
            if include_discount:
                price = get_product_quantity_price(self, qty)
            else:
                adjustment = get_product_quantity_adjustments(self, qty)
                if adjustment.price is not None:
                    price = adjustment.price.price
                else:
                    price = None
            if not price:
                price = self._get_fullPrice()

        return price

    def get_qty_price_list(self):
        """Return a list of tuples (qty, price)"""
        prices = Price.objects.filter(
            product__id=self.id).exclude(
            expires__isnull=False,
            expires__lt=datetime.date.today()
        ).select_related()
        return [(price.quantity, price.dynamic_price) for price in prices]

    def in_stock(self):
        subtype = self.get_subtype_with_attr('in_stock')
        if subtype and subtype is not self:
            return subtype.in_stock

        return self.items_in_stock > 0

    @cached_property
    def has_full_dimensions(self):
        """Return true if the dimensions all have units and values. Used in shipping calcs. """
        for att in ('length', 'length_units', 'width', 'width_units', 'height', 'height_units'):
            if self.smart_attr(att) is None:
                return False
        return True

    @cached_property
    def has_full_weight(self):
        """Return True if we have weight and weight units"""
        for att in ('weight', 'weight_units'):
            if self.smart_attr(att) is None:
                return False
        return True

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('satchmo_product', kwargs={'product_slug': self.slug})

    class Meta:
        ordering = ('ordering', 'name')
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        # unique_together = (('site', 'sku'),('site','slug'))

    def save(self, **kwargs):
        if not self.pk:
            self.date_added = datetime.date.today()

        if self.name and not self.slug:
            self.slug = slugify(self.name, instance=self)

        if not self.sku:
            self.sku = self.slug
        super(Product, self).save(**kwargs)
        ProductPriceLookup.objects.smart_create_for_product(self)

    def get_subtypes(self):
        # If we've already computed it once, let's not do it again.
        # This is a performance speedup.
        if hasattr(self, "_sub_types"):
            return self._sub_types
        types = []
        try:
            for module, subtype in active_product_types():
                try:
                    subclass = getattr(self, subtype.lower())
                    if subclass is not None:
                        gettype = getattr(subclass, '_get_subtype')
                        subtype = gettype()
                        if subtype not in types:
                            types.append(subtype)
                except models.ObjectDoesNotExist:
                    pass
        except SettingNotSet:
            log.warn("Error getting subtypes, OK if in SyncDB")

        self._sub_types = tuple(types)
        return self._sub_types

    get_subtypes.short_description = _("Product Subtypes")

    def get_subtype_with_attr(self, *args):
        """Get a subtype with the specified attributes.  Note that this can be chained
        so that you can ensure that the attribute then must have the specified attributes itself.

        example:  get_subtype_with_attr('parent') = any parent
        example:  get_subtype_with_attr('parent', 'product') = any parent which has a product attribute
        """
        for subtype_name in self.get_subtypes():
            subtype = getattr(self, subtype_name.lower())
            if hasattr(subtype, args[0]):
                if len(args) == 1:
                    return subtype
                else:
                    found = True
                    for attr in args[1:-1]:
                        if hasattr(subtype, attr):
                            subtype = getattr(self, attr)
                        else:
                            found = False
                            break
                    if found and hasattr(subtype, args[-1]):
                        return subtype

        return None

    def smart_attr(self, attr):
        """Retrieve an attribute, or its parent's attribute if it is null or blank.
        Ex: to get a weight.  obj.smart_attr('weight')"""

        val = getattr(self, attr)
        if val is None or val == "":
            for subtype_name in self.get_subtypes():
                subtype = getattr(self, subtype_name.lower())

                if hasattr(subtype, 'parent'):
                    subtype = subtype.parent.product

                if hasattr(subtype, attr):
                    val = getattr(subtype, attr)
                    if val is not None:
                        break
        return val

    def smart_relation(self, relation):
        """Retrieve a relation, or its parent's relation if the relation count is 0"""
        q = getattr(self, relation)
        if q.count() > 0:
            return q

        for subtype_name in self.get_subtypes():
            subtype = getattr(self, subtype_name.lower())

            if hasattr(subtype, 'parent'):
                subtype = subtype.parent.product

                return getattr(subtype, relation)

    @cached_property
    def has_variants(self):
        subtype = self.get_subtype_with_attr('has_variants')
        return subtype and subtype.has_variants

    @cached_property
    def get_category(self):
        """
        Return the primary category associated with this product
        """
        subtype = self.get_subtype_with_attr('get_category')
        if subtype and subtype is not self:
            return subtype.get_category

        try:
            return self.category.all()[0]
        except IndexError:
            return None

    @cached_property
    def is_downloadable(self):
        """
        If this Product has any subtypes associated with it that are downloadable, then
        consider it downloadable
        """
        return self.get_subtype_with_attr('is_downloadable') is not None

    @cached_property
    def is_subscription(self):
        """
        If this Product has any subtypes associated with it that are subscriptions, then
        consider it subscription based.
        """
        for prod_type in self.get_subtypes():
            subtype = getattr(self, prod_type.lower())
            if hasattr(subtype, 'is_subscription'):
                return subtype.is_subscription
        return False

    @cached_property
    def is_shippable(self):
        """
        If this Product has any subtypes associated with it that are not
        shippable, then consider the product not shippable.
        If it is downloadable, then we don't ship it either.
        """
        if self.shipclass == "DEFAULT":
            subtype = self.get_subtype_with_attr('is_shippable')
            if subtype and subtype is not self and not subtype.is_shippable:
                return False
            return True
        elif self.shipclass == "YES":
            return True
        else:
            return False

    def add_template_context(self, context, *args, **kwargs):
        """
        Add context for the product template.
        Call the add_template_context method of each subtype and return the
        combined context.
        """
        subtypes = self.get_subtypes()
        logging.debug('subtypes = %s', subtypes)
        for subtype_name in subtypes:
            subtype = getattr(self, subtype_name.lower())
            if subtype == self:
                continue
            if hasattr(subtype, 'add_template_context'):
                context = subtype.add_template_context(context, *args, **kwargs)

        return context


@python_2_unicode_compatible
class ProductTranslation(models.Model):
    """A specific language translation for a `Product`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    product = models.ForeignKey('Product', related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    name = models.CharField(_("Full Name"), max_length=255)
    description = models.TextField(_("Description of product"), help_text=_("This field can contain HTML and should be a few paragraphs explaining the background of the product, and anything that would help the potential customer make their purchase."), default='', blank=True)
    short_description = models.TextField(_("Short description of product"), help_text=_("This should be a 1 or 2 line description for use in product listing screens"), max_length=200, default='', blank=True)
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Product Translation')
        verbose_name_plural = _('Product Translations')
        ordering = ('product', 'name', 'languagecode')
        unique_together = ('product', 'languagecode', 'version')

    def __str__(self):
        return "ProductTranslation: [%s] (ver #%i) %s Name: %s" % (self.languagecode, self.version, self.product, self.name)


# class BundledProduct(models.Model):
#     """
#     This type of Product is a group of products that are sold as a set
#     NOTE: This doesn't do anything yet - it's just an example
#     """
#     product = models.OneToOneField(Product)
#     members = models.ManyToManyField(Product, related_name='parent_productgroup_set')


class ProductPriceLookupManager(models.Manager):

    def by_product(self, product):
        return self.get(productslug=product.slug)

    def delete_expired(self):
        for p in self.filter(expires__lt=datetime.date.today()):
            p.delete()

    def create_for_product(self, product):
        """Create a set of lookup objects for all priced quantities of the Product"""

        self.delete_for_product(product)
        pricelist = product.get_qty_price_list()

        objs = []
        for qty, price in pricelist:
            for site in product.site.all():
                obj = ProductPriceLookup(productslug=product.slug,
                                         siteid=site.pk,
                                         active=product.active,
                                         price=price,
                                         quantity=qty,
                                         discountable=product.is_discountable,
                                         items_in_stock=product.items_in_stock)
                                         # productimage_set=product.productimage_set)
                obj.save()
                objs.append(obj)
        return objs

    def create_for_configurableproduct(self, configproduct):
        """Create a set of lookup objects for all variations of this product"""

        objs = self.create_for_product(configproduct)
        for pv in configproduct.configurableproduct.productvariation_set.filter(product__active='1'):
            objs.extend(self.create_for_variation(pv, configproduct))

        return objs

    def create_for_variation(self, variation, parent):

        product = variation.product

        self.delete_for_product(product)
        pricelist = variation.get_qty_price_list()

        objs = []
        for qty, price in pricelist:
            for site in product.site.all():
                obj = ProductPriceLookup(productslug=product.slug,
                                         parentid=parent.pk,
                                         siteid=site.pk,
                                         active=product.active,
                                         price=price,
                                         quantity=qty,
                                         key=variation.optionkey,
                                         discountable=product.is_discountable,
                                         items_in_stock=product.items_in_stock)
                obj.save()
                objs.append(obj)
        return objs

    def delete_for_product(self, product):
        for obj in self.filter(productslug=product.slug, siteid__in=list(product.site.all().values_list('pk', flat=True))):
            obj.delete()

    def rebuild_all(self, site=None):
        if not site:
            site = Site.objects.get_current()

        for lookup in self.filter(siteid=site.id):
            lookup.delete()

        ct = 0
        log.debug('ProductPriceLookup rebuilding all pricing')
        for p in Product.objects.active_by_site(site=site, variations=False):
            prices = self.smart_create_for_product(p)
            ct += len(prices)
        log.info('ProductPriceLookup built %i prices', ct)

    def smart_create_for_product(self, product):
        subtypes = product.get_subtypes()
        if 'ConfigurableProduct' in subtypes:
            return self.create_for_configurableproduct(product)
        elif 'ProductVariation' in subtypes:
            return self.create_for_variation(product.productvariation, product.productvariation.parent)
        else:
            return self.create_for_product(product)


class ProductPriceLookup(models.Model):
    """
    A denormalized object, used to quickly provide
    details needed for productvariation display, without way too many database hits.
    """
    siteid = models.IntegerField()
    key = models.CharField(max_length=60, null=True)
    parentid = models.IntegerField(null=True)
    productslug = models.CharField(max_length=255, db_index=True)
    price = models.DecimalField(max_digits=14, decimal_places=6)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    active = models.BooleanField(default=False)
    discountable = models.BooleanField(default=False)
    items_in_stock = models.DecimalField(max_digits=18, decimal_places=6)

    objects = ProductPriceLookupManager()

    @cached_property
    def product(self):
        return Product.objects.get(slug=self.productslug, site__id=self.siteid)

    @cached_property
    def productimage_set(self):
        try:
            return ProductImage.objects.filter(product=self.product)
        except ObjectDoesNotExist:
            pass
        return None

    @cached_property
    def dynamic_price(self):
        """Get the current price as modified by all listeners."""
        adjust = PriceAdjustmentCalc(self)
        signals.satchmo_price_query.send(self, adjustment=adjust, slug=self.productslug, discountable=self.discountable)
        self.price = adjust.final_price()
        return self.price


# Support the user's setting of custom expressions in the settings.py file
try:
    user_validations = settings.SATCHMO_SETTINGS.get('ATTRIBUTE_VALIDATIONS')
except:
    user_validations = None


VALIDATIONS = [
    ('product.utils.validation_simple', _('One or more characters')),
    ('product.utils.validation_integer', _('Integer number')),
    ('product.utils.validation_yesno', _('Yes or No')),
    ('product.utils.validation_decimal', _('Decimal number')),
]
if user_validations:
    VALIDATIONS.extend(user_validations)


@python_2_unicode_compatible
class AttributeOption(models.Model):
    """
    Allows arbitrary name/value pairs to be attached to a product.
    By defining the list, the user will be presented with a predefined
    list of attributes instead of a free form field.
    The validation field should contain a regular expression that can be
    used to validate the structure of the input.
    Possible usage for a book:
    ISBN, Pages, Author, etc
    """
    description = models.CharField(_("Description"), max_length=100)
    name = models.SlugField(_("Attribute name"), max_length=100)
    validation = models.CharField(_("Field Validations"), choices=VALIDATIONS, max_length=100)
    sort_order = models.IntegerField(_("Sort Order"), default=1)
    error_message = models.CharField(_("Error Message"), default=_("Invalid Entry"), max_length=100)

    class Meta:
        ordering = ('sort_order',)

    def __str__(self):
        return self.description


@python_2_unicode_compatible
class ProductAttribute(models.Model):
    """
    Allows arbitrary name/value pairs (as strings) to be attached to a product.
    This is a simple way to add extra text or numeric info to a product.
    If you want more structure than this, create your own subtype to add
    whatever you want to your Products.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES, null=True, blank=True)
    option = models.ForeignKey(AttributeOption, on_delete=models.CASCADE)
    value = models.CharField(_("Value"), max_length=255)

    @cached_property
    def name(self):
        return self.option.name

    @cached_property
    def description(self):
        return self.option.description

    class Meta:
        verbose_name = _("Product Attribute")
        verbose_name_plural = _("Product Attributes")
        ordering = ('option__sort_order',)

    def __str__(self):
        return self.option.name


@python_2_unicode_compatible
class CategoryAttribute(models.Model):
    """
    Similar to ProductAttribute, except that this is for categories.
    """
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES, null=True, blank=True)
    option = models.ForeignKey(AttributeOption, on_delete=models.CASCADE)
    value = models.CharField(_("Value"), max_length=255)

    @cached_property
    def name(self):
        return self.option.name

    @cached_property
    def description(self):
        return self.option.description

    class Meta:
        verbose_name = _("Category Attribute")
        verbose_name_plural = _("Category Attributes")
        ordering = ('option__sort_order',)

    def __str__(self):
        return self.option.name


@python_2_unicode_compatible
class Price(models.Model):
    """
    A Price!
    Separating it out lets us have different prices for the same product for different purposes.
    For example for quantity discounts.
    The current price should be the one with the earliest expires date, and the highest quantity
    that's still below the user specified (IE: ordered) quantity, that matches a given product.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    price = CurrencyField(_("Price"), max_digits=14, decimal_places=6, )
    quantity = models.DecimalField(_("Discount Quantity"), max_digits=18, decimal_places=6, default='1.0',
                                   help_text=_("Use this price only for this quantity or higher"))
    expires = models.DateField(_("Expires"), null=True, blank=True)
    # TODO: add fields here for locale/currency specific pricing

    def __str__(self):
        return six.text_type(self.price)

    def adjustments(self, product=None):
        """Get a list of price adjustments, in the form of a PriceAdjustmentCalc
        object. Optionally, provide a pre-fetched product to avoid the foreign
        key lookup of the `product' attribute.
        """
        if product is None:
            product = self.product
        adjust = PriceAdjustmentCalc(self, product)
        signals.satchmo_price_query.send(self, adjustment=adjust, slug=product.slug, discountable=product.is_discountable)
        return adjust

    @cached_property
    def dynamic_price(self):
        """Get the current price as modified by all listeners."""

        adjustment = self.adjustments()
        return adjustment.final_price()

    def save(self, **kwargs):
        prices = Price.objects.filter(product=self.product, quantity=self.quantity)
        # Jump through some extra hoops to check expires - if there's a better way to handle this field I can't think of it. Expires needs to be able to be set to None in cases where there is no expiration date.
        if self.expires:
            prices = prices.filter(expires=self.expires)
        else:
            prices = prices.filter(expires__isnull=True)
        if self.id:
            prices = prices.exclude(id=self.id)
        if prices.count():
            return  # Duplicate Price

        super(Price, self).save(**kwargs)
        ProductPriceLookup.objects.smart_create_for_product(self.product)

    class Meta:
        ordering = ['expires', '-quantity']
        verbose_name = _("Price")
        verbose_name_plural = _("Prices")
        unique_together = (("product", "quantity", "expires"),)


@python_2_unicode_compatible
class ProductImage(models.Model):
    """
    A picture of an item.  Can have many pictures associated with an item.
    Thumbnails are automatically created.
    """
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE)
    picture = ImageWithThumbnailField(verbose_name=_('Picture'),
                                      upload_to="__DYNAMIC__",
                                      name_field="_filename",
                                      max_length=200)  # Media root is automatically prepended
    caption = models.CharField(_("Optional caption"), max_length=100, null=True, blank=True)
    sort = models.IntegerField(_("Sort Order"), default=0)

    def translated_caption(self, language_code=None):
        return lookup_translation(self, 'caption', language_code)

    @cached_property
    def _filename(self):
        if self.product:
            # In some cases the name could be too long to fit into the field
            # Truncate it if this is the case
            pic_field_max_length = self._meta.get_field('picture').max_length
            max_slug_length = pic_field_max_length - len('images/productimage-picture-.jpg') - len(str(self.id))
            slug = self.product.slug[:max_slug_length]
            return '%s-%s' % (slug, self.id)
        else:
            return 'default'

    def __str__(self):
        if self.product:
            return "Image of Product %s" % self.product.slug
        elif self.caption:
            return "Image with caption \"%s\"" % self.caption
        else:
            return "%s" % self.picture

    class Meta:
        ordering = ['sort']
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")


@python_2_unicode_compatible
class ProductImageTranslation(models.Model):
    """A specific language translation for a `ProductImage`.  This is intended for all descriptions which are not the
    default settings.LANGUAGE.
    """
    productimage = models.ForeignKey(ProductImage, related_name="translations", on_delete=models.CASCADE)
    languagecode = models.CharField(_('language'), max_length=10, choices=settings.LANGUAGES)
    caption = models.CharField(_("Translated Caption"), max_length=255, )
    version = models.IntegerField(_('version'), default=1)
    active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name = _('Product Image Translation')
        verbose_name_plural = _('Product Image Translations')
        ordering = ('productimage', 'caption', 'languagecode')
        unique_together = ('productimage', 'languagecode', 'version')

    def __str__(self):
        return "ProductImageTranslation: [%s] (ver #%i) %s" % (self.languagecode, self.version, self.productimage)


@python_2_unicode_compatible
class TaxClass(models.Model):
    """
    Type of tax that can be applied to a product.  Tax
    might vary based on the type of product.  In the US, clothing could be
    taxed at a different rate than food items.
    """
    title = models.CharField(_("Title"), max_length=20,
                             help_text=_("Displayed title of this tax."))
    description = models.CharField(_("Description"), max_length=30,
                                   help_text=_("Description of products that would be taxed."))

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _("Tax Class")
        verbose_name_plural = _("Tax Classes")


def make_option_unique_id(groupid, value):
    return '%s-%s' % (smart_str(groupid), smart_str(value),)


def round_cents(work):
    cents = Decimal("0.01")
    for lid in work:
        work[lid] = work[lid].quantize(cents)


def split_option_unique_id(uid):
    "reverse of make_option_unique_id"

    parts = uid.split('-')
    return (parts[0], '-'.join(parts[1:]))
