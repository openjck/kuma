# -*- coding: utf-8 -*-
import operator

from django.conf import settings
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.functional import cached_property
from elasticutils.contrib.django.tasks import index_objects

from kuma.core.managers import PrefetchTaggableManager
from kuma.core.urlresolvers import reverse

from .signals import delete_index


class IndexManager(models.Manager):
    """
    The model manager to implement a couple of useful methods for handling
    search indexes.
    """
    def get_current(self):
        try:
            return (self.filter(promoted=True, populated=True)
                        .order_by('-created_at'))[0]
        except (self.model.DoesNotExist, IndexError, AttributeError):
            fallback_name = settings.ES_INDEXES['default']
            index = Index(name=fallback_name, promoted=True)
            index.save()
            return index


class Index(models.Model):
    """
    Model to store a bunch of metadata about search indexes including
    a way to promote it to be picked up as the "current" one.
    """
    created_at = models.DateTimeField(default=timezone.now)
    name = models.CharField(max_length=30, blank=True, null=True,
                            help_text='The search index name, set to '
                                      'the created date when left empty')
    promoted = models.BooleanField(default=False)
    populated = models.BooleanField(default=False)

    objects = IndexManager()

    class Meta:
        verbose_name = 'Index'
        verbose_name_plural = 'Indexes'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.created_at.strftime('%Y-%m-%d-%H-%M-%S')
        super(Index, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.name

    @cached_property
    def successor(self):
        try:
            return self.get_next_by_created_at()
        except (Index.DoesNotExist, ValueError):
            return None

    @cached_property
    def prefixed_name(self):
        "The name to use for the search index in ES"
        return '%s-%s' % (settings.ES_INDEX_PREFIX, self.name)

    def populate(self):
        from .tasks import populate_index
        populate_index.delay(self.pk)

    def record_outdated(self, instance):
        if self.successor:
            return OutdatedObject.objects.create(index=self.successor,
                                                 content_object=instance)

    def promote(self):
        rescheduled = []
        for outdated_object in self.outdated_objects.all():
            instance = outdated_object.content_object
            label = ('%s.%s.%s' %
                     (outdated_object.content_type.natural_key() +
                      (instance.id,)))  # gives us 'wiki.document.12345'
            if label in rescheduled:
                continue
            mappping_type = instance.get_mapping_type()
            index_objects.delay(mappping_type, [instance.id])
            rescheduled.append(label)
        self.outdated_objects.all().delete()
        self.promoted = True
        self.save()

    def demote(self):
        self.promoted = False
        self.save()


post_delete.connect(delete_index, sender=Index,
                    dispatch_uid='search.index.delete')


class OutdatedObject(models.Model):
    index = models.ForeignKey(Index, related_name='outdated_objects')
    created_at = models.DateTimeField(default=timezone.now)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')


class FilterGroup(models.Model):
    """
    A way to group different kinds of filters from each other.
    """
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, blank=True, null=True,
                            help_text='the slug to be used as the name of the '
                                      'query parameter in the search URL')
    order = models.IntegerField(default=1,
                                help_text='An integer defining which order '
                                          'the filter group should show up '
                                          'in the sidebar')

    class Meta:
        ordering = ('-order', 'name')
        unique_together = (
            ('name', 'slug'),
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(FilterGroup, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.name


class FilterManager(models.Manager):
    use_for_related_fields = True

    def visible_only(self):
        return self.filter(visible=True)


class Filter(models.Model):
    """
    The model to store custom search filters in the database. This is
    used to dynamically tweak the search filters available to users.
    """
    OPERATOR_AND = 'AND'
    OPERATOR_OR = 'OR'
    OPERATOR_CHOICES = (
        (OPERATOR_OR, OPERATOR_OR),
        (OPERATOR_AND, OPERATOR_AND),
    )
    OPERATORS = {
        OPERATOR_OR: operator.or_,
        OPERATOR_AND: operator.and_,
    }
    name = models.CharField(max_length=255, db_index=True,
                            help_text='the English name of the filter '
                                      'to be shown in the frontend UI')
    slug = models.CharField(max_length=255, db_index=True,
                            help_text='the slug to be used as a query '
                                      'parameter in the search URL')
    shortcut = models.CharField(max_length=255, db_index=True,
                                null=True, blank=True,
                                help_text='the name of the shortcut to '
                                          'show in the command and query UI. '
                                          'e.g. fxos')
    group = models.ForeignKey(FilterGroup, related_name='filters',
                              help_text='E.g. "Topic", "Skill level" etc')
    tags = PrefetchTaggableManager(help_text='A comma-separated list of tags. '
                                             'If more than one tag given a OR '
                                             'query is executed')
    operator = models.CharField(max_length=3, choices=OPERATOR_CHOICES,
                                default=OPERATOR_OR,
                                help_text='The logical operator to use '
                                          'if more than one tag is given')
    enabled = models.BooleanField(default=True,
                                  help_text='Whether this filter is shown '
                                            'to users or not.')
    visible = models.BooleanField(default=True,
                                  help_text='Whether this filter is shown '
                                            'at public places, e.g. the '
                                            'command and query UI')

    objects = FilterManager()

    class Meta(object):
        unique_together = (
            ('name', 'slug'),
        )

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        path = reverse('search', locale=settings.LANGUAGE_CODE)
        return '%s%s?%s=%s' % (settings.SITE_URL, path,
                               self.group.slug, self.slug)

