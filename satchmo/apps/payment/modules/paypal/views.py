from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
try:
    from django.core.urlresolvers import NoReverseMatch
except ImportError:
    from django.urls import NoReverseMatch
    
from livesettings.functions import config_get_group, config_value
from payment.config import gateway_live
from payment.utils import get_processor_by_key
from payment.views import payship
from satchmo_store.shop.models import Cart
from satchmo_store.shop.models import Order, OrderPayment
from satchmo_store.contact.models import Contact
from satchmo_utils.dynamic import lookup_url, lookup_template
from satchmo_utils.views import bad_or_missing
from six.moves import urllib
from sys import exc_info
from traceback import format_exception
import logging
from django.views.decorators.csrf import csrf_exempt


log = logging.getLogger('payment.modules.paypal.views')

def pay_ship_info(request):
    return payship.base_pay_ship_info(request,
        config_get_group('PAYMENT_PAYPAL'), payship.simple_pay_ship_process_form,
        'shop/checkout/paypal/pay_ship.html')
pay_ship_info = never_cache(pay_ship_info)


def confirm_info(request):
    payment_module = config_get_group('PAYMENT_PAYPAL')

    try:
        order = Order.objects.from_request(request)
    except Order.DoesNotExist:
        url = lookup_url(payment_module, 'satchmo_checkout-step1')
        return HttpResponseRedirect(url)

    tempCart = Cart.objects.from_request(request)
    if tempCart.numItems == 0 and not order.is_partially_paid:
        template = lookup_template(payment_module, 'shop/checkout/empty_cart.html')
        return render(request, template)

    # Check if the order is still valid
    if not order.validate(request):
        return render(request, 'shop/404.html', {'message': _('Your order is no longer valid.')})

    template = lookup_template(payment_module, 'shop/checkout/paypal/confirm.html')
    if payment_module.LIVE.value:
        log.debug("live order on %s", payment_module.KEY.value)
        url = payment_module.POST_URL.value
        account = payment_module.BUSINESS.value
    else:
        url = payment_module.POST_TEST_URL.value
        account = payment_module.BUSINESS_TEST.value

    try:
        address = lookup_url(payment_module,
            payment_module.RETURN_ADDRESS.value, include_server=True)
    except NoReverseMatch:
        address = payment_module.RETURN_ADDRESS.value

    try:
        cart = Cart.objects.from_request(request)
    except:
        cart = None
    try:
        contact = Contact.objects.from_request(request)
    except:
        contact = None
    if cart and contact:
        cart.customer = contact
        log.debug(':::Updating Cart %s for %s' % (cart, contact))
        cart.save()

    processor_module = payment_module.MODULE.load_module('processor')
    processor = processor_module.PaymentProcessor(payment_module)
    processor.create_pending_payment(order=order)
    default_view_tax = config_value('TAX', 'DEFAULT_VIEW_TAX')

    recurring = None

    # Run only if subscription products are installed
    if 'product.modules.subscription' in settings.INSTALLED_APPS:
        order_items = order.orderitem_set.all()
        for item in order_items:
            if not item.product.is_subscription:
                continue

            if item.product.has_variants:
                price = item.product.productvariation.get_qty_price(item.quantity, True)
            else:
                price = item.product.get_qty_price(item.quantity, True)
            recurring = {'product':item.product, 'price':price.quantize(Decimal('.01'))}
            trial0 = recurring['product'].subscriptionproduct.get_trial_terms(0)
            if len(order_items) > 1 or trial0 is not None or recurring['price'] < order.balance:
                recurring['trial1'] = {'price': order.balance,}
                if trial0 is not None:
                    recurring['trial1']['expire_length'] = trial0.expire_length
                    recurring['trial1']['expire_unit'] = trial0.subscription.expire_unit[0]
                # else:
                #     recurring['trial1']['expire_length'] = recurring['product'].subscriptionproduct.get_trial_terms(0).expire_length
                trial1 = recurring['product'].subscriptionproduct.get_trial_terms(1)
                if trial1 is not None:
                    recurring['trial2']['expire_length'] = trial1.expire_length
                    recurring['trial2']['expire_unit'] = trial1.subscription.expire_unit[0]
                    recurring['trial2']['price'] = trial1.price

    ctx = {'order': order,
     'post_url': url,
     'default_view_tax': default_view_tax,
     'business': account,
     'currency_code': payment_module.CURRENCY_CODE.value,
     'return_address': address,
     'invoice': order.id,
     'subscription': recurring,
     'PAYMENT_LIVE' : gateway_live(payment_module)
    }

    return render(request, template, ctx)
confirm_info = never_cache(confirm_info)

@csrf_exempt
def ipn(request):
    """PayPal IPN (Instant Payment Notification)
    Cornfirms that payment has been completed and marks invoice as paid.
    Adapted from IPN cgi script provided at http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/456361"""
    payment_module = config_get_group('PAYMENT_PAYPAL')
    if payment_module.LIVE.value:
        log.debug("Live IPN on %s", payment_module.KEY.value)
        url = payment_module.POST_URL.value
        account = payment_module.BUSINESS.value
    else:
        log.debug("Test IPN on %s", payment_module.KEY.value)
        url = payment_module.POST_TEST_URL.value
        account = payment_module.BUSINESS_TEST.value
    PP_URL = url

    try:
        data = request.POST
        log.debug("PayPal IPN data: " + repr(data))
        if not confirm_ipn_data(request.body, PP_URL):
            return HttpResponse()

        if not 'payment_status' in data or not data['payment_status'] == "Completed":
            # We want to respond to anything that isn't a payment - but we won't insert into our database.
             log.info("Ignoring IPN data for non-completed payment.")
             return HttpResponse()

        try:
            invoice = data['invoice']
        except:
            invoice = data['item_number']

        gross = data['mc_gross']
        txn_id = data['txn_id']

        if not OrderPayment.objects.filter(transaction_id=txn_id).count():
            # If the payment hasn't already been processed:
            order = Order.objects.get(pk=invoice)

            order.add_status(status='New', notes=_("Paid through PayPal."))
            processor = get_processor_by_key('PAYMENT_PAYPAL')
            payment = processor.record_payment(order=order, amount=gross, transaction_id=txn_id)

            if 'memo' in data:
                if order.notes:
                    notes = order.notes + "\n"
                else:
                    notes = ""

                order.notes = notes + _('---Comment via Paypal IPN---') + '\n' + data['memo']
                order.save()
                log.debug("Saved order notes from Paypal")

            # Run only if subscription products are installed
            if 'product.modules.subscription' in settings.INSTALLED_APPS:
                for item in order.orderitem_set.filter(product__subscriptionproduct__recurring=True, completed=False):
                    item.completed = True
                    item.save()
            # We no longer empty the cart here. We do it on checkout success.

    except:
        log.exception(''.join(format_exception(*exc_info())))

    return HttpResponse()

def confirm_ipn_data(query_string, PP_URL):
    # data is the form data that was submitted to the IPN URL.

    params = b'cmd=_notify-validate&' + query_string

    req = urllib.request.Request(PP_URL)
    req.add_header("Content-type", "application/x-www-form-urlencoded")
    req.add_header("user-agent", "Python-IPN-Verification-Script")
    fo = urllib.request.urlopen(req, params)

    ret = fo.read()
    if ret.decode() == "VERIFIED":
        log.info("PayPal IPN data verification was successful.")
    else:
        log.info("PayPal IPN data verification failed.")
        log.debug("HTTP code %s, response text: '%s'" % (fo.code, ret))
        return False

    return True


def success(request):
    """
    The order has been succesfully processed.
    We clear out the cart but let the payment processing get called by IPN
    """
    try:
        order = Order.objects.from_request(request)
    except Order.DoesNotExist:
        return bad_or_missing(request, _('Your order has already been processed.'))

    # Added to track total sold for each product
    for item in order.orderitem_set.all():
        product = item.product
        product.total_sold += item.quantity
        if config_value('PRODUCT','TRACK_INVENTORY'):
            product.items_in_stock -= item.quantity
        product.save()

    # Clean up cart now, the rest of the order will be cleaned on paypal IPN
    for cart in Cart.objects.filter(customer=order.contact):
        cart.empty()

    del request.session['orderID']
    return render(request, 'shop/checkout/success.html', {'order': order})

success = never_cache(success)
