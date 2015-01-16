import logging

from elasticsearch.exceptions import RequestError, NotFoundError

from .models import Index, WikiDocumentType


log = logging.getLogger('kuma.search.index')


def delete_index_if_exists(index):
    """Delete the specified index.

    :arg index: The name of the index to delete.

    """
    es = WikiDocumentType.get_connection()
    try:
        es.indices.delete(index)
    except NotFoundError:
        # Can ignore this since it indicates the index doesn't exist
        # and therefore there's nothing to delete.
        pass


def recreate_index(es=None, index=None):
    """Delete index if it's there and creates a new one.

    :arg es: ES to use. By default, this creates a new indexing ES.

    """
    cls = WikiDocumentType

    if es is None:
        es = cls.get_connection()
    if index is None:
        index = Index.objects.get_current().prefixed_name

    delete_index_if_exists(index)

    # Simultaneously create the index and the mappings, so live
    # indexing doesn't get a chance to index anything between the two
    # causing ES to infer a possibly bogus mapping (which causes ES to
    # freak out if the inferred mapping is incompatible with the
    # explicit mapping).
    try:
        es.indices.create(index, body=cls.get_settings())
    except RequestError:
        pass
