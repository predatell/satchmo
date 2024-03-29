from livesettings.values import StringValue,ConfigurationGroup,BooleanValue,DecimalValue,PositiveIntegerValue,ModuleValue,MultipleStringValue,LongStringValue
from livesettings.functions import config_register_list
from django.utils.translation import gettext_lazy as _

PAYMENT_GROUP = ConfigurationGroup('PAYMENT_GIFTCERTIFICATE',
    _('Gift Certificate Settings'))

config_register_list(
    StringValue(PAYMENT_GROUP,
        'CHARSET',
        description=_("Character Set"),
        default="BCDFGHKPRSTVWXYZbcdfghkprstvwxyz23456789",
        help_text=_("The characters allowable in randomly-generated certficate codes.  No vowels means no unfortunate words.")),

    StringValue(PAYMENT_GROUP,
        'KEY',
        description=_("Module key"),
        hidden=True,
        default = 'GIFTCERTIFICATE'),

    StringValue(PAYMENT_GROUP,
        'FORMAT',
        description=_('Code format'),
        default="^^^^-^^^^-^^^^",
        help_text=_("Enter the format for your cert code.  Use a '^' for the location of a randomly generated character.")),

    ModuleValue(PAYMENT_GROUP,
        'MODULE',
        description=_('Implementation module'),
        hidden=True,
        default = 'payment.modules.giftcertificate'),

    StringValue(PAYMENT_GROUP,
        'LABEL',
        description=_('English name for this group on the checkout screens'),
        default = 'Gift Certificate',
        dummy = _('Gift Certificate'), # Force this to appear on po-files
        help_text = _('This will be passed to the translation utility')),

    BooleanValue(PAYMENT_GROUP,
        'LIVE',
        description=_("Accept real payments"),
        help_text=_("False if you want to be in test mode"),
        default=False),

    BooleanValue(PAYMENT_GROUP,
        'EMAIL_RECIPIENT',
        description=_("Send email to recipients"),
        help_text=_("If the purchaser includes an email address, should we send a notification to them?"),
        default=True),

    StringValue(PAYMENT_GROUP,
        'URL_BASE',
        description=_('The url base used for constructing urlpatterns which will use this module'),
        default = r'^giftcertificate/'),

    BooleanValue(PAYMENT_GROUP,
        'EXTRA_LOGGING',
        description=_("Verbose logs"),
        help_text=_("Add extensive logs during post."),
        default=False)
)
