from collections import namedtuple
from operator import attrgetter
from django.utils.datastructures import SortedDict

from elasticsearch_dsl.search import Search
from tower import ugettext as _

from .utils import QueryURLObject


class Filter(namedtuple('Filter',
                        ['name', 'slug', 'count', 'url',
                         'page', 'active', 'group_name', 'group_slug'])):
    __slots__ = ()

    def pop_page(self, url):
        return str(url.pop_query_param('page', str(self.page)))

    def urls(self):
        return {
            'active': self.pop_page(
                self.url.merge_query_param(self.group_slug, self.slug)),
            'inactive': self.pop_page(
                self.url.pop_query_param(self.group_slug, self.slug)),
        }


FilterGroup = namedtuple('FilterGroup', ['name', 'slug', 'order', 'options'])


class DocumentS(Search):
    """
    This `Search` object acts more like Django's querysets to better match
    the behavior of restframework's serializers as well as adding a method
    to return our custom facets.
    """
    def __init__(self, *args, **kwargs):
        self.url = kwargs.pop('url', None)
        self.current_page = kwargs.pop('current_page', None)
        self.serialized_filters = kwargs.pop('serialized_filters', None)
        self.selected_filters = kwargs.pop('selected_filters', None)
        super(DocumentS, self).__init__(*args, **kwargs)

    def _clone(self):
        new = super(DocumentS, self)._clone()
        new.url = self.url
        new.current_page = self.current_page
        new.serialized_filters = self.serialized_filters
        new.selected_filters = self.selected_filters
        return new

    def faceted_filters(self):
        url = QueryURLObject(self.url)
        filter_mapping = SortedDict((filter_['slug'], filter_)
                                    for filter_ in self.serialized_filters)

        filter_groups = SortedDict()

        # TODO: Explore a way to not have to call `execute` here as we may have
        # already made the query elsewhere.
        result = self.execute()
        facet_counts = [(k, result.facets[k]['count'])
                        for k in filter_mapping.keys()]

        for slug, count in facet_counts:

            filter_ = filter_mapping.get(slug, None)
            if filter_ is None:
                filter_name = slug
                group_name = None
                group_slug = None
            else:
                # Let's check if we can get the name from the gettext catalog
                filter_name = _(filter_['name'])
                group_name = _(filter_['group']['name'])
                group_slug = filter_['group']['slug']

            filter_groups.setdefault((
                group_name,
                group_slug,
                filter_['group']['order']
            ), []).append(
                Filter(url=url,
                       page=self.current_page,
                       name=filter_name,
                       slug=slug,
                       count=count,
                       active=slug in self.selected_filters,
                       group_name=group_name,
                       group_slug=group_slug))

        # return a sorted list of filters here
        grouped_filters = []
        for group_options, filters in filter_groups.items():
            group_name, group_slug, group_order = group_options
            sorted_filters = sorted(filters, key=attrgetter('name'))
            grouped_filters.append(FilterGroup(name=group_name,
                                               slug=group_slug,
                                               order=group_order,
                                               options=sorted_filters))
        return sorted(grouped_filters, key=attrgetter('order'), reverse=True)
