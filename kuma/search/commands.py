import logging
import time

from django.conf import settings
from django.db import reset_queries

from elasticsearch.exceptions import NotFoundError

from .decorators import requires_good_connection
from .index import recreate_index
from .models import Index, WikiDocumentType
from .utils import chunked, format_time


log = logging.getLogger('kuma.search.commands')


@requires_good_connection
def es_reindex_cmd(chunk_size=1000, index=None, percent=100):
    """Rebuild ElasticSearch indexes.

    :arg chunk_size: how many documents to bulk index as a single chunk.
    :arg index: the `Index` object to reindex into. Uses the current promoted
        index if none provided.
    :arg percent: 1 to 100--the percentage of the db to index.

    """
    from .tasks import index_documents

    cls = WikiDocumentType

    index = index or Index.objects.get_current()
    index_name = index.prefixed_name

    es = cls.get_connection('indexing')

    log.info('Wiping and recreating %s....', index_name)
    recreate_index(es=es, index=index_name)

    indexable = WikiDocumentType.get_indexable()

    # We're doing a lot of indexing, so we get the refresh_interval
    # currently in the index, then nix refreshing. Later we'll restore it.
    index_settings = {}
    try:
        index_settings = (es.indices.get_settings(index_name)
                            .get(index_name, {}).get('settings', {}))
    except NotFoundError:
        pass

    refresh_interval = index_settings.get(
        'index.refresh_interval', settings.ES_DEFAULT_REFRESH_INTERVAL)
    number_of_replicas = index_settings.get(
        'number_of_replicas', settings.ES_DEFAULT_NUM_REPLICAS)

    # Disable automatic refreshing.
    temporary_settings = {
        'index': {
            'refresh_interval': '-1',
            'number_of_replicas': '0',
        }
    }

    try:
        es.indices.put_settings(temporary_settings, index=index_name)
        start_time = time.time()

        cls_start_time = time.time()
        total = len(indexable)

        if total == 0:
            return

        log.info('Reindex %s. %s to index...', cls.get_doc_type(), total)

        i = 0
        for chunk in chunked(indexable, chunk_size):
            index_documents(chunk, index.pk)

            i += len(chunk)
            time_to_go = (total - i) * ((time.time() - start_time) / i)
            per_chunk_size = (time.time() - start_time) / (i / float(chunk_size))
            log.info('%s/%s... (%s to go, %s per %s docs)', i, total,
                     format_time(time_to_go),
                     format_time(per_chunk_size),
                     chunk_size)

            # We call this every 1000 or so because we're
            # essentially loading the whole db and if DEBUG=True,
            # then Django saves every sql statement which causes
            # our memory to go up up up. So we reset it and that
            # makes things happier even in DEBUG environments.
            reset_queries()

        delta_time = time.time() - cls_start_time
        log.info('Done! (%s, %s per %s docs)',
                 format_time(delta_time),
                 format_time(delta_time / (total / float(per_chunk_size))),
                 chunk_size)

    finally:
        # Re-enable automatic refreshing
        reset_settings = {
            'index': {
                'refresh_interval': refresh_interval,
                'number_of_replicas': number_of_replicas,
            }
        }
        es.indices.put_settings(reset_settings, index_name)
        delta_time = time.time() - start_time
        log.info('Done! (total time: %s)', format_time(delta_time))
