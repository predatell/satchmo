"""
Handle a Purchase Order payments.
"""
from django.utils.translation import gettext as _
from payment.modules.base import BasePaymentProcessor, ProcessorResult

class PaymentProcessor(BasePaymentProcessor):

    def __init__(self, settings):
        super(PaymentProcessor, self).__init__('purchaseorder', settings)

    def can_refund(self):
        return True

    def prepare_data(self, order):
        super(PaymentProcessor, self).prepare_data(order)

    def capture_payment(self, testing=False, order=None, amount=None):
        """
        Purchase Orders are always successful.
        """
        if not order:
            order = self.order

        if amount is None:
            amount = order.balance

        payment = self.record_payment(order=order, amount=amount,
            transaction_id="PO", reason_code='0')

        return ProcessorResult(self.key, True, _('Success'), payment)

