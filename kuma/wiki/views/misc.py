# -*- coding: utf-8 -*-
import newrelic.agent
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET
from smuggler.forms import ImportForm

from kuma.contentflagging.models import FLAG_NOTIFICATIONS, ContentFlag
from kuma.core.decorators import block_user_agents, superuser_required
from kuma.users.models import User

from ..constants import ALLOWED_TAGS, REDIRECT_CONTENT
from ..decorators import allow_CORS_GET, process_document_path
from ..forms import DocumentContentFlagForm
from ..models import Document, EditorToolbar


def ckeditor_config(request):
    """
    Return ckeditor config from database
    """
    default_config = EditorToolbar.objects.filter(name='default')
    if default_config.exists():
        code = default_config[0].code
    else:
        code = ''

    context = {
        'editor_config': code,
        'redirect_pattern': REDIRECT_CONTENT,
        'allowed_tags': ' '.join(ALLOWED_TAGS),
    }
    return render(request, 'wiki/ckeditor_config.js', context,
                  content_type='application/x-javascript')


@block_user_agents
@require_GET
@allow_CORS_GET
@newrelic.agent.function_trace()
def autosuggest_documents(request):
    """
    Returns the closest title matches for front-end autosuggests
    """
    partial_title = request.GET.get('term', '')
    locale = request.GET.get('locale', False)
    current_locale = request.GET.get('current_locale', False)
    exclude_current_locale = request.GET.get('exclude_current_locale', False)

    if not partial_title:
        # Only handle actual autosuggest requests, not requests for a
        # memory-busting list of all documents.
        return HttpResponseBadRequest(_('Autosuggest requires a partial '
                                        'title. For a full document '
                                        'index, see the main page.'))

    # Retrieve all documents that aren't redirects or templates
    docs = (Document.objects.extra(select={'length': 'Length(slug)'})
                            .filter(title__icontains=partial_title,
                                    is_template=0,
                                    is_redirect=0)
                            .exclude(slug__icontains='Talk:')  # Remove old talk pages
                            .order_by('title', 'length'))

    # All locales are assumed, unless a specific locale is requested or banned
    if locale:
        docs = docs.filter(locale=locale)
    if current_locale:
        docs = docs.filter(locale=request.LANGUAGE_CODE)
    if exclude_current_locale:
        docs = docs.exclude(locale=request.LANGUAGE_CODE)

    # Generates a list of acceptable docs
    docs_list = []
    for doc in docs:
        data = doc.get_json_data()
        data['label'] += ' [' + doc.locale + ']'
        docs_list.append(data)

    return JsonResponse(docs_list, safe=False)


@block_user_agents
@xframe_options_sameorigin
@process_document_path
def flag(request, document_slug, document_locale):
    """
    Flag a document for something.
    """
    doc = get_object_or_404(Document,
                            slug=document_slug,
                            locale=document_locale)

    if request.method == 'POST':
        form = DocumentContentFlagForm(data=request.POST)
        if form.is_valid():
            flag_type = form.cleaned_data['flag_type']
            recipients = None
            if (flag_type in FLAG_NOTIFICATIONS and
                    FLAG_NOTIFICATIONS[flag_type]):
                query = Q(email__isnull=True) | Q(email='')
                recipients = list(User.objects.exclude(query)
                                              .values_list('email', flat=True))

            flag, created = ContentFlag.objects.flag(
                request=request, object=doc,
                flag_type=flag_type,
                explanation=form.cleaned_data['explanation'],
                recipients=recipients)
            return redirect(doc)
    else:
        form = DocumentContentFlagForm(data=request.GET)

    return render(request, 'wiki/flag.html', {'form': form, 'doc': doc})


@block_user_agents
@superuser_required
def load_documents(request):
    """
    Load documents from uploaded file.
    """
    form = ImportForm()
    if request.method == 'POST':

        # Accept the uploaded document data.
        file_data = None
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['uploads']
            if uploaded_file.multiple_chunks():
                file_data = open(uploaded_file.temporary_file_path(), 'r')
            else:
                file_data = uploaded_file.read()

        if file_data:
            # Try to import the data, but report any error that occurs.
            try:
                counter = Document.objects.load_json(request.user, file_data)
                user_msg = (ugettext('%(obj_count)d object(s) loaded.') %
                            {'obj_count': counter, })
                messages.add_message(request, messages.INFO, user_msg)
            except Exception as e:
                err_msg = (ugettext('Failed to import data: %(error)s') %
                           {'error': '%s' % e, })
                messages.add_message(request, messages.ERROR, err_msg)

    context = {'import_file_form': form}
    return render(request, 'admin/wiki/document/load_data_form.html', context)
