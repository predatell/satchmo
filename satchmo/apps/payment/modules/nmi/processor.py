import urllib
import copy
from datetime import timedelta

from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from payment.modules.base import BasePaymentProcessor, ProcessorResult

TEST_CARDS = ["4111111111111111", "5431111111111111", "6011601160116611", "341111111111111", "30205252489926", "3541963594572595", "6799990100000000019"]


class PaymentProcessor(BasePaymentProcessor):
    """
    NMI payment processing module
    You must have an account with nmi.com in order to use this module.

    Additionally, you must have ARB enabled in your account to use recurring billing.
    """

    def __init__(self, settings):
        super(PaymentProcessor, self).__init__('nmi', settings)

    def can_recur_bill(self):
        return True

    def capture_payment(self, testing=False, order=None, amount=None):
        """Process payments without an authorization step."""
        if order:
            self.prepare_data(order)
        else:
            order = self.order

        standard = self.get_standard_charge_data(order)

        recurlist = self.get_recurring_charge_data(standard)
        if recurlist:
            success, results = self.process_recurring_subscriptions(recurlist, testing)
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
            standard['amount'] = '{0:.2f}'.format(float(amount))
            if order.is_shippable:
                self.attach_shipping(standard, order)
            results = self.send_post(standard, testing, amount)

        return results

    def get_recurring_charge_data(self, standard):
        """Build the list of dictionaries needed to process a recurring charge.

        Because Authorize can only take one subscription at a time, we build a list
        of the transaction dictionaries, for later sequential posting.
        """
        if not self.settings.ARB.value:
            return []

        # get all subscriptions from the order
        recurring_orderitems = self.get_recurring_orderitems()

        if len(recurring_orderitems) == 0:
            self.log_extra('No subscription items')
            return []

        start_date = timezone.now().date()
        translist = []

        for order_item in recurring_orderitems:
            data = standard.copy()
            product = order_item.product
            subscription = product.subscriptionproduct
            amount = order_item.total_with_tax

            if order_item.is_shippable:
                self.attach_shipping(data, order_item.order)

            occurrences = subscription.recurring_times or 9999
            if occurrences >= 9999:
                occurrences = 0

            if subscription.expire_unit == "DAY":
                data['day_frequency'] = subscription.expire_length
            else:
                data['month_frequency'] = subscription.expire_length
                data['day_of_month'] = start_date.day

            start_date += timedelta(1)
            data['order_description'] = "Subscription: %s" % product.name,
            data['plan_payments'] = occurrences
            data['recurring'] = "add_subscription"
            data['start_date'] = start_date.strftime("%Y%m%d")
            data['plan_amount'] = '{0:.2f}'.format(float(amount))
            data['amount'] = '{0:.2f}'.format(float(amount))
            if amount:
                translist.append(data)

        return translist

    def process_recurring_subscriptions(self, recurlist, testing=False):
        """Post all subscription requests."""

        results = []
        success = True
        for recur in recurlist:
            amount = recur['plan_amount']
            recur['plan_amount'] = '{0:.2f}'.format(float(amount))
            result = self.send_post(recur, testing, amount)
            if result.success:
                results.append(result)
            else:
                self.log.info("Failed to process recurring subscription")
                success = False
                results = result
                break

        return success, results

    def get_standard_charge_data(self, order, amount=None):
        exp = "%.2d%.2d" % (int(order.credit_card.expire_month), (int(order.credit_card.expire_year) % 100))

        if self.settings.LIVE.value:
            security_key = self.settings.TRANKEY.value
        else:
            security_key = self.settings.TEST_TRANKEY.value

        data = {
            'security_key': security_key,

            'ccnumber' : order.credit_card.decryptedCC,
            'ccexp' : exp,
            'cvv' : order.credit_card.ccv,

            'type': "sale",
            # 'amount': '{0:.2f}'.format(float(amount)),

            'orderid': str(order.pk),
            'order_description': "Order #%s from %s %s" % (order.pk, order.bill_first_name, order.bill_last_name),
            # 'shipping': '{0:.2f}'.format(float(order.shipping_sub_total))
            # 'ipaddress': ipadress
            # 'tax': '{0:.2f}'.format(float(order.tax))
            # 'ponumber': ponumber

            'email' : order.contact.email,
            'phone' : order.contact.primary_phone.phone,

            'firstname': order.bill_first_name,
            'lastname' : order.bill_last_name,
            'address1': order.bill_street1,
            'address2': order.bill_street2,
            'city': order.bill_city,
            'state' : order.bill_state,
            'zip' : order.bill_postal_code,
            'country': order.bill_country,
            # 'website' : website,
        }

        if self.settings.SIMULATE.value:
            if data["ccexp"] == "1025" and data["ccexp"] in TEST_CARDS:
                data["test_mode"] = "enabled"

        return data

    def attach_shipping(self, data, order):
        data['shipping_firstname'] = order.ship_first_name
        data['shipping_lastname'] = order.ship_last_name
        data['shipping_address1'] = order.ship_street1
        data['shipping_address2'] = order.ship_street2
        data['shipping_city'] = order.ship_city
        data['shipping_state'] = order.ship_state
        data['shipping_zip'] = order.ship_postal_code
        data['shipping_country'] = order.ship_country

    def send_post(self, data, testing=False, amount=None):
        """Execute the post to nmi.com.

        Params:
        - data: dictionary as returned by get_standard_charge_data
        - testing: if true, then don't record the payment

        Returns:
        - ProcessorResult
        """
        # self.log.info("About to send a request to NMI: %(connection)s\n%(logPostString)s", data)
        post_data = urlencode(data)

        try:
            conn = urllib.request.Request(url=self.settings.CONNECTION.value, data=post_data.encode("utf-8"))
            f = urllib.request.urlopen(conn)
            all_results = f.read().decode("utf-8")

            temp = urllib.parse.parse_qs(all_results)
            responses = {}
            for key, value in temp.items():
                responses[key] = value[0]
        except urllib.error.URLError as ue:
            self.log.error("error opening %s\n%s", self.settings.CONNECTION.value, ue)
            return ProcessorResult(self.key, False, 'Could not talk to NMI gateway')

        response_code = int(responses['response'])
        response_text = responses['responsetext']
        reason_code = responses['response_code']
        payment = None
        if response_code == 1:
            if not testing:
                payment = self.record_payment(order=self.order, amount=amount,
                    transaction_id=responses['transactionid'], reason_code=reason_code)
            success = True
        else:
            if not testing:
                payment = self.record_failure(order=self.order, amount=amount,
                    reason_code=reason_code, details=response_text)
            success = False
        result = ProcessorResult(self.key, success, response_text, payment=payment)
        return result


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

    nmi_settings = config_get_group('PAYMENT_NMI')
    if not nmi_settings.LIVE.value:
        processor = PaymentProcessor(nmi_settings)
        processor.prepare_data(sampleOrder)
        results = processor.process(testing=True)
