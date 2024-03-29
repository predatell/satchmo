from decimal import Decimal
from livesettings.functions import config_get_group, config_value
from satchmo_store.shop.models import Order, OrderItem, OrderItemDetail, OrderCart, NullCart
from satchmo_store.shop.signals import satchmo_post_copy_item_to_order
from shipping.utils import update_shipping
from satchmo_store.mail import send_store_mail
from django.utils.translation import gettext as _
import logging

log = logging.getLogger('payment.utils')

def capture_authorizations(order):
    """Capture all outstanding authorizations on this order"""
    if order.authorized_remaining > Decimal('0'):
        for authz in order.authorizations.filter(complete=False):
            processor = get_processor_by_key('PAYMENT_%s' % authz.payment)
            processor.capture_authorized_payments(order)

def get_or_create_order(request, working_cart, contact, data):
    """Get the existing order from the session, else create using
    the working_cart, contact and data"""
    shipping = data.get('shipping', None)
    discount = data.get('discount', None)
    notes = data.get('notes', None)

    try:
        order = Order.objects.from_request(request)
        if order.status != '':
            # This order is being processed. We should not touch it!
            order = None
    except Order.DoesNotExist:
        order = None

    update = bool(order)
    if order:
        # make sure to copy/update addresses - they may have changed
        order.copy_addresses()
        order.save()
        if discount is None and order.discount_code:
            discount = order.discount_code
    else:
        # Create a new order.
        order = Order(contact=contact)

    pay_ship_save(order, working_cart, contact,
        shipping=shipping, discount=discount, notes=notes, update=update)
    request.session['orderID'] = order.id
    return order

def get_processor_by_key(key):
    """
    Returns an instance of a payment processor, referred to by *key*.

    :param key: A string of the form 'PAYMENT_<PROCESSOR_NAME>'.
    """
    payment_module = config_get_group(key)
    processor_module = payment_module.MODULE.load_module('processor')
    return processor_module.PaymentProcessor(payment_module)

def pay_ship_save(new_order, cart, contact, shipping, discount, notes, update=False):
    """
    Save the order details, first removing all items if this is an update.
    """
    if shipping:
        update_shipping(new_order, shipping, contact, cart)

    if not update:
        # Temp setting of the tax and total so we can save it
        new_order.total = Decimal('0.00')
        new_order.tax = Decimal('0.00')
        new_order.sub_total = cart.total
        new_order.method = 'Online'

    if discount:
        new_order.discount_code = discount
    else:
        new_order.discount_code = ""
    if notes:
        new_order.notes = notes
    update_orderitems(new_order, cart, update=update)

def update_orderitem_details(new_order_item, item):
    """Update orderitem details, if any.
    """
    if item.has_details:
        # Check to see if cartitem has CartItemDetails
        # If so, add here.
        #obj = CustomTextField.objects.get(id=item.details.values()[0]['customfield_id'])
        #val = item.details.values()[0]['detail']
        for detail in item.details.all():
            new_details = OrderItemDetail(item=new_order_item,
                value=detail.value,
                name=detail.name,
                price_change=detail.price_change,
                sort_order=detail.sort_order)
            new_details.save()


def update_orderitem_for_subscription(new_order_item, item):
    """Update orderitem subscription details, if any.
    """
    #if product is recurring, set subscription end
    #if item.product.expire_length:
    if item.product.is_subscription:
        subscription = item.product.subscriptionproduct
        if subscription.expire_length:
            new_order_item.expire_date = subscription.calc_expire_date()
    else:
        subscription = None

    #if product has trial price, set it here and update expire_date with trial period.
    trial = None

    if subscription:
        trial = subscription.get_trial_terms()

    if trial:
        trial1 = trial[0]
        new_order_item.unit_price = trial1.price
        new_order_item.line_item_price = new_order_item.quantity * new_order_item.unit_price
        new_order_item.expire_date = trial1.calc_expire_date()

    new_order_item.save()


def update_orderitems(new_order, cart, update=False):
    """Update the order with all cart items, first removing all items if this
    is an update.
    """
    if not isinstance(cart, OrderCart) and not isinstance(cart, NullCart):
        if update:
            new_order.remove_all_items()
        else:
            # have to save first, or else we can't add orderitems
            new_order.site = cart.site
            new_order.save()

        # Add all the items in the cart to the order
        for item in cart.cartitem_set.all():
            new_order_item = OrderItem(order=new_order,
                product=item.product,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_item_price=item.line_total)

            update_orderitem_for_subscription(new_order_item, item)
            update_orderitem_details(new_order_item, item)

            # Send a signal after copying items
            # External applications can copy their related objects using this
            satchmo_post_copy_item_to_order.send(
                    cart,
                    cartitem=item,
                    order=new_order, orderitem=new_order_item
                    )
            
    new_order.recalculate_total()

def send_gift_certificate_by_email(gc):
    """ Helper function to send email messages to gift certificate recipients
    """
    ctx = {
        'message': gc.message,
        'addressee': gc.recipient_email,
        'code': gc.code,
        'balance':gc.balance,
        'purchased_by': gc.purchased_by
        }
    subject = _('Your Gift Certificate')

    send_store_mail(
        subject,
        ctx,
        template = 'shop/email/gift_certificate_recipient.txt',
        template_html='shop/email/gift_certificate_recipient.html',
        recipients_list=[gc.recipient_email,],
        fail_silently=True,
        )

def gift_certificate_processor(order):
    """ If an order has gift certificates, then we'll try to send emails to the recipients
    """
    from payment.modules.giftcertificate.models import GiftCertificate
    email_sent = False
    send_email = config_value('PAYMENT_GIFTCERTIFICATE','EMAIL_RECIPIENT')
    if send_email:
        gcs = GiftCertificate.objects.filter(order=order)
        for gc in gcs:
            if gc.recipient_email:
                send_gift_certificate_by_email(gc)
                email_sent = True
    return email_sent
