from livesettings.values import StringValue,ConfigurationGroup,BooleanValue,DecimalValue,ModuleValue
from livesettings.functions import config_register_list
from django.utils.translation import gettext_lazy as _

# this is so that the translation utility will pick up the string
gettext = lambda s: s

PAYMENT_GROUP = ConfigurationGroup('PAYMENT_COD',
    _('COD Payment Module Settings'),
    ordering = 100)

config_register_list(
    BooleanValue(PAYMENT_GROUP,
        'LIVE',
        description=_("Accept real payments"),
        help_text=_("False if you want to be in test mode"),
        default=False),


    ModuleValue(PAYMENT_GROUP,
        'MODULE',
        description=_('Implementation module'),
        hidden=True,
        default = 'payment.modules.cod'),

    StringValue(PAYMENT_GROUP,
        'KEY',
        description=_("Module key"),
        hidden=True,
        default = 'COD'),

    StringValue(PAYMENT_GROUP,
        'LABEL',
        description=_('English name for this group on the checkout screens'),
        default = 'COD Payment',
        dummy = _('COD Payment'), # Force this to appear on po-files
        help_text = _('This will be passed to the translation utility')),

    StringValue(PAYMENT_GROUP,
        'URL_BASE',
        description=_('The url base used for constructing urlpatterns which will use this module'),
        default = '^cod/'),

    BooleanValue(PAYMENT_GROUP,
        'EXTRA_LOGGING',
        description=_("Verbose logs"),
        help_text=_("Add extensive logs during post."),
        default=False)
)
