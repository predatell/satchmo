from payment.modules.giftcertificate.models import GiftCertificate, GiftCertificateUsage, GiftCertificateProduct
from django.contrib import admin
from django.utils.translation import get_language, gettext_lazy as _


class GiftCertificateUsage_Inline(admin.StackedInline):
    model = GiftCertificateUsage
    extra = 1

class GiftCertificateOptions(admin.ModelAdmin):
    list_display = ['site', 'purchased_by','code','balance', 'date_added']
    list_display_links = ('code',)
    ordering = ['site', 'date_added']
    inlines = [GiftCertificateUsage_Inline]

admin.site.register(GiftCertificate, GiftCertificateOptions)
admin.site.register(GiftCertificateProduct)

