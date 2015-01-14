from nose.tools import eq_

from kuma.wiki.tests import revision

from . import ElasticTestCase
from ..models import WikiDocumentType


class TestLiveIndexing(ElasticTestCase):

    def test_live_indexing_docs(self):
        S = WikiDocumentType.search
        count_before = S().count()

        r = revision(save=True)
        r.document.render()

        self.refresh()
        eq_(count_before + 1, S().count())

        r.document.delete()
        self.refresh()
        eq_(count_before, S().count())
