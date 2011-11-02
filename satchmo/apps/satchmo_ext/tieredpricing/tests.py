from decimal import Decimal
from django.contrib.auth.models import User, Group
from django.test import TestCase
from product.models import Product, Price
from satchmo_ext.tieredpricing.models import *
from threaded_multihost.threadlocals import set_current_user, set_thread_variable
import keyedcache

class TieredTest(TestCase):
    """Test Tiered Pricing"""
    fixtures = ['l10n-data.yaml','sample-store-data.yaml', 'products.yaml', 'test-config.yaml']

    def setUp(self):
        keyedcache.cache_delete()
        # remove users stored by previous requests into threadlocals
        set_thread_variable('request', None)
        tieruser = User.objects.create_user('timmy', 'timmy@example.com', '12345')
        stduser = User.objects.create_user('tommy', 'tommy@example.com', '12345')
        tieruser.save()
        stduser.save()
        self.tieruser = tieruser
        self.stduser = stduser
        tiergroup = Group(name="tiertest")
        tiergroup.save()
        tieruser.groups.add(tiergroup)
        tieruser.save()
        self.tier = PricingTier(group=tiergroup, title="Test Tier", discount_percent=Decimal('10.0'))
        self.tier.save()

    def tearDown(self):
        keyedcache.cache_delete()

    def test_simple_tier(self):
        """Check quantity price for a standard product using the default price"""
        product = Product.objects.get(slug='PY-Rocks')
        set_current_user(None)
        self.assertEqual(product.unit_price, Decimal("19.50"))

    def test_tiered_user(self):
        """Test that a tiered user gets the tiered price"""
        product = Product.objects.get(slug='PY-Rocks')
        set_current_user(self.tieruser)
        self.assertEqual(product.unit_price, Decimal("17.550"))

    def test_no_tier_user(self):
        """Check price when user doesn't have a tier"""
        product = Product.objects.get(slug='PY-Rocks')
        set_current_user(self.stduser)
        self.assertEqual(product.unit_price, Decimal("19.50"))

    def test_tieredprice(self):
        """Test setting an explicit tieredprice on a product"""
        product = Product.objects.get(slug='PY-Rocks')
        tp = TieredPrice(product=product, pricingtier=self.tier, quantity='1', price=Decimal('10.00'))
        tp.save()
        set_current_user(self.tieruser)
        self.assertEqual(product.unit_price, Decimal("10.00"))

    def test_tieredprice_no_tier_user(self):
        """Test setting an explicit tieredprice on a product, but no tier for user"""
        product = Product.objects.get(slug='PY-Rocks')
        tp = TieredPrice(product=product, pricingtier=self.tier, quantity='1', price=Decimal('5.00'))
        tp.save()
        set_current_user(self.stduser)
        self.assertEqual(product.unit_price, Decimal("19.50"))

    def test_tiered_user_dynamic_update(self):
        """
        Test that adding a user to tiered group or removing him is reflected immediately
        (without waiting for server restart)
        """
        product = Product.objects.get(slug='PY-Rocks')
        set_current_user(self.tieruser)
        _ = product.unit_price
        tiergroup = Group.objects.get(name="tiertest")
        self.tieruser.groups.remove(tiergroup)
        self.assertEqual(product.unit_price, Decimal("19.50"))
        self.tieruser.groups.add(tiergroup)
        self.assertEqual(product.unit_price, Decimal("17.550"))
        tiergroup.user_set.clear()
        self.assertEqual(product.unit_price, Decimal("19.50"))

