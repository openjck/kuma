# -*- coding: utf-8 -*-
import operator
from django.conf import settings
from django.db import models
from django.utils.html import strip_tags

from elasticsearch.helpers import bulk
from elasticsearch_dsl import document, field
from elasticsearch_dsl.connections import connections

from kuma.search.queries import DocumentS

# Configure Elasticsearch connections for connection pooling.

connections.configure(
    default={'hosts': settings.ES_URLS},
    indexing={'hosts': settings.ES_URLS,
              'timeout': settings.ES_INDEXING_TIMEOUT},
)


class WikiDocumentType(document.DocType):
    excerpt_fields = ['summary', 'content']
    exclude_slugs = ['Talk:', 'User:', 'User_talk:', 'Template_talk:',
                     'Project_talk:']

    boost = field.Float(null_value=1.0)
    content = field.String(analyzer='kuma_content',
                           term_vector='with_positions_offsets')
    css_classnames = field.String(analyzer='case_insensitive_keyword')
    html_attributes = field.String(analyzer='case_insensitive_keyword')
    id = field.Long()
    kumascript_macros = field.String(analyzer='case_insensitive_keyword')
    locale = field.String(index='not_analyzed')
    modified = field.Date()
    parent = field.Object(properties={
        'id': field.Long(),
        'title': field.String(analyzer='kuma_title'),
        'slug': field.String(index='not_analyzed'),
        'locale': field.String(index='not_analyzed'),
    })
    slug = field.String(index='not_analyzed')
    summary = field.String(analyzer='kuma_content',
                           term_vector='with_positions_offsets')
    tags = field.String(analyzer='case_sensitive')
    title = field.String(analyzer='kuma_title', boost=1.2)

    class Meta(object):
        doc_type = 'wiki_document'

    @classmethod
    def get_connection(cls, alias='default'):
        return connections.get_connection(alias)

    @classmethod
    def get_doc_type(cls):
        return cls._doc_type.name

    @classmethod
    def from_django(cls, obj):
        doc = {
            'id': obj.id,
            'title': obj.title,
            'slug': obj.slug,
            'summary': obj.get_summary(strip_markup=True),
            'locale': obj.locale,
            'modified': obj.modified,
            'content': strip_tags(obj.rendered_html),
            'tags': list(obj.tags.values_list('name', flat=True)),
            'kumascript_macros': obj.extract_kumascript_macro_names(),
            'css_classnames': obj.extract_css_classnames(),
            'html_attributes': obj.extract_html_attributes(),
        }
        if obj.zones.exists():
            # boost all documents that are a zone
            doc['_boost'] = 8.0
        elif obj.slug.split('/') == 1:
            # a little boost if no zone but still first level
            doc['_boost'] = 4.0
        else:
            doc['_boost'] = 1.0
        if obj.parent:
            doc['parent'] = {
                'id': obj.parent.id,
                'title': obj.parent.title,
                'locale': obj.parent.locale,
                'slug': obj.parent.slug,
            }
        else:
            doc['parent'] = {}

        return doc

    @classmethod
    def get_mapping(cls):
        mapping = cls._doc_type.mapping.to_dict()
        # TODO: Temporary until elasticsearch-dsl-py supports this.
        mapping['wiki_document']['_all'] = {'enabled': False}

        return mapping

    @classmethod
    def get_settings(cls):
        settings = {
            'mappings': cls.get_mapping(),
            'settings': {
                'index': {
                    'analysis': cls.get_analysis()
                }
            }
        }

        return settings

    @classmethod
    def bulk_index(cls, documents, id_field='id', es=None, index=None):
        """Index of a bunch of documents."""
        es = es or cls.get_connection()
        index = index or cls.get_index()
        type = cls.get_doc_type()

        actions = [
            {'_index': index, '_type': type, '_id': d['id'], '_source': d}
            for d in documents]

        bulk(es, actions)

    @classmethod
    def get_index(cls):
        from kuma.search.models import Index
        return Index.objects.get_current().prefixed_name

    @classmethod
    def search(cls, **kwargs):
        kwargs.update({
            'using': connections.get_connection(),
            'index': cls.get_index(),
            'doc_type': {cls._doc_type.name: cls.from_es},
        })
        search = DocumentS(**kwargs)
        search = search.highlight(*cls.excerpt_fields)
        search = search.extra(explain=True)
        return search

    ###
    ### Old elasticutils methods below.
    ###

    @classmethod
    def get_model(cls):
        from kuma.wiki.models import Document
        return Document

    @classmethod
    def get_analysis(cls):
        return {
            'filter': {
                'kuma_word_delimiter': {
                    'type': 'word_delimiter',
                    'preserve_original': True,  # hi-fi -> hifi, hi-fi
                    'catenate_words': True,  # hi-fi -> hifi
                    'catenate_numbers': True,  # 90-210 -> 90210
                }
            },
            'analyzer': {
                'default': {
                    'tokenizer': 'standard',
                    'filter': ['standard', 'elision']
                },
                # a custom analyzer that strips html and uses our own
                # word delimiter filter and the elision filter
                # (e.g. L'attribut -> attribut). The rest is the same as
                # the snowball analyzer
                'kuma_content': {
                    'type': 'custom',
                    'tokenizer': 'standard',
                    'char_filter': ['html_strip'],
                    'filter': [
                        'elision',
                        'kuma_word_delimiter',
                        'lowercase',
                        'standard',
                        'stop',
                        'snowball',
                    ],
                },
                'kuma_title': {
                    'type': 'custom',
                    'tokenizer': 'standard',
                    'filter': [
                        'elision',
                        'kuma_word_delimiter',
                        'lowercase',
                        'standard',
                        'snowball',
                    ],
                },
                'case_sensitive': {
                    'type': 'custom',
                    'tokenizer': 'keyword'
                },
                'case_insensitive_keyword': {
                    'type': 'custom',
                    'tokenizer': 'keyword',
                    'filter': 'lowercase'
                }
            },
        }

    @classmethod
    def get_indexable(cls, percent=100):
        """
        For this mapping type return a list of model IDs that should be
        indexed with the management command, in a full reindex.

        WARNING: When changing this code make sure to update the
                 ``should_update`` method below, too!

        """
        model = cls.get_model()

        excludes = []
        for exclude in cls.exclude_slugs:
            excludes.append(models.Q(slug__icontains=exclude))

        qs = (model.objects
                   .filter(is_template=False,
                           is_redirect=False,
                           deleted=False)
                   .exclude(reduce(operator.or_, excludes)))

        percent = float(percent) / 100
        if percent < 1:
            qs = qs[:int(qs.count() * percent)]

        return qs.values_list('id', flat=True)

    @classmethod
    def should_update(cls, obj):
        """
        Given a Document instance should return boolean value
        whether the instance should be indexed or not.

        WARNING: This *must* mirror the logic of the ``get_indexable``
                 method above!
        """
        return (not obj.is_template and
                not obj.is_redirect and
                not obj.deleted and
                not any([exclude in obj.slug
                         for exclude in cls.exclude_slugs]))

    def get_excerpt(self):
        if getattr(self, 'highlight', False):
            for excerpt_field in self.excerpt_fields:
                if excerpt_field in self.highlight:
                    return u'…'.join(self.highlight[excerpt_field])
        return self.summary
