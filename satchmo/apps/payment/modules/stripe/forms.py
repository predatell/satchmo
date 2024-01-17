from payment.forms import CreditPayShipForm


class StripePaymentForm(CreditPayShipForm):
    DEFAULT_PAYMENT_METHOD = 0

    def __init__(self, request, paymentmodule, *args, **kwargs):
        creditchoices = paymentmodule.CREDITCHOICES.choice_values
        super(StripePaymentForm, self).__init__(request, paymentmodule, *args, **kwargs)
        processor_module = paymentmodule.MODULE.load_module('processor')
        processor = processor_module.PaymentProcessor(paymentmodule)
        default_payment_method = processor.get_default_payment_method(request)
        if default_payment_method:
            creditchoices.insert(0, (self.DEFAULT_PAYMENT_METHOD, default_payment_method))
            self.fields['credit_type'].initial = self.DEFAULT_PAYMENT_METHOD
            card_required_list = ['credit_number', 'month_expires', 'year_expires', 'ccv']
            for field_name in card_required_list:
                self.fields[field_name].required = False
        self.fields['credit_type'].choices = creditchoices

    def clean_credit_number(self):
        credit_number = self.cleaned_data.get("credit_number", "")
        if self.if_default_payment_method(self.cleaned_data):
            return credit_number
        else:
            return super(StripePaymentForm, self).clean_credit_number()

    def clean_ccv(self):
        ccv = self.cleaned_data.get("ccv", "")
        if self.if_default_payment_method(self.cleaned_data):
            return ccv
        else:
            return super(StripePaymentForm, self).clean_ccv()

    def save(self, request, cart, contact, payment_module, data=None):
        if data is None:
            data = self.cleaned_data
        super(StripePaymentForm, self).save(request, cart, contact, payment_module, data=data)
        if self.order and self.if_default_payment_method(data):
            self.order.add_variable("default_payment_method", True)

    def if_default_payment_method(self, data):
        return data.get("credit_type", "0") == str(self.DEFAULT_PAYMENT_METHOD)
