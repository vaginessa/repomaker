import os
import shutil

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from maker import DEFAULT_USER_NAME
from maker.models import App, Apk, ApkPointer, Repository, Screenshot
from .. import TEST_DIR, TEST_MEDIA_DIR, TEST_FILES_DIR


@override_settings(MEDIA_ROOT=TEST_MEDIA_DIR)
class AppViewTestCase(TestCase):

    def setUp(self):
        # create repository for singe-user-mode
        self.repo = Repository.objects.create(
            name="Test Name",
            description="Test Description",
            url="https://example.org",
            user=User.objects.get(username=DEFAULT_USER_NAME),
        )
        self.repo.chdir()

        # create app in repo
        self.app = App.objects.create(repo=self.repo,
                                      package_id='org.bitbucket.tickytacky.mirrormirror',
                                      name='TestApp', website='TestSite', author_name='author')
        # translate app in default language
        self.app.translate(settings.LANGUAGE_CODE)
        self.app.summary = 'Test Summary'
        self.app.description = 'Test Description'
        self.app.save()

    def tearDown(self):
        if os.path.isdir(TEST_DIR):
            shutil.rmtree(TEST_DIR)

    def test_app_detail_default_lang_redirect(self):
        kwargs = {'repo_id': self.app.repo.pk, 'app_id': self.app.pk}
        response = self.client.get(reverse('app', kwargs=kwargs))
        self.assertRedirects(response, self.app.get_absolute_url())

    def test_app_detail_default_lang(self):
        response = self.client.get(self.app.get_absolute_url())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, self.app.name)
        self.assertContains(response, self.app.author_name)
        self.assertContains(response, self.app.summary)
        self.assertContains(response, self.app.description)

    def test_app_detail_other_lang(self):
        self.translate_to_de()
        self.assertTrue('/de/' in self.app.get_absolute_url())

        response = self.client.get(self.app.get_absolute_url())
        self.assertContains(response, 'Test-Zusammenfassung')
        self.assertContains(response, 'Test-Beschreibung')

        # ensure that there is a link to the default language
        app = App.objects.language(settings.LANGUAGE_CODE).get(pk=self.app.pk)
        self.assertFalse('/de/' in app.get_absolute_url())
        self.assertTrue('/' + settings.LANGUAGE_CODE + '/' in app.get_absolute_url())
        self.assertContains(response, app.get_absolute_url())

    def test_app_detail_prev_next(self):
        # create a second app in a different language
        app2 = App.objects.create(repo=self.repo, package_id='org.example', name='Example')
        app2.translate('de')
        app2.save()

        # ensure first app has a link to the next one
        response = self.client.get(self.app.get_absolute_url())
        self.assertEqual(self.app, response.context['app'])
        with self.assertRaises(App.DoesNotExist):
            self.app.get_previous()
        self.assertContains(response, self.app.get_next().get_absolute_url())

        # ensure second app has a link back to the previous one
        response = self.client.get(self.app.get_next().get_absolute_url())
        self.assertEqual(app2, response.context['app'])
        self.assertContains(response, app2.get_previous().get_absolute_url())
        with self.assertRaises(App.DoesNotExist):
            app2.get_next()

    def test_app_edit_default_lang(self):
        response = self.client.get(self.app.get_edit_url())
        self.assertEqual(200, response.status_code)
        self.assertContains(response, self.app.name)
        self.assertContains(response, self.app.author_name)
        self.assertContains(response, self.app.summary)
        self.assertContains(response, self.app.description)

    def test_app_edit_other_lang(self):
        self.translate_to_de()
        self.assertTrue('/de/' in self.app.get_edit_url())

        response = self.client.get(self.app.get_edit_url())
        self.assertContains(response, 'Test-Zusammenfassung')
        self.assertContains(response, 'Test-Beschreibung')

        # ensure that there is a link to the default language
        app = App.objects.language(settings.LANGUAGE_CODE).get(pk=self.app.pk)
        self.assertFalse('/de/' in app.get_absolute_url())
        self.assertTrue('/' + settings.LANGUAGE_CODE + '/' in app.get_edit_url())
        self.assertContains(response, app.get_edit_url())

    def test_app_edit_unknown_lang(self):
        kwargs = {'repo_id': self.repo.pk, 'app_id': self.app.pk, 'lang': 'xxx'}
        response = self.client.get(reverse('app_edit', kwargs=kwargs))
        self.assertEqual(404, response.status_code)

    def test_app_edit_prev_next(self):
        # create a second app in a different language
        app2 = App.objects.create(repo=self.repo, package_id='org.example', name='Example')
        app2.translate('de')
        app2.save()

        # ensure first app has a link to the next one
        response = self.client.get(self.app.get_edit_url())
        self.assertEqual(self.app, response.context['app'])
        with self.assertRaises(App.DoesNotExist):
            self.app.get_previous()
        self.assertContains(response, self.app.get_next().get_edit_url())

        # ensure second app has a link back to the previous one
        response = self.client.get(self.app.get_next().get_edit_url())
        self.assertEqual(app2, response.context['app'])
        self.assertContains(response, app2.get_previous().get_edit_url())
        with self.assertRaises(App.DoesNotExist):
            app2.get_next()

    def test_upload_apk_and_update(self):
        self.assertEqual(1, App.objects.all().count())
        self.assertEqual(0, Apk.objects.all().count())
        self.assertEqual(0, ApkPointer.objects.all().count())

        with open(os.path.join(TEST_FILES_DIR, 'test_1.apk'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'apks': f})

        self.assertEqual(1, App.objects.all().count())
        self.assertEqual(1, Apk.objects.all().count())
        self.assertEqual(1, ApkPointer.objects.all().count())
        self.assertEqual(1, self.app.apkpointer_set.count())

        with open(os.path.join(TEST_FILES_DIR, 'test_2.apk'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'apks': f})

        self.assertEqual(1, App.objects.all().count())
        self.assertEqual(2, Apk.objects.all().count())
        self.assertEqual(2, ApkPointer.objects.all().count())
        self.assertEqual(2, self.app.apkpointer_set.count())

        self.assertTrue(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_reject_non_update(self):
        with open(os.path.join(TEST_FILES_DIR, 'test_1.apk'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'apks': f})

        # unset scheduled update, so we can test that no new one was scheduled at the end
        self.repo.update_scheduled = False
        self.repo.save()

        with open(os.path.join(TEST_FILES_DIR, 'test.pdf'), 'rb') as f:
            response = self.client.post(self.app.get_edit_url(), {'apks': f})
            form = response.context['form']
            self.assertTrue(form.has_error('apks'))
            self.assertContains(response,
                                'test.pdf: This file is not an update ' +
                                'for org.bitbucket.tickytacky.mirrormirror')

        self.assertEqual(1, App.objects.all().count())
        self.assertEqual(1, Apk.objects.all().count())
        self.assertEqual(1, ApkPointer.objects.all().count())
        self.assertEqual(1, self.app.apkpointer_set.count())

        self.assertFalse(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_reject_non_update_ajax(self):
        with open(os.path.join(TEST_FILES_DIR, 'test_1.apk'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'apks': f})

        # unset scheduled update, so we can test that no new one was scheduled at the end
        self.repo.update_scheduled = False
        self.repo.save()

        with open(os.path.join(TEST_FILES_DIR, 'test.pdf'), 'rb') as f:
            response = self.client.post(self.app.get_edit_url(), {'apks': f},
                                        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                                        HTTP_RM_BACKGROUND_TYPE='screenshots')
        self.assertContains(response, 'test.pdf: This file is not an update ' +
                            'for org.bitbucket.tickytacky.mirrormirror', status_code=500)

        self.assertEqual(1, App.objects.all().count())
        self.assertEqual(1, Apk.objects.all().count())
        self.assertEqual(1, ApkPointer.objects.all().count())
        self.assertEqual(1, self.app.apkpointer_set.count())

        self.assertFalse(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_upload_screenshot(self):
        self.assertEqual(0, Screenshot.objects.all().count())

        with open(os.path.join(TEST_FILES_DIR, 'test.png'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'screenshots': f})

        self.assertEqual(1, Screenshot.objects.all().count())
        self.assertTrue(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_upload_screenshot_ajax(self):
        self.assertEqual(0, Screenshot.objects.all().count())

        with open(os.path.join(TEST_FILES_DIR, 'test.png'), 'rb') as f:
            self.client.post(self.app.get_edit_url(), {'screenshots': f},
                             HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                             HTTP_RM_BACKGROUND_TYPE='screenshots')

        self.assertEqual(1, Screenshot.objects.all().count())
        self.assertTrue(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_add_lang(self):
        self.assertFalse('de' in self.app.get_available_languages())
        kwargs = {'repo_id': self.repo.pk, 'app_id': self.app.pk}
        data = {
            'lang': 'de',
            'summary': 'Test-Zusammenfassung',
            'description': 'Test-Beschreibung',
        }
        response = self.client.post(reverse('app_add_lang', kwargs=kwargs), data)
        kwargs['lang'] = 'de'
        self.assertRedirects(response, reverse('app', kwargs=kwargs))
        self.assertTrue('de' in self.app.get_available_languages())

        # assert data was saved properly
        self.app = App.objects.language('de').get(pk=self.app.pk)
        self.assertEqual(data['summary'], self.app.summary)
        self.assertEqual(data['description'], self.app.description)
        self.assertTrue(Repository.objects.get(pk=self.repo.pk).update_scheduled)

    def test_add_lang_exists(self):
        self.translate_to_de()
        kwargs = {'repo_id': self.repo.pk, 'app_id': self.app.pk}
        response = self.client.post(reverse('app_add_lang', kwargs=kwargs), {'lang': 'de'})
        self.assertEqual(200, response.status_code)
        self.assertEqual('This language already exists. Please choose another one!',
                         response.context['form'].errors['lang'])
        self.assertContains(response, response.context['form'].errors['lang'])

    def test_add_lang_invalid(self):
        kwargs = {'repo_id': self.repo.pk, 'app_id': self.app.pk}
        response = self.client.post(reverse('app_add_lang', kwargs=kwargs), {'lang': '123'})
        self.assertEqual(200, response.status_code)
        self.assertEqual('This is not a valid language code.',
                         response.context['form'].errors['lang'])
        self.assertContains(response, response.context['form'].errors['lang'])

    def translate_to_de(self):
        self.app.translate('de')
        self.app.summary = 'Test-Zusammenfassung'
        self.app.description = 'Test-Beschreibung'
        self.app.save()
