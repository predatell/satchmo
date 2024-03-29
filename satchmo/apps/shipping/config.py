from django.utils.translation import gettext_lazy as _
from livesettings.values import StringValue,ConfigurationGroup, BooleanValue, MultipleStringValue
from livesettings.functions import config_register, config_value
from satchmo_store.shop import get_satchmo_setting
from satchmo_utils import load_module
import logging

log = logging.getLogger('shipping.config')

SHIPPING_GROUP = ConfigurationGroup('SHIPPING', _('Shipping Settings'))

SHIPPING_ACTIVE = config_register(MultipleStringValue(SHIPPING_GROUP,
    'MODULES',
    description=_("Active shipping modules"),
    help_text=_("Select the active shipping modules, save and reload to set any module-specific shipping settings."),
    default=["shipping.modules.per"],
    choices=[('shipping.modules.per', _('Per piece'))],
    ordering=0
    ))

config_register(
    StringValue(SHIPPING_GROUP,
        'HIDING',
        description = _("Hide if one?"),
        help_text = _("Hide shipping form fields if there is only one choice available?"),
        default='NO',
        ordering=10,
        choices = (
            ('NO', _('No')),
            ('YES', _('Yes')),
            ('DESCRIPTION', _('Show description only'))
        )))

config_register(
    BooleanValue(SHIPPING_GROUP,
        'DOWNLOAD_PDFS',
        description = _("Download PDFs from admin page"),
        default=True,
        ordering=5
        ))

config_register(
    BooleanValue(SHIPPING_GROUP,
        'SELECT_CHEAPEST',
        description = _("Select least expensive by default?"),
        default=True,
        ordering=15
        ))


# --- Load default shipping modules.  Ignore import errors, user may have deleted them. ---
# DO NOT ADD 'tiered' or 'no' to this list.
# 'no' is used internally
# 'Tiered' is special, since it needs to be added as a module.  To enable it,
# just add shipping.modules.tiered to your INSTALLED_APPS
_default_modules = ('canadapost', 'dummy', 'fedex_web_services', 'flat', 'per', 'ups', 'usps')

for module in _default_modules:
    try:
        load_module("shipping.modules.%s.config" % module)
    except ImportError:
        log.debug('Could not load default shipping module configuration: %s', module)

# --- Load any extra shipping modules. ---
extra_shipping = get_satchmo_setting('CUSTOM_SHIPPING_MODULES')

for extra in extra_shipping:
    try:
        load_module("%s.config" % extra)
    except ImportError:
        log.warn('Could not load shipping module configuration: %s' % extra)

class ShippingModuleNotFound(Exception):
    def __init__(self, key):
        self.key = key

def shipping_methods():
    methods = []
    modules = config_value('SHIPPING', 'MODULES')
    log.debug('Getting shipping methods: %s', modules)
    for m in modules:
        module = load_module(".".join([m, 'methods']))
        methods.extend(module.get_methods())
    return methods

def shipping_method_by_key(key):
    if key and key != "NoShipping":
        for method in shipping_methods():
            if method.id == key:
                return method
    else:
        import shipping.modules.no.shipper as noship
        method = noship.Shipper()

    if method:
        return method
    else:
        raise ShippingModuleNotFound(key)


def shipping_choices():
    choices = []
    keys = []
    for method in shipping_methods():
        key = method.id
        label = method.description()
        choices.append((key, label))
    return choices
