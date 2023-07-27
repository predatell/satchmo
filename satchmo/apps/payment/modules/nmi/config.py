from livesettings.values import StringValue,ConfigurationGroup,BooleanValue,DecimalValue,ModuleValue,MultipleStringValue
from livesettings.functions import config_register,config_register_list
from django.utils.translation import gettext_lazy as _

# this is so that the translation utility will pick up the string
gettext = lambda s: s
_strings = (gettext('nmi'), gettext('NMI'))

PAYMENT_GROUP = ConfigurationGroup('PAYMENT_NMI',
    _('NMI Payment Settings'),
    ordering=101)

config_register_list(

    StringValue(PAYMENT_GROUP,
        'CONNECTION',
        description=_("Submit to URL"),
        help_text=_("""This is the address to submit live transactions."""),
        default='https://secure.nmi.com/api/transact.php'),

    BooleanValue(PAYMENT_GROUP,
        'LIVE',
        description=_("Accept real payments"),
        help_text=_("False if you want to be in test mode"),
        default=False),

    BooleanValue(PAYMENT_GROUP,
        'SIMULATE',
        description=_("Force a test post?"),
        help_text=_("True if you want to submit to the live url using a test flag, which won't be accepted."),
        default=False),

    ModuleValue(PAYMENT_GROUP,
        'MODULE',
        description=_('Implementation module'),
        hidden=True,
        default = 'payment.modules.nmi'),

    StringValue(PAYMENT_GROUP,
        'KEY',
        description=_("Module key"),
        hidden=True,
        default = 'NMI'),

    StringValue(PAYMENT_GROUP,
        'LABEL',
        description=_('English name for this group on the checkout screens'),
        default = 'Credit Cards (NMI)',
        dummy = _('Credit Cards (NMI)'), # Force this to appear on po-files
        help_text = _('This will be passed to the translation utility')),

    StringValue(PAYMENT_GROUP,
        'TRANKEY',
        description=_('Your NMI security key'),
        default=""),

    StringValue(PAYMENT_GROUP,
        'TEST_TRANKEY',
        description=_('Your TEST NMI security key'),
        default="6457Thfj624V5r7WUwc5v6a68Zsd6YEm"),

    StringValue(PAYMENT_GROUP,
        'URL_BASE',
        description=_('The url base used for constructing urlpatterns which will use this module'),
        default = r'^credit-nmi/'),

    MultipleStringValue(PAYMENT_GROUP,
        'CREDITCHOICES',
        description=_('Available credit cards'),
        choices = (
            (('American Express', 'American Express')),
            (('Visa','Visa')),
            (('Mastercard','Mastercard')),
            (('Discover','Discover'))),
        default = ('American Express', 'Visa', 'Mastercard', 'Discover')),

    BooleanValue(PAYMENT_GROUP,
        'EXTRA_LOGGING',
        description=_("Verbose logs"),
        help_text=_("Add extensive logs during post."),
        default=False),

    BooleanValue(PAYMENT_GROUP,
        'ARB',
        description=_('Enable ARB?'),
        default=False,
        help_text=_('Enable ARB processing for setting up subscriptions.')),

)
