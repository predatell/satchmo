import urllib
import stripe
import datetime

from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from satchmo_store.contact.models import Contact
from payment.modules.base import BasePaymentProcessor, ProcessorResult
from payment.modules.stripe.forms import StripePaymentForm

FORM = StripePaymentForm


class PaymentProcessor(BasePaymentProcessor):
    """
    Authorize.NET payment processing module
    You must have an account with authorize.net in order to use this module.

    Additionally, you must have ARB enabled in your account to use recurring billing.
    """

    def __init__(self, settings):
        super(PaymentProcessor, self).__init__('stripe', settings)
        self.stripe = stripe
        self.search_stripe_version = "2020-08-27"

        if settings.LIVE.value:
            security_key = settings.TRANKEY.value
        else:
            security_key = settings.TEST_TRANKEY.value
        self.stripe.api_key = security_key

        try:
            from djstripe import models
            self.dj_models = models
        except ImportError:
            self.dj_models = False

        self.customer_id = None
        self.card_token = None

    def can_recur_bill(self):
        return True

    def capture_payment(self, testing=False, order=None, amount=None):
        """Process payments without an authorization step."""
        if order:
            self.prepare_data(order)
        else:
            order = self.order

        # recurlist = self.get_recurring_charge_data()
        if not self.settings.ARB.value:
            recurring_orderitems = self.get_recurring_orderitems()
            if recurring_orderitems:
                success, results = self.process_recurring_subscriptions(recurring_orderitems, testing)
                if not success:
                    self.log_extra('recur payment failed, aborting the rest of the module')
                    return results

        if order.paid_in_full:
            self.log_extra('%s is paid in full, no capture attempted.', order)
            results = ProcessorResult(self.key, True, _("No charge needed, paid in full."))
            # if not recurlist:
            #     self.record_payment()
        else:
            self.log_extra('Capturing payment for %s', order)

            if amount is None:
                amount = order.balance

            standard = self.get_standard_charge_data(order, amount)
            customer_id = self.get_or_create_customer(order)
            standard["customer"] = customer_id
            # payment_method = self.create_payment_method(order, include_billing_details=True)
            # standard["payment_method"] = payment_method
            standard["confirm"] = True
            payment_intent = self.stripe.PaymentIntent.create(**standard)
            payment = self.record_payment(order=self.order, amount=amount, transaction_id=payment_intent.id)
            results = ProcessorResult(self.key, True, "Payment Intent #%s is created" % payment_intent.id, payment=payment)

        return results

    def process_recurring_subscription(self, order_item, customer_id, testing=False):
        product = None
        amount = order_item.total_with_tax
        subscriptionproduct = order_item.product.subscriptionproduct
        price_data = {
            'unit_amount': int(amount * 100),
            'currency': self.settings.CURRENCY_CODE.value,
            'recurring': {
                'interval': subscriptionproduct.expire_unit.lower(),
                'interval_count': subscriptionproduct.expire_length,
            },
            # 'product': product.id,
        }

        query = "metadata['product_pk']:'%s'" % order_item.product.pk
        search_result = self.stripe.Product.search(query=query, stripe_version=self.search_stripe_version, expand=["data.default_price"])
        items = search_result.get("data")
        if len(items) > 0:
            product = items[0]

        if product:
            price = product.get("default_price")
            if not price or price.get("unit_amount") != price_data.get("unit_amount") or not price.get("recurring") or \
             price.get("recurring").get("interval") != price_data.get("recurring").get("interval") or \
             price.get("recurring").get("interval_count") != price_data.get("recurring").get("interval_count"):
                price_data['product'] = product.get("id")
                price = stripe.Price.create(**price_data)
                self.stripe.Product.modify(product.get("id"), default_price=price.id)
        else:
            product = self.stripe.Product.create(name=order_item.product.name,
                                                 default_price_data=price_data,
                                                 metadata={'product_pk': order_item.product.pk})
            price = product.default_price

        data = {
            'customer': customer_id,
            'items': [{
                'price': price.get("id"),
            }]
        }
        subscription = stripe.Subscription.create(**data)
        payment = self.record_payment(order=self.order, amount=amount, transaction_id=subscription.id)
        return ProcessorResult(self.key, True, "Subscription #%s is created" % subscription.id, payment=payment)

    def process_recurring_subscriptions(self, recurring_orderitems, testing=False):
        """Post all subscription requests."""

        results = []
        success = True
        customer_id = self.get_or_create_customer(recurring_orderitems[0].order)
        for order_item in recurring_orderitems:
            result = self.process_recurring_subscription(order_item, customer_id, testing=testing)

            if result.success:
                results.append(result)
            else:
                self.log.info("Failed to process recurring subscription")
                success = False
                results = result
                break

        return success, results

    def generate_card_token(self, credit_card, order):
        if self.card_token:
            return self.card_token
        card_data = {
            "number": credit_card.decryptedCC,
            "exp_month": credit_card.expire_month,
            "exp_year": credit_card.expire_year,
            "cvc": credit_card.ccv,
            # 'address_country': order.bill_country,
            # 'address_state': order.bill_state,
            # 'address_city': order.bill_city,
            # 'address_zip': order.bill_postal_code,
            # 'address_line1': order.bill_street1,
            # 'address_line2': order.bill_street2,
            # 'name': "%s %s" % (order.bill_first_name, order.bill_last_name),
        }
        result = self.stripe.Token.create(card=card_data)
        self.card_token = result['id']
        return self.card_token

    def get_standard_charge_data(self, order, amount):
        data = {
            'amount': int(amount * 100),
            'currency': self.settings.CURRENCY_CODE.value,
            # 'source': self.generate_card_token(order.credit_card, order),
            'description': "Order #%s from %s %s" % (order.pk, order.bill_first_name, order.bill_last_name),
            'metadata': {"order_id": str(order.pk)},
            # 'receipt_email' : order.contact.email,
        }
        if order.is_shippable:
            data['shipping'] = {
                'name': order.ship_addressee,
                'address': self.prepare_shipping_address(order),
            }
        return data

    def prepare_billing_address(self, order):
        return {
            'country': order.bill_country,
            'state': order.bill_state,
            'city': order.bill_city,
            'postal_code': order.bill_postal_code,
            'line1': order.bill_street1,
            'line2': order.bill_street2,
        }

    def prepare_shipping_address(self, order):
        return {
            'country': order.ship_country,
            'state': order.ship_state,
            'city': order.ship_city,
            'postal_code': order.ship_postal_code,
            'line1': order.ship_street1,
            'line2': order.ship_street2,
        }

    def get_or_create_customer(self, order):
        if self.customer_id:
            return self.customer_id

        customer_id = None
        email = order.contact.email
        default_payment_card = None
        default_payment_method = order.get_variable("default_payment_method")
        try:
            customer = self.dj_models.Customer.objects.get(email=email, id__isnull=False)
            customer_id = customer.id
            if default_payment_method:
                default_payment_card = customer.default_payment_method.card
        except (self.dj_models.Customer.DoesNotExist, AttributeError):
            query = "email:'%s'" % email
            search_result = self.stripe.Customer.search(query=query, stripe_version=self.search_stripe_version, expand=['data.invoice_settings.default_payment_method'])
            items = search_result.get("data")
            if len(items) > 0:
                customer_id = items[0].get("id")
                if default_payment_method:
                    try:
                        default_payment_card = items[0].get("invoice_settings").get("default_payment_method").get("card")
                    except AttributeError:
                        pass

        payment_method_id = None
        if not default_payment_card:
            payment_method = self.create_payment_method(order)
            payment_method_id = payment_method.id

        data = {
            'name': "%s %s" % (order.bill_first_name, order.bill_last_name),
            'phone': order.contact.primary_phone.phone,
            'address': self.prepare_billing_address(order),
            'shipping': {
                'name': order.ship_addressee,
                'address': self.prepare_shipping_address(order),
            },
        }

        if customer_id:
            if not default_payment_card:
                self.stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
                data['invoice_settings'] = {'default_payment_method': payment_method_id}
            self.stripe.Customer.modify(customer_id, **data)
        else:
            data['email'] = email
            data['payment_method'] = payment_method_id
            customer = self.stripe.Customer.create(**data)
            customer_id = customer.id

        self.customer_id = customer_id
        return self.customer_id

    def create_payment_method(self, order, include_billing_details=False):
        data = {
            'type': "card",
            'card': {
                "number": order.credit_card.decryptedCC,
                "exp_month": order.credit_card.expire_month,
                "exp_year": order.credit_card.expire_year,
                "cvc": order.credit_card.ccv,
            },
        }
        if include_billing_details:
            data['billing_details'] = {
                'name': "%s %s" % (order.bill_first_name, order.bill_last_name),
                'email': order.contact.email,
                'phone': order.contact.primary_phone.phone,
                'address': self.prepare_billing_address(order),
            }
        payment_method = self.stripe.PaymentMethod.create(**data)
        return payment_method

    def get_default_payment_method(self, request):
        contact = Contact.objects.from_request(request)
        if contact:
            email = contact.email
            default_payment_method = None
            card = None
            try:
                customer = self.dj_models.Customer.objects.get(email=email, id__isnull=False)
                card = customer.default_payment_method.card
            except (self.dj_models.Customer.DoesNotExist, AttributeError):
                query = "email:'%s'" % email
                search_result = self.stripe.Customer.search(query=query, stripe_version=self.search_stripe_version, expand=['data.invoice_settings.default_payment_method'])
                items = search_result.get("data")
                if len(items) > 0:
                    try:
                        card = items[0].get("invoice_settings").get("default_payment_method").get("card")
                    except AttributeError:
                        pass
            if card and self.validate_card(card):
                default_payment_method = "%s: ... %s" % (card.get("brand", "").title(), card.get("last4", ""))
            return default_payment_method

    def validate_card(self, card):
        if card:
            exp_month = card.get('exp_month', None)
            exp_year = card.get('exp_year', None)
            if exp_month and exp_year:
                today = timezone.now().date()
                exp_date = datetime.date(exp_year, exp_month + 1, 1)
                if exp_date > today:
                    return True


if __name__ == "__main__":
    """
    This is for testing - enabling you to run from the command line and make
    sure everything is ok
    """
    import os
    from livesettings.functions import config_get_group

    # Set up some dummy classes to mimic classes being passed through Satchmo
    class testContact(object):
        pass
    class testCC(object):
        pass
    class testOrder(object):
        def __init__(self):
            self.contact = testContact()
            self.credit_card = testCC()
        def order_success(self):
            pass

    if not "DJANGO_SETTINGS_MODULE" in os.environ:
        os.environ["DJANGO_SETTINGS_MODULE"]="satchmo_store.settings"

    settings_module = os.environ['DJANGO_SETTINGS_MODULE']
    settingsl = settings_module.split('.')
    settings = __import__(settings_module, {}, {}, settingsl[-1])

    sampleOrder = testOrder()
    sampleOrder.contact.first_name = 'Chris'
    sampleOrder.contact.last_name = 'Smith'
    sampleOrder.contact.primary_phone = '801-555-9242'
    sampleOrder.full_bill_street = '123 Main Street'
    sampleOrder.bill_postal_code = '12345'
    sampleOrder.bill_state = 'TN'
    sampleOrder.bill_city = 'Some City'
    sampleOrder.bill_country = 'US'
    sampleOrder.total = "27.01"
    sampleOrder.balance = "27.01"
    sampleOrder.credit_card.decryptedCC = '6011000000000012'
    sampleOrder.credit_card.expirationDate = "10/11"
    sampleOrder.credit_card.ccv = "144"

    stripe_settings = config_get_group('PAYMENT_STRIPE')
    if not stripe_settings.LIVE.value:
        processor = PaymentProcessor(stripe_settings)
        processor.prepare_data(sampleOrder)
        results = processor.process(testing=True)
