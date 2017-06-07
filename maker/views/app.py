import json

from django.core.exceptions import ValidationError
from django.db.utils import OperationalError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.forms import FileField, ImageField, ClearableFileInput
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, ListView
from django.views.generic.edit import UpdateView, DeleteView
from hvad.forms import translationformset_factory
from tinymce.widgets import TinyMCE

from maker.models import RemoteRepository, App, RemoteApp, ApkPointer, Screenshot
from maker.models.category import Category
from . import BaseModelForm
from .repository import RepositoryAuthorizationMixin


class MDLTinyMCE(TinyMCE):
    """
    Ugly hack to work around a conflict between MDL and TinyMCE. See #31 for more details.
    """
    def _media(self):
        media = super()._media()
        media._js.remove('django_tinymce/init_tinymce.js')  # pylint: disable=protected-access
        media._js.append('maker/js/mdl-tinymce.js')  # pylint: disable=protected-access
        return media
    media = property(_media)


class AppAddView(RepositoryAuthorizationMixin, ListView):
    model = RemoteApp
    context_object_name = 'apps'
    paginate_by = 15
    template_name = "maker/app/add.html"

    def get_queryset(self):
        qs = RemoteApp.objects.filter(repo__users__id=self.request.user.id)
        if 'remote_repo_id' in self.kwargs:
            qs = qs.filter(repo__pk=self.kwargs['remote_repo_id'])
        if 'search' in self.request.GET:
            query = self.request.GET['search']
            qs = qs.filter(Q(name__icontains=query) | Q(summary__icontains=query))
        if 'category_id' in self.kwargs:
            qs = qs.filter(category__id=self.kwargs['category_id'])
        return qs

    def get_context_data(self, **kwargs):
        context = super(AppAddView, self).get_context_data(**kwargs)
        context['repo'] = self.get_repo()
        context['remote_repos'] = RemoteRepository.objects.filter(users__id=self.request.user.id)
        context['categories'] = Category.objects.filter(Q(user=None) | Q(user=self.request.user))
        if 'remote_repo_id' in self.kwargs:
            context['remote_repo'] = RemoteRepository.objects.get(pk=self.kwargs['remote_repo_id'])
        if 'category_id' in self.kwargs:
            context['category'] = context['categories'].get(pk=self.kwargs['category_id'])
        if 'search' in self.request.GET and self.request.GET['search'] != '':
            context['search_params'] = 'search=%s' % self.request.GET['search']
        for app in context['apps']:
            app.added = app.is_in_repo(context['repo'])
        return context

    def post(self, request, *args, **kwargs):
        if request.is_ajax():
            apps_to_add = json.loads(request.body.decode("utf-8"))
            for app in apps_to_add:
                app_id = app['appId']
                remote_repo_id = app['appRepoId']
                remote_app = RemoteApp.objects.get(repo__id=remote_repo_id, pk=app_id,
                                                   repo__users__id=request.user.id)
                try:
                    remote_app.add_to_repo(self.get_repo())
                except OperationalError:
                    return HttpResponse(1, status=500)
                except ValidationError as e:
                    # TODO: Remove with https://gitlab.com/fdroid/repomaker/issues/93
                    if "This app does already exist in your repository." == e.message:
                        return HttpResponse(2, status=400)
                    return HttpResponse(status=400)
            self.get_repo().update_async()  # schedule repository update
            return HttpResponse(status=204)
        return Http404()


class AppDetailView(RepositoryAuthorizationMixin, DetailView):
    model = App
    pk_url_kwarg = 'app_id'
    context_object_name = 'app'
    template_name = 'maker/app/index.html'

    def get_repo(self):
        return self.get_object().repo

    def get_context_data(self, **kwargs):
        context = super(AppDetailView, self).get_context_data(**kwargs)
        app = context['app']
        if app.name is None or app.name == '':
            raise RuntimeError("App has not been created properly.")
        context['apks'] = ApkPointer.objects.filter(app=app).order_by('-apk__version_code')
        return context


class AppForm(BaseModelForm):
    screenshots = ImageField(required=False, widget=ClearableFileInput(attrs={'multiple': True}))
    apks = FileField(required=False, widget=ClearableFileInput(attrs={'multiple': True}))

    def __init__(self, *args, **kwargs):
        super(AppForm, self).__init__(*args, **kwargs)
        if self.instance.category:
            # Show only own and default categories
            self.fields['category'].queryset = Category.objects.filter(
                Q(user=None) | Q(user=self.instance.repo.user))

    class Meta:
        model = App
        fields = ['summary', 'description', 'author_name', 'website', 'category', 'screenshots',
                  'apks']
        widgets = {'description': MDLTinyMCE()}


class AppUpdateView(RepositoryAuthorizationMixin, UpdateView):
    model = App
    form_class = AppForm
    pk_url_kwarg = 'app_id'
    template_name = 'maker/app/edit.html'

    def get_repo(self):
        return self.get_object().repo

    def get_context_data(self, **kwargs):
        context = super(AppUpdateView, self).get_context_data(**kwargs)
        context['apks'] = ApkPointer.objects.filter(app=self.object).order_by('-apk__version_code')
        return context

    def form_valid(self, form):
        result = super(AppUpdateView, self).form_valid(form)

        for screenshot in self.request.FILES.getlist('screenshots'):
            Screenshot.objects.create(app=self.object, file=screenshot)

        for apk in self.request.FILES.getlist('apks'):
            pointer = ApkPointer.objects.create(repo=self.object.repo, file=apk)
            try:
                # TODO check that the APK belongs to this app and that signature matches
                pointer.initialize()  # this also attaches the app
            except Exception as e:
                pointer.delete()
                raise e

        form.instance.repo.update_async()  # schedule repository update
        return result


class AppDeleteView(RepositoryAuthorizationMixin, DeleteView):
    model = App
    pk_url_kwarg = 'app_id'
    template_name = 'maker/app/delete.html'

    def get_repo(self):
        return self.get_object().repo

    def get_success_url(self):
        self.get_repo().update_async()  # schedule repository update
        return reverse_lazy('repo', kwargs={'repo_id': self.kwargs['repo_id']})


class AppTranslationUpdateView(RepositoryAuthorizationMixin, UpdateView):
    model = App
    form_class = translationformset_factory(App, fields=['l_summary', 'l_description',
                                                         'feature_graphic'],
                                            widgets={'l_description': MDLTinyMCE()}, extra=1)
    pk_url_kwarg = 'app_id'
    context_object_name = 'app'
    template_name = "maker/app/translate.html"

    def get_success_url(self):
        self.get_repo().update_async()  # schedule repository update
        return reverse('app', kwargs=self.kwargs)
