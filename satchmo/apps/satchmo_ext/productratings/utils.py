from django.conf import settings
from six.moves import reduce
try:
    from django.contrib.comments.models import Comment
except ImportError:
    from django_comments.models import Comment
from django.contrib.sites.models import Site
from django.db.models import Avg
from django.utils.translation import ugettext_lazy as _
from satchmo_ext.productratings.models import ProductRating
import logging
import operator

log = logging.getLogger('product.comments.utils')

def average(ratings):
    """ Average a list of numbers, return None if it fails """
    if ratings:
        ratings = list(filter(lambda x: x is not None, ratings))
    if ratings:
        total = reduce(operator.add, ratings)
        if total != None:
            return float(total)/len(ratings)
    return None

def get_product_rating(product, site=None):
    """Get the average product rating"""
    if site is None:
        site = Site.objects.get_current()

    rating = ProductRating.objects.filter(comment__object_pk=product.pk,
                                          comment__content_type__app_label='product',
                                          comment__content_type__model='product',
                                          comment__site__id=site.pk, comment__is_public=True,
                                          rating__gt=0).distinct().aggregate(average=Avg('rating'))['average']
    log.debug("Rating: %s", rating)
    return rating

def get_product_rating_string(product, site=None):
    """Get the average product rating as a string, for use in templates"""
    rating = get_product_rating(product, site=site)
    
    if rating is not None:
        rating = "%0.1f" % rating
        if rating.endswith('.0'):
            rating = rating[0]
        rating = rating + "/5"
    else:
        rating = _('Not Rated')
        
    return rating
    
