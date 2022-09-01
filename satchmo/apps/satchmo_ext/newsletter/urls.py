"""
URLConf for Satchmo Newsletter app

This will get automatically added by satchmo_store, under the url given in your livesettings "NEWSLETTER","NEWSLETTER_SLUG"
"""

from django.urls import re_path, include

from livesettings.functions import config_value_safe
from . import views
import logging

log = logging.getLogger('newsletter.urls')

urlpatterns = [
    re_path(r'^subscribe/$', views.add_subscription, name='newsletter_subscribe'),
    re_path(r'^subscribe/ajah/$', views.add_subscription,
            {'result_template': 'newsletter/ajah.html'}, name='newsletter_subscribe_ajah'),
    re_path(r'^unsubscribe/$', views.remove_subscription, name='newsletter_unsubscribe'),
    re_path(r'^unsubscribe/ajah/$', views.remove_subscription,
            {'result_template': 'newsletter/ajah.html'}, name='newsletter_unsubscribe_ajah'),
    re_path(r'^update/$', views.update_subscription, name='newsletter_update'),
]


def add_newsletter_urls(sender, patterns=(), **kwargs):
    newsbase = r'^' + config_value_safe('NEWSLETTER', 'NEWSLETTER_SLUG', "newsletter") + '/'
    log.debug("Adding newsletter urls at %s", newsbase)
    newspatterns = [
        re_path(newsbase, include('satchmo_ext.newsletter.urls'))
    ]
    patterns += newspatterns
