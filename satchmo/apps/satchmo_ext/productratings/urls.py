"""urlpatterns for productratings.  Note that you do not need to add these to your urls anywhere, they'll be automatically added by the collect_urls signals."""
from django.conf import settings
from django.urls import re_path, include

from satchmo_ext.productratings.views import BestratingsListView
import logging

log = logging.getLogger('productratings.urls')

productpatterns = [
    re_path(r'^view/bestrated/$', BestratingsListView.as_view(), name='satchmo_product_best_rated'),
]

# Override comments with our redirecting view. You can remove the next two
# URLs if you aren't using ratings.
# (r'^comments/post/$', 'comments.post_rating', {'maxcomments': 1 }, 'satchmo_rating_post'),
if 'django_comments' in settings.INSTALLED_APPS:
    comment_urls = 'django_comments.urls'
else:
    comment_urls = 'django.contrib.comments.urls'

commentpatterns = [
    re_path(r'^comments/', include(comment_urls)),
]


def add_product_urls(sender, patterns=(), section="", **kwargs):
    if section == "product":
        log.debug('adding ratings urls')
        patterns += productpatterns


def add_comment_urls(sender, patterns=(), **kwargs):
    log.debug('adding comments urls')
    patterns += commentpatterns
