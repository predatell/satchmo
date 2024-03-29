#
#   SERMEPA / ServiRed payments module for Satchmo
#
#   Author: Michal Salaban <michal (at) salaban.info>
#   with a great help of Fluendo S.A., Barcelona
#
#   Based on "Guia de comercios TPV Virtual SIS" ver. 5.18, 15/11/2008, SERMEPA
#   For more information about integration look at http://www.sermepa.es/
#
#   TODO: SERMEPA interface provides possibility of recurring payments, which
#   could be probably used for SubscriptionProducts. This module doesn't support it.
#
from decimal import Decimal
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound, HttpResponseBadRequest
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.views.decorators.cache import never_cache
try:
    from django.core.urlresolvers import NoReverseMatch
except ImportError:
    from django.urls import NoReverseMatch
    
from livesettings.functions import config_get_group, config_value
from payment.utils import get_processor_by_key
from payment.views import payship
from satchmo_store.shop.models import Order, Cart
from satchmo_store.shop.satchmo_settings import get_satchmo_setting
from satchmo_utils.dynamic import lookup_url, lookup_template
from django.views.decorators.csrf import csrf_exempt  
from satchmo_utils.views import bad_or_missing

import logging
try:
    from hashlib import sha1
except ImportError:
    # python < 2.5
    from sha import sha as sha1

log = logging.getLogger()

def pay_ship_info(request):
    return payship.base_pay_ship_info(
            request,
            config_get_group('PAYMENT_SERMEPA'), payship.simple_pay_ship_process_form,
            'shop/checkout/sermepa/pay_ship.html'
            )
pay_ship_info = never_cache(pay_ship_info)


def _resolve_local_url(payment_module, cfgval, ssl=False):
    try:
        return lookup_url(payment_module, cfgval.value, include_server=True, ssl=ssl)
    except NoReverseMatch:
        return cfgval.value


def confirm_info(request):
    payment_module = config_get_group('PAYMENT_SERMEPA')

    try:
        order = Order.objects.from_request(request)
    except Order.DoesNotExist:
        url = lookup_url(payment_module, 'satchmo_checkout-step1')
        return HttpResponseRedirect(url)

    tempCart = Cart.objects.from_request(request)
    if tempCart.numItems == 0:
        template = lookup_template(payment_module, 'shop/checkout/empty_cart.html')
        return render(request, template)

    # Check if the order is still valid
    if not order.validate(request):
        return render(request, 'shop/404.html', {'message': _('Your order is no longer valid.')})

    # Check if we are in test or real mode
    live = payment_module.LIVE.value
    if live:
        post_url = payment_module.POST_URL.value
        signature_code = payment_module.MERCHANT_SIGNATURE_CODE.value
        terminal = payment_module.MERCHANT_TERMINAL.value
    else:
        post_url = payment_module.POST_TEST_URL.value
        signature_code = payment_module.MERCHANT_TEST_SIGNATURE_CODE.value
        terminal = payment_module.MERCHANT_TEST_TERMINAL.value

    # SERMEPA system does not accept multiple payment attempts with the same ID, even
    # if the previous one has never been finished. The worse is that it does not display
    # any message which could be understood by an end user.
    #
    # If user goes to SERMEPA page and clicks 'back' button (e.g. to correct contact data),
    # the next payment attempt will be rejected.
    #
    # To provide higher probability of ID uniqueness, we add mm:ss timestamp part
    # to the order id, separated by 'T' character in the following way:
    #
    #   ID: oooooooTmmss
    #   c:  123456789012
    #
    # The Satchmo's Order number is therefore limited to 10 million - 1.
    now = timezone.now()
    xchg_order_id = "%07dT%02d%02d" % (order.id, now.minute, now.second)

    amount = "%d" % (order.balance * 100,)    # in cents

    template = lookup_template(payment_module, 'shop/checkout/sermepa/confirm.html')

    url_callback = _resolve_local_url(payment_module, payment_module.MERCHANT_URL_CALLBACK, ssl=get_satchmo_setting('SSL'))
    url_ok = _resolve_local_url(payment_module, payment_module.MERCHANT_URL_OK)
    url_ko = _resolve_local_url(payment_module, payment_module.MERCHANT_URL_KO)

    if payment_module.EXTENDED_SIGNATURE.value:
        signature_data = ''.join(
                map(str, (
                        amount,
                        xchg_order_id,
                        payment_module.MERCHANT_FUC.value,
                        payment_module.MERCHANT_CURRENCY.value,
                        "0", #TransactionType
                        url_callback,
                        signature_code,
                        )
                   )
                )
    else:
        signature_data = ''.join(
                map(str, (
                        amount,
                        xchg_order_id,
                        payment_module.MERCHANT_FUC.value,
                        payment_module.MERCHANT_CURRENCY.value,
                        signature_code,
                        )
                   )
                )

    signature = sha1(signature_data).hexdigest()
    ctx = {
        'live': live,
        'post_url': post_url,
        'MERCHANT_CURRENCY': payment_module.MERCHANT_CURRENCY.value,
        'MERCHANT_FUC': payment_module.MERCHANT_FUC.value,
        'terminal': terminal,
        'MERCHANT_TITULAR': payment_module.MERCHANT_TITULAR.value,
        'url_callback': url_callback,
        'url_ok': url_ok,
        'url_ko': url_ko,
        'order': order,
        'xchg_order_id' : xchg_order_id,
        'amount': amount,
        'signature': signature,
        'default_view_tax': config_value('TAX', 'DEFAULT_VIEW_TAX'),
    }
    return render(request, template, ctx)
confirm_info = never_cache(confirm_info)

@csrf_exempt
def notify_callback(request):
    payment_module = config_get_group('PAYMENT_SERMEPA')
    if payment_module.LIVE.value:
        log.debug("Live IPN on %s", payment_module.KEY.value)
        signature_code = payment_module.MERCHANT_SIGNATURE_CODE.value
        terminal = payment_module.MERCHANT_TERMINAL.value
    else:
        log.debug("Test IPN on %s", payment_module.KEY.value)
        signature_code = payment_module.MERCHANT_TEST_SIGNATURE_CODE.value
        terminal = payment_module.MERCHANT_TEST_TERMINAL.value
    data = request.POST
    log.debug("Transaction data: " + repr(data))
    try:
        sig_data = "%s%s%s%s%s%s" % (
                data['Ds_Amount'],
                data['Ds_Order'],
                data['Ds_MerchantCode'],
                data['Ds_Currency'],
                data['Ds_Response'],
                signature_code
                )
        sig_calc = sha1(sig_data).hexdigest()
        if sig_calc != data['Ds_Signature'].lower():
            log.error("Invalid signature. Received '%s', calculated '%s'." % (data['Ds_Signature'], sig_calc))
            return HttpResponseBadRequest("Checksum error")
        if data['Ds_MerchantCode'] != payment_module.MERCHANT_FUC.value:
            log.error("Invalid FUC code: %s" % data['Ds_MerchantCode'])
            return HttpResponseNotFound("Unknown FUC code")
        if int(data['Ds_Terminal']) != int(terminal):
            log.error("Invalid terminal number: %s" % data['Ds_Terminal'])
            return HttpResponseNotFound("Unknown terminal number")
        # TODO: fields Ds_Currency, Ds_SecurePayment may be worth checking

        xchg_order_id = data['Ds_Order']
        try:
            order_id = xchg_order_id[:xchg_order_id.index('T')]
        except ValueError:
            log.error("Incompatible order ID: '%s'" % xchg_order_id)
            return HttpResponseNotFound("Order not found")
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            log.error("Received data for nonexistent Order #%s" % order_id)
            return HttpResponseNotFound("Order not found")
        amount = Decimal(data['Ds_Amount']) / Decimal('100')    # is in cents, divide it
        if int(data['Ds_Response']) > 100:
            log.info("Response code is %s. Payment not accepted." % data['Ds_Response'])
            return HttpResponse()
    except KeyError:
        log.error("Received incomplete SERMEPA transaction data")
        return HttpResponseBadRequest("Incomplete data")
    # success
    order.add_status(status='New', notes="Paid through SERMEPA.")
    processor = get_processor_by_key('PAYMENT_SERMEPA')
    payment = processor.record_payment(
        order=order,
        amount=amount,
        transaction_id=data['Ds_AuthorisationCode'])
    # empty customer's carts
    for cart in Cart.objects.filter(customer=order.contact):
        cart.empty()
    return HttpResponse()
    

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
        product.items_in_stock -= item.quantity
        product.save()

    log.warning(_('The contact is %s') % order.contact)
    # Clean up cart now, the rest of the order will be cleaned on paypal IPN
    for cart in Cart.objects.filter(customer=order.contact):
        log.warning(_('Processing cart item %s') % cart.pk)
        cart.empty()

    del request.session['orderID']
    log.warning(request.session)
    return render(request, 'shop/checkout/success.html', {'order': order})

success = never_cache(success)




