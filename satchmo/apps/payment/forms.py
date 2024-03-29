from decimal import Decimal

from django import forms
from django.template import loader
from django.utils.translation import gettext_lazy as _

from l10n.utils import moneyfmt
from livesettings.functions import config_value, config_value_safe
from payment import signals
from payment.config import labelled_gateway_choices, credit_choices
from payment.models import CreditCardDetail
from payment.utils import get_or_create_order
from product.models import Discount, TaxClass, Price
from product.prices import PriceAdjustmentCalc, PriceAdjustment
from product.utils import find_best_auto_discount
from satchmo_store.contact.forms import ProxyContactForm, ContactInfoForm
from satchmo_store.contact.models import Contact
from satchmo_store.shop.models import Cart, Order, OrderItem
from satchmo_store.shop.signals import satchmo_shipping_price_query
from satchmo_utils.dynamic import lookup_template
from satchmo_utils.views import CreditCard
from shipping.config import shipping_methods, shipping_method_by_key
from shipping.signals import shipping_choices_query
from shipping.utils import update_shipping
from satchmo_utils.signals import form_init, form_initialdata, form_presave, form_postsave, form_validate
from tax.templatetags.satchmo_tax import _get_taxprocessor
from threaded_multihost import threadlocals
import calendar
import datetime
import logging

log = logging.getLogger('payment.forms')

MONTHS = [(month,'%02d'%month) for month in range(1,13)]

def _get_cheapest_shipping(shipping_dict):
    """Use the shipping_dict as returned by _get_shipping_choices
    to figure the cheapest shipping option."""

    least = None
    leastcost = None
    for key, value in shipping_dict.items():
        current = value['cost']
        if leastcost is None or current < leastcost:
            least = key
            leastcost = current

    return least

def _get_shipping_choices(request, paymentmodule, cart, contact, default_view_tax=False, order=None):
    """Iterate through legal shipping modules, building the list for display to the user.

    Returns the shipping choices list, along with a dictionary of shipping choices, useful
    for building javascript that operates on shipping choices.
    """
    shipping_options = []
    shipping_dict = {}
    rendered = {}
    if not order:
        try:
            order = Order.objects.from_request(request)
        except Order.DoesNotExist:
            pass

    discount = None
    if order:
        try:
            discount = Discount.objects.by_code(order.discount_code)
        except Discount.DoesNotExist:
            pass

    if not cart.is_shippable:
        methods = [shipping_method_by_key('NoShipping'),]
    else:
        methods = shipping_methods()

    tax_shipping = config_value_safe('TAX','TAX_SHIPPING', False)
    shipping_tax = None

    if tax_shipping:
        taxer = _get_taxprocessor(request)
        shipping_tax = TaxClass.objects.get(title=config_value('TAX', 'TAX_CLASS'))

    for method in methods:
        method.calculate(cart, contact)
        if method.valid(order=order):
            template = lookup_template(paymentmodule, 'shipping/options.html')
            t = loader.get_template(template)
            shipcost = finalcost = method.cost()

            if discount and order:
                order.shipping_cost = shipcost
                discount.calc(order)
                shipdiscount = discount.item_discounts.get('Shipping', 0)
            else:
                shipdiscount = 0

            # set up query to determine shipping price to show
            shipprice = Price()
            shipprice.price = shipcost
            shipadjust = PriceAdjustmentCalc(shipprice)
            if shipdiscount:
                shipadjust += PriceAdjustment('discount', _('Discount'), shipdiscount)

            satchmo_shipping_price_query.send(cart, adjustment=shipadjust)
            shipdiscount = shipadjust.total_adjustment()

            if shipdiscount:
                finalcost -= shipdiscount

            shipping_dict[method.id] = {'cost' : shipcost, 'discount' : shipdiscount, 'final' : finalcost}

            taxed_shipping_price = None
            if tax_shipping:
                taxcost = taxer.by_price(shipping_tax, finalcost)
                total = finalcost + taxcost
                taxed_shipping_price = moneyfmt(total)
                shipping_dict[method.id]['taxedcost'] = total
                shipping_dict[method.id]['tax'] = taxcost

            c = {
                'amount': finalcost,
                'description' : method.description(),
                'method' : method.method(),
                'expected_delivery' : method.expectedDelivery(),
                'default_view_tax' : default_view_tax,
                'shipping_tax': shipping_tax,
                'taxed_shipping_price': taxed_shipping_price}
            rendered[method.id] = t.render(c)

    #now sort by price, low to high
    sortme = [(value['cost'], key) for key, value in shipping_dict.items()]
    sortme.sort()

    shipping_options = [(key, rendered[key]) for cost, key in sortme]

    shipping_choices_query.send(sender=cart, cart=cart,
        paymentmodule=paymentmodule, contact=contact,
        default_view_tax=default_view_tax, order=order,
        shipping_options = shipping_options,
        shipping_dict = shipping_dict)
    return shipping_options, shipping_dict


def _find_sale(cart):
    if cart.numItems > 0:
        products = [item.product for item in cart.cartitem_set.all()]
        sale = find_best_auto_discount(products)
    else:
        sale = None

    return sale

    
# class CustomChargeForm(forms.Form):
#     orderitem = forms.IntegerField(required=True, widget=forms.HiddenInput())
#     amount = forms.DecimalField(label=_('New price'), required=False)
#     shipping = forms.DecimalField(label=_('Shipping adjustment'), required=False)
#     notes = forms.CharField(label=_('Notes'), required=False, initial="Your custom item is ready.")

#     def __init__(self, *args, **kwargs):
#         initial = kwargs.get('initial', {})
#         form_initialdata.send('CustomChargeForm', form=self, initial=initial)
#         kwargs['initial'] = initial
#         super(CustomChargeForm, self).__init__(*args, **kwargs)
#         form_init.send(CustomChargeForm, form=self)

#     def clean(self, *args, **kwargs):
#         super(CustomChargeForm, self).clean(*args, **kwargs)
#         form_validate.send(CustomChargeForm, form=self)
#         return self.cleaned_data


class CustomChargeForm(forms.ModelForm):
    shipping = forms.DecimalField(label=_('Extra Shipping'), required=False)
    notes = forms.CharField(label=_('Notes'), required=False, initial="Your custom item is ready.")
        
    class Meta:
        model = OrderItem
        fields = ('unit_price', 'line_item_price')

    def __init__(self, *args, **kwargs):
        initial = kwargs.get('initial', {})
        form_initialdata.send('CustomChargeForm', form=self, initial=initial)
        kwargs['initial'] = initial
        super(CustomChargeForm, self).__init__(*args, **kwargs)
        form_init.send(CustomChargeForm, form=self)
        
    def clean(self, *args, **kwargs):
        super(CustomChargeForm, self).clean(*args, **kwargs)
        form_validate.send(CustomChargeForm, form=self)
        return self.cleaned_data
        
    def save(self, commit=True): 
        self.instance.line_item_price = self.cleaned_data.get('unit_price') * self.instance.quantity
        obj = super(CustomChargeForm, self).save(commit=commit)
        order = obj.order
        if not order.shipping_cost:
            order.shipping_cost = Decimal("0.00")
        shipping = self.cleaned_data.get('shipping')
        if shipping:
            order.shipping_cost += shipping
        order.recalculate_total()
        notes = self.cleaned_data.get('notes') or "Updated total price"
        order.add_status(notes=notes)
        return obj        
        
        
class PaymentMethodForm(ProxyContactForm):
    paymentmethod = forms.ChoiceField(label=_('Payment method'), required=True,
                                      choices=labelled_gateway_choices(), widget=forms.RadioSelect)

    def __init__(self, cart=None, order=None, *args, **kwargs):
        super(PaymentMethodForm, self).__init__(*args, **kwargs)
        self.cart = cart
        # Send a signal to perform additional filtering of available payment methods.
        # Receivers have cart/order passed in variables to check the contents and modify methods
        # list if neccessary.
        payment_choices = labelled_gateway_choices()
        signals.payment_methods_query.send(
                PaymentMethodForm,
                methods=payment_choices,
                cart=cart,
                order=order,
                contact=self._contact
                )
        if self.fields['paymentmethod'].initial == None:
            self.fields['paymentmethod'].initial = payment_choices[0][0]
        if len(payment_choices) == 1:
            self.fields['paymentmethod'].widget = forms.HiddenInput()
        else:
            self.fields['paymentmethod'].widget = forms.RadioSelect()
        self.fields['paymentmethod'].choices = payment_choices

    def clean(self):
        # allow additional validation
        form_validate.send(PaymentMethodForm, form=self)
        return self.cleaned_data

        
class PaymentContactInfoForm(PaymentMethodForm, ContactInfoForm):
    payment_required_fields = None

    def __init__(self, *args, **kwargs):
        super(PaymentContactInfoForm, self).__init__(*args, **kwargs)
        if not self.cart:
            request = threadlocals.get_current_request()
            self.cart = Cart.objects.from_request(request)

        self.fields['discount'] = forms.CharField(max_length=30, required=False)

        self.payment_required_fields = {}

        if config_value('PAYMENT', 'USE_DISCOUNTS'):
            if not self.fields['discount'].initial:
                sale = _find_sale(self.cart)
                if sale:
                    self.fields['discount'].initial = sale.code
        else:
            self.fields['discount'].widget = forms.HiddenInput()

        # Listeners of the form_init signal (below) may modify the dict of
        # payment_required_fields. For example, if your CUSTOM_PAYMENT requires
        # customer's city, put the following code in the listener:
        #
        #   form.payment_required_fields['CUSTOM_PAYMENT'] = ['city']
        #
        form_init.send(PaymentContactInfoForm, form=self)

    def save(self, request, *args, **kwargs):
        form_presave.send(PaymentContactInfoForm, form=self)
        contactid = super(PaymentContactInfoForm, self).save(*args, **kwargs)
        contact = Contact.objects.get(pk=contactid)
        cart = kwargs.get('cart', None)
        if not cart:
            cart = Cart.objects.from_request(request)
        if not cart.customer:
            cart.customer = contact
            cart.save()
        self.order = get_or_create_order(request, cart, contact, self.cleaned_data)
        form_postsave.send(PaymentContactInfoForm, form=self)
        return contactid

    def clean(self):
        try:
            paymentmethod = self.cleaned_data['paymentmethod']
        except KeyError:
            self._errors['paymentmethod'] = forms.util.ErrorList([_('This field is required')])
            return self.cleaned_data
        required_fields = self.payment_required_fields.get(paymentmethod, [])
        msg = _('Selected payment method requires this field to be filled')
        for fld in required_fields:
            if not (fld in self.cleaned_data and self.cleaned_data[fld]):
                self._errors[fld] = forms.util.ErrorList([msg])
            elif fld == 'state':
                self.enforce_state = True
                try:
                    self._check_state(self.cleaned_data['state'], self.cleaned_data['country'])
                except forms.ValidationError as e:
                    self._errors[fld] = e.messages
        super(PaymentContactInfoForm, self).clean()
        return self.cleaned_data

    def clean_discount(self):
        """ Check if discount exists and is valid. """
        if not config_value('PAYMENT', 'USE_DISCOUNTS'):
            return ''
        data = self.cleaned_data['discount']
        if data:
            try:
                discount = Discount.objects.get(code=data, active=True)
            except Discount.DoesNotExist:
                raise forms.ValidationError(_('Invalid discount code.'))

            request = threadlocals.get_current_request()
            try:
                contact = Contact.objects.from_request(request)
            except Contact.DoesNotExist:
                contact = None

            valid, msg = discount.isValid(self.cart, contact=contact)

            if not valid:
                raise forms.ValidationError(msg)
            # TODO: validate that it can work with these products
        return data


class SimplePayShipForm(forms.Form):
    shipping = forms.ChoiceField(widget=forms.RadioSelect(), required=False)

    def __init__(self, request, paymentmodule, *args, **kwargs):
        super(SimplePayShipForm, self).__init__(*args, **kwargs)

        try:
            order = Order.objects.from_request(request)
        except Order.DoesNotExist:
            order = None
        self.order = order
        self.orderpayment = None
        self.paymentmodule = paymentmodule

        try:
            self.tempCart = Cart.objects.from_request(request)
            if self.tempCart.numItems > 0:
                products = [item.product for item in self.tempCart.cartitem_set.all()]

        except Cart.DoesNotExist:
            self.tempCart = None

        try:
            self.tempContact = Contact.objects.from_request(request)
        except Contact.DoesNotExist:
            self.tempContact = None

        if 'default_view_tax' in kwargs:
            default_view_tax = kwargs['default_view_tax']
        else:
            default_view_tax = config_value_safe('TAX', 'TAX_SHIPPING', False)

        shipping_choices, shipping_dict = _get_shipping_choices(request, paymentmodule, self.tempCart, self.tempContact, default_view_tax=default_view_tax)


        cheapshipping = _get_cheapest_shipping(shipping_dict)
        self.cheapshipping = cheapshipping
        discount = None
        if order and order.discount_code:
            try:
                discount = Discount.objects.by_code(order.discount_code)
                # 'discount' object could be NullDiscount instance
                if discount and hasattr(discount, 'shipping') and discount.shipping == "FREECHEAP":
                    if cheapshipping:
                        shipping_choices = [opt for opt in shipping_choices if opt[0] == cheapshipping]
                        shipping_dict = {cheapshipping: shipping_dict[cheapshipping]}
            except Discount.DoesNotExist:
                pass
        
        # possibly hide the shipping based on store config
        shiphide = config_value('SHIPPING','HIDING')
        # Handle a partial payment and make sure we don't show a shipping choice after one has
        # already been chosen
        if self.order and self.order.is_partially_paid and shipping_dict.get(self.order.shipping_model, False):
            self.fields['shipping'] = forms.CharField(max_length=30, initial=self.order.shipping_model,
                widget=forms.HiddenInput(attrs={'value' : shipping_choices[0][0]}))
            self.shipping_hidden = True
        # Possibly hide if there is only 1 choise
        elif shiphide in ('YES', 'DESCRIPTION') and len(shipping_choices) == 1:
            self.fields['shipping'] = forms.CharField(max_length=30, initial=shipping_choices[0][0],
                widget=forms.HiddenInput(attrs={'value' : shipping_choices[0][0]}))
            if shiphide == 'DESCRIPTION':
                self.shipping_hidden = False
                self.shipping_description = shipping_choices[0][1]
            else:
                self.shipping_hidden = True
                self.shipping_description = ""
        elif len(shipping_choices) == 0:
            self.shipping_hidden = True
        else:
            self.fields['shipping'].choices = shipping_choices
            if config_value('SHIPPING','SELECT_CHEAPEST'):
                if cheapshipping is not None:
                    self.fields['shipping'].initial = cheapshipping
                    initial = kwargs.get('initial') or {}
                    initial['shipping'] = cheapshipping
                    kwargs['initial'] = initial
            self.shipping_hidden = False
                
        self.shipping_dict = shipping_dict
        form_init.send(SimplePayShipForm, form=self)

    def clean_shipping(self):
        shipping = self.cleaned_data['shipping']
        if not shipping and self.tempCart.is_shippable:
            raise forms.ValidationError(_('This field is required.'))
        return shipping

    def is_needed(self):
        """Check to see if this form is even needed
        it is *not* needed if:
        - we have an order
        - the order balance is zero
        - No shipping needs to be selected
        """
        needed = True
        if self.order and self.tempContact and self.tempCart:
            order = self.order
            if order.is_shippable and len(self.shipping_dict) == 1:
                update_shipping(order, list(self.shipping_dict.keys())[0], self.tempContact, self.tempCart)
            order.recalculate_total(save=False)
            needed = not order.paid_in_full
            if not needed:
                log.debug('%s can skip the payment step - no info needed', order)

        return needed

    def save(self, request, cart, contact, payment_module, data=None):
        form_presave.send(SimplePayShipForm, form=self)
        if data is None:
            data = self.cleaned_data
        self.order = get_or_create_order(request, cart, contact, data)
        if payment_module:
            processor_module = payment_module.MODULE.load_module('processor')
            processor = processor_module.PaymentProcessor(payment_module)
            self.orderpayment = processor.create_pending_payment(order=self.order)
        else:
            self.orderpayment = None
        form_postsave.send(SimplePayShipForm, form=self)


class CreditPayShipForm(SimplePayShipForm):
    credit_type = forms.ChoiceField()
    credit_number = forms.CharField(max_length=20, widget=forms.PasswordInput(attrs={'autocomplete':'off'}))
    month_expires = forms.ChoiceField(choices=MONTHS)
    year_expires = forms.ChoiceField()
    ccv = forms.CharField(max_length=4, label='Sec code', widget=forms.PasswordInput(attrs={'autocomplete':'off'}))

    def __init__(self, request, paymentmodule, *args, **kwargs):
        creditchoices = paymentmodule.CREDITCHOICES.choice_values
        super(CreditPayShipForm, self).__init__(request, paymentmodule, *args, **kwargs)

        self.cc = None

        self.fields['credit_type'].choices = creditchoices

        num_years = config_value('PAYMENT', 'CC_NUM_YEARS')
        year_now = datetime.date.today().year
        self.fields['year_expires'].choices = [(year, year) for year in range(year_now, year_now+num_years+1)]

        self.tempCart = Cart.objects.from_request(request)

        initial = kwargs.get('initial', None)
        if initial:
            if initial.get('credit_number', None):
                self.fields['credit_number'].widget = forms.PasswordInput()
            if initial.get('ccv', None):
                self.fields['ccv'].widget = forms.PasswordInput()

        try:
            self.tempContact = Contact.objects.from_request(request)
        except Contact.DoesNotExist:
            self.tempContact = None

    def clean(self):
        super(CreditPayShipForm, self).clean()
        data = self.cleaned_data
        if not self.is_valid():
            log.debug('form not valid, no early auth')
            return data
        early = config_value('PAYMENT', 'AUTH_EARLY')

        if early:
            processor_module = self.paymentmodule.MODULE.load_module('processor')
            processor = processor_module.PaymentProcessor(self.paymentmodule)
            if processor.can_authorize():
                log.debug('Processing early capture/release for: %s', self.order)
                processor_module = self.paymentmodule.MODULE.load_module('processor')
                processor = processor_module.PaymentProcessor(self.paymentmodule)
                if self.order:
                    # we have to make a payment object and save the credit card data to
                    # make an auth/release.
                    orderpayment = processor.create_pending_payment(order=self.order,
                        amount=Decimal('0.01'))
                    op = orderpayment.capture

                    cc = CreditCardDetail(orderpayment=op,
                        expire_month=data['month_expires'],
                        expire_year=data['year_expires'],
                        credit_type=data['credit_type'])

                    cc.storeCC(data['credit_number'])
                    cc.save()

                    # set ccv into cache
                    cc.ccv = data['ccv']
                    self.cc = cc
                    results = processor.authorize_and_release(order=self.order)
                    if not results.success:
                        log.debug('Payment module error: %s', results)
                        raise forms.ValidationError(results.message)
                else:
                    log.debug('Payment module capture/release success for %s', self.order)
            else:
                log.debug('Payment module %s cannot do credit authorizations, ignoring AUTH_EARLY setting.',
                    self.paymentmodule.MODULE.value)
        return data


    def clean_credit_number(self):
        """ Check if credit card is valid. """
        data = self.cleaned_data
        credit_number = data['credit_number']
        card = CreditCard(credit_number, data['credit_type'])
        results, msg = card.verifyCardTypeandNumber()
        if not results:
            raise forms.ValidationError(msg)

        return credit_number

    def clean_month_expires(self):
        return int(self.cleaned_data['month_expires'])

    def clean_year_expires(self):
        """ Check if credit card has expired. """
        month = self.cleaned_data['month_expires']
        year = int(self.cleaned_data['year_expires'])
        max_day = calendar.monthrange(year, month)[1]
        if datetime.date.today() > datetime.date(year=year, month=month, day=max_day):
            raise forms.ValidationError(_('Your card has expired.'))
        return year

    def clean_ccv(self):
        """ Validate a proper CCV is entered. Remember it can have a leading 0 so don't convert to int and return it"""
        try:
            check = int(self.cleaned_data['ccv'])
            return self.cleaned_data['ccv'].strip()
        except ValueError:
            raise forms.ValidationError(_('Invalid ccv.'))

    def save(self, request, cart, contact, payment_module, data=None):
        """Save the order and the credit card information for this orderpayment"""
        form_presave.send(CreditPayShipForm, form=self)
        if data is None:
            data = self.cleaned_data
        assert(data)
        super(CreditPayShipForm, self).save(request, cart, contact, payment_module, data=data)

        if self.orderpayment:
            op = self.orderpayment.capture

            cc = CreditCardDetail(orderpayment=op,
                expire_month=data['month_expires'],
                expire_year=data['year_expires'],
                credit_type=data['credit_type'])

            cc.storeCC(data['credit_number'])
            cc.save()

            # set ccv into cache
            cc.ccv = data['ccv']
            self.cc = cc
        form_postsave.send(CreditPayShipForm, form=self)

        
class CreditCardDetailAdminForm(forms.ModelForm):
    credit_type = forms.ChoiceField()
    
    class Meta:
        model = CreditCardDetail
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super(CreditCardDetailAdminForm, self).__init__(*args, **kwargs)
        self.fields['credit_type'].choices = credit_choices()
