from django import forms
from django.utils.translation import gettext, gettext_lazy as _
try:
    from django.core.urlresolvers import reverse, NoReverseMatch
except ImportError:
    from django.urls import reverse, NoReverseMatch
from payment.utils import capture_authorizations
import logging

log = logging.getLogger('payment.listeners')

def form_terms_listener(sender, form=None, **kwargs):
    """Adds a 'do you accept the terms and conditions' checkbox to the form"""

    try:
        url = reverse('shop_terms')
    except NoReverseMatch:
        log.warn('To use the form_terms_listener, you must have a "shop_terms" url in your site urls')
        url = "#"
        
    link = '<a target="_blank" href="%s">%s</a>' % (url,gettext('terms and conditions'))
    form.fields['terms'] = forms.BooleanField(
        label=_('Do you accept the %(terms_link)s?') % {'terms_link' : link}, 
        widget=forms.CheckboxInput(), required=True)

def shipping_hide_if_one(sender, form=None, **kwargs):
    """Makes the widget for shipping hidden if there is only one choice."""

    log.warn("shipping_hide_if_one listener is deprecated, please configure this in your site settings in the shipping section.")
    
def capture_on_ship_listener(sender, oldstatus="", newstatus="", order=None, **kwargs):
    """Listen for a transition to 'shipped', and capture authorizations."""

    log.debug('heard satchmo_order_status_changed, %s=%s', oldstatus, newstatus)
    if oldstatus != 'Shipped' and newstatus == 'Shipped':
        capture_authorizations(order)
