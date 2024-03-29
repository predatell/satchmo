from livesettings.values import StringValue,ConfigurationGroup,BooleanValue,ModuleValue,MultipleStringValue
from livesettings.functions import config_register_list
from django.utils.translation import gettext_lazy as _

# this is so that the translation utility will pick up the string
gettext = lambda s: s
_strings = (gettext('CreditCard'), gettext('Credit Card'), gettext('Sage Pay Secure Payments'))

# These cards require the issue number and start date fields filled in.
REQUIRES_ISSUE_NUMBER = ('MAESTRO', 'SOLO')

PAYMENT_GROUP = ConfigurationGroup('PAYMENT_SAGEPAY',
    _('Sage Pay Payment Settings'),
    ordering=101)

config_register_list(

    BooleanValue(PAYMENT_GROUP,
        'LIVE',
        description=_("Accept real payments"),
        help_text=_("False if you want to be in test mode"),
        default=False),

    BooleanValue(PAYMENT_GROUP,
        'SIMULATOR',
        description=_("Simulated Transactions?"),
        help_text=_("Must be false to accept real payments"),
        default=False),

    BooleanValue(PAYMENT_GROUP,
        'SKIP_POST',
        description=_("Skip post?"),
        help_text=_("For testing only, this will skip actually posting to Sage Pay servers.  This is because their servers restrict IPs of posting servers, even for tests.  If you are developing on a desktop, you'll have to enable this."),
        default=False),

    StringValue(PAYMENT_GROUP,
        'CAPTURE',
        description=_('Payment Capture'),
        help_text=_('This can be "Payment" which captures immediately, or "Deferred".  Note that you can only use the latter if you set option on your Sage pay account first.'),
        choices = (
            (('PAYMENT', 'Payment')),
            (('DEFERRED', 'Deferred')),
        ),
        default = 'PAYMENT'),


    ModuleValue(PAYMENT_GROUP,
        'MODULE',
        description=_('Implementation module'),
        hidden=True,
        default = 'payment.modules.sagepay'),

    StringValue(PAYMENT_GROUP,
        'KEY',
        description=_("Module key"),
        hidden=True,
        default = 'SAGEPAY'),

    StringValue(PAYMENT_GROUP,
        'LABEL',
        description=_('English name for this group on the checkout screens'),
        default = 'Sage Pay Secure Payments',
        dummy = _('Sage Pay Secure Payments'), # Force this to appear on po-files
        help_text = _('This will be passed to the translation utility')),

    MultipleStringValue(PAYMENT_GROUP,
        'CREDITCHOICES',
        description=_('Available credit cards'),
        choices = (
                (('VISA','Visa Credit/Debit')),
                (('UKE','Visa Electron')),
                (('DELTA','Delta')),
                #(('AMEX','American Express')),  # not always available
                #(('DC','Diners Club')), # not always available
                (('MC','Mastercard')),
                (('MAESTRO','UK Maestro')),
                (('SOLO','Solo')),
                (('JCB','JCB')),
            ),
        default = ('VISA', 'MC')),

    StringValue(PAYMENT_GROUP,
        'VENDOR',
        description=_('Your Vendor Name'),
        default="",
        help_text= _("This is used for Live and Test transactions.  Make sure to add your server IP address to VSP, or it won't work.")),

    StringValue(PAYMENT_GROUP,
        'VENDOR_SIMULATOR',
        description=_('Simulator Vendor Name'),
        default="",
        help_text= _("This is used for Live and Test transactions.  Make sure to activate the VSP Simulator (you have to directly request it) and add your server IP address to the VSP Simulator, or it won't work.")),

    StringValue(PAYMENT_GROUP,
        'CURRENCY_CODE',
        description=_('Currency Code'),
        help_text=_('Currency code for Sage Pay transactions.'),
        default = 'GBP'),

    StringValue(PAYMENT_GROUP,
        'URL_BASE',
        description=_('The url base used for constructing urlpatterns which will use this module'),
        default = r'^sagepay/'),

    BooleanValue(PAYMENT_GROUP,
        'EXTRA_LOGGING',
        description=_("Verbose logs"),
        help_text=_("Add extensive logs during post."),
        default=False)
)
