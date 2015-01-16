import logging
import warnings

from django.conf import settings
from django.core.mail import mail_admins

from celery.exceptions import SoftTimeLimitExceeded
from celery.task import task

from .commands import es_reindex_cmd
from .models import Index, WikiDocumentType


log = logging.getLogger('kuma.search.tasks')


# ignore a deprecation warning from elasticutils until the fix is released
# refs https://github.com/mozilla/elasticutils/pull/160
warnings.filterwarnings("ignore",
                        category=DeprecationWarning,
                        module='celery.decorators')

FIVE_MINUTES = 60 * 5
ONE_HOUR = FIVE_MINUTES * 12


@task(soft_time_limit=ONE_HOUR, time_limit=ONE_HOUR + FIVE_MINUTES)
def populate_index(index_pk):
    index = Index.objects.get(pk=index_pk)
    try:
        es_reindex_cmd(index=index.prefixed_name, chunk_size=500)
    except SoftTimeLimitExceeded:
        subject = ('[%s] Exceptions raised in populate_index() task '
                  'with index %s' % (settings.PLATFORM_NAME,
                                     index.prefixed_name))
        message = ("Task ran longer than soft limit of %s seconds. "
                   "Needs increasing?" % ONE_HOUR)
    else:
        index.populated = True
        index.save()
        subject = ('[%s] Index %s completely populated' %
                   (settings.PLATFORM_NAME, index.prefixed_name))
        message = "You may want to promote it now via the admin interface."
    mail_admins(subject=subject, message=message)


@task
def index_documents(ids, index_pk, reraise=False):
    """
    Index a list of documents into the provided index.

    :arg ids: Iterable of `Document` pks to index.
    :arg index_pk: The `Index` pk of the index to index into.
    :arg reraise: False if you want errors to be swallowed and True
        if you want errors to be thrown.

    .. Note::

       This indexes all the documents in the chunk in one single bulk
       indexing call. Keep that in mind when you break your indexing
       task into chunks.

    """
    from kuma.wiki.models import Document

    cls = WikiDocumentType
    es = cls.get_connection('indexing')
    index = Index.objects.get(pk=index_pk)

    objects = Document.objects.filter(id__in=ids)
    documents = []
    for obj in objects:
        try:
            documents.append(cls.from_django(obj))
        except Exception:
            log.exception('Unable to extract/index document (id: %d)', obj.id)
            if reraise:
                raise

    cls.bulk_index(documents, id_field='id', es=es, index=index.prefixed_name)


@task
def unindex_documents(ids, index_pk):
    """
    Delete a list of documents from the provided index.

    :arg ids: Iterable of `Document` pks to remove.
    :arg index_pk: The `Index` pk of the index to remove items from.

    """
    cls = WikiDocumentType
    es = cls.get_connection('indexing')
    index = Index.objects.get(pk=index_pk)

    for pk in ids:
        es.delete(index=index, doc_type=cls.get_doc_type(), id=pk)
