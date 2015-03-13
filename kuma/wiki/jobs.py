from cacheback.base import Job


class DocumentZoneStackJob(Job):
    lifetime = 60 * 60 * 3
    refresh_timeout = 60

    def fetch(self, pk):
        """
        Assemble the stack of DocumentZones available from this document,
        moving up the stack of topic parents
        """
        from .models import Document, DocumentZone
        document = Document.objects.get(pk=pk)
        stack = []
        try:
            stack.append(DocumentZone.objects.get(document=document))
        except DocumentZone.DoesNotExist:
            pass
        for parent in document.get_topic_parents():
            try:
                stack.append(DocumentZone.objects.get(document=parent))
            except DocumentZone.DoesNotExist:
                pass
        return stack

    def key(self, pk):
        # override the default way to make sure we handle unicode,
        # bytestring and integer versions of the pk the same
        return 'wiki:zone:stack:%s' % pk

    def empty(self):
        return []


class DocumentZoneURLRemapsJob(Job):
    lifetime = 60 * 60 * 3
    refresh_timeout = 60

    def fetch(self, locale):
        from .models import DocumentZone
        zones = (DocumentZone.objects.filter(document__locale=locale,
                                             url_root__isnull=False)
                                     .exclude(url_root=''))
        remaps = [('/docs/%s' % zone.document.slug, '/%s' % zone.url_root)
                  for zone in zones]
        return remaps

    def key(self, locale):
        # override the default way to make sure we handle unicode
        # and bytestring versions of the locale the same
        return 'wiki:zone:remaps:%s' % locale

    def empty(self):
        # the empty result needs to be an empty list instead of None
        return []
