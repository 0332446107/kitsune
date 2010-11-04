from nose.tools import eq_
from taggit.models import TaggedItem

from django.core.exceptions import ValidationError

from sumo import ProgrammingError
from sumo.tests import TestCase
from wiki.cron import calculate_related_documents
from wiki.models import (FirefoxVersion, OperatingSystem, Document,
                         REDIRECT_CONTENT, REDIRECT_SLUG, REDIRECT_TITLE,
                         REDIRECT_HTML)
from wiki.parser import wiki_to_html
from wiki.tests import document, revision, doc_rev


def _objects_eq(manager, list_):
    """Assert that the objects contained by `manager` are those in `list_`."""
    eq_(set(manager.all()), set(list_))


class DocumentTests(TestCase):
    """Tests for the Document model"""

    def test_document_is_template(self):
        """is_template stays in sync with the title"""
        d = document(title='test')
        d.save()

        assert not d.is_template

        d.title = 'Template:test'
        d.save()

        assert d.is_template

        d.title = 'Back to document'
        d.save()

        assert not d.is_template

    def test_delete_tagged_document(self):
        """Make sure deleting a tagged doc deletes its tag relationships."""
        # TODO: Move to wherever the tests for TaggableMixin are.
        # This works because Django's delete() sees the `tags` many-to-many
        # field (actually a manager) and follows the reference.
        d = document()
        d.save()
        d.tags.add('grape')
        eq_(1, TaggedItem.objects.count())

        d.delete()
        eq_(0, TaggedItem.objects.count())

    def _test_inheritance(self, enum_class, attr, direct_attr):
        """Test a descriptor's handling of parent delegation."""
        parent = document()
        child = document(parent=parent, title='Some Other Title')
        e1 = enum_class(item_id=1)
        parent.save()

        # Make sure child sees stuff set on parent:
        getattr(parent, attr).add(e1)
        _objects_eq(getattr(child, attr), [e1])

        # Make sure parent sees stuff set on child:
        child.save()
        e2 = enum_class(item_id=2)
        getattr(child, attr).add(e2)
        _objects_eq(getattr(parent, attr), [e1, e2])

        # Assert the data are attached to the parent, not the child:
        _objects_eq(getattr(parent, direct_attr), [e1, e2])
        _objects_eq(getattr(child, direct_attr), [])

    def test_firefox_version_inheritance(self):
        """Assert the parent delegation of firefox_version works."""
        self._test_inheritance(FirefoxVersion, 'firefox_versions',
                               'firefox_version_set')

    def test_operating_system_inheritance(self):
        """Assert the parent delegation of operating_system works."""
        self._test_inheritance(OperatingSystem, 'operating_systems',
                               'operating_system_set')

    def _test_int_sets_and_descriptors(self, enum_class, attr):
        """Test our lightweight int sets & descriptors' getting and setting."""
        d = document()
        d.save()
        _objects_eq(getattr(d, attr), [])

        i1 = enum_class(item_id=1)
        getattr(d, attr).add(i1)
        _objects_eq(getattr(d, attr), [i1])

        i2 = enum_class(item_id=2)
        getattr(d, attr).add(i2)
        _objects_eq(getattr(d, attr), [i1, i2])

    def test_firefox_versions(self):
        """Test firefox_versions attr"""
        self._test_int_sets_and_descriptors(FirefoxVersion, 'firefox_versions')

    def test_operating_systems(self):
        """Test operating_systems attr"""
        self._test_int_sets_and_descriptors(OperatingSystem,
                                            'operating_systems')

    def _test_remembering_setter_unsaved(self, field):
        """A remembering setter shouldn't kick in until the doc is saved."""
        old_field = 'old_' + field
        d = document()
        setattr(d, field, 'Foo')
        assert not hasattr(d, old_field), "Doc shouldn't have %s until it's" \
                                          "saved." % old_field

    def test_slug_setter_unsaved(self):
        self._test_remembering_setter_unsaved('slug')

    def test_title_setter_unsaved(self):
        self._test_remembering_setter_unsaved('title')

    def _test_remembering_setter(self, field):
        old_field = 'old_' + field
        d = document()
        d.save()
        old = getattr(d, field)

        # Changing the field makes old_field spring into life:
        setattr(d, field, 'Foo')
        eq_(old, getattr(d, old_field))

        # Changing it back makes old_field disappear:
        setattr(d, field, old)
        assert not hasattr(d, old_field)

        # Change it again once:
        setattr(d, field, 'Foo')

        # And twice:
        setattr(d, field, 'Bar')

        # And old_field should remain as it was, since it hasn't been saved
        # between the two changes:
        eq_(old, getattr(d, old_field))

    def test_slug_setter(self):
        """Make sure changing a slug remembers its old value."""
        self._test_remembering_setter('slug')

    def test_title_setter(self):
        """Make sure changing a title remembers its old value."""
        self._test_remembering_setter('title')

    def test_redirect_prefix(self):
        """Test accuracy of the prefix that helps us recognize redirects."""
        assert wiki_to_html(REDIRECT_CONTENT % 'foo').startswith(REDIRECT_HTML)


class RedirectTests(TestCase):
    """Tests for automatic creation of redirects when slug or title changes"""
    fixtures = ['users.json']

    def setUp(self):
        self.d, self.r = doc_rev()
        self.old_title = self.d.title
        self.old_slug = self.d.slug

    def test_change_slug(self):
        """Test proper redirect creation on slug change."""
        self.d.slug = 'new-slug'
        self.d.save()
        redirect = Document.uncached.get(slug=self.old_slug)
        # "uncached" isn't necessary, but someday a worse caching layer could
        # make it so.
        eq_(REDIRECT_CONTENT % self.d.title, redirect.current_revision.content)
        eq_(REDIRECT_TITLE % dict(old=self.d.title, number=1), redirect.title)

    def test_change_title(self):
        """Test proper redirect creation on title change."""
        self.d.title = 'New Title'
        self.d.save()
        redirect = Document.uncached.get(title=self.old_title)
        eq_(REDIRECT_CONTENT % self.d.title, redirect.current_revision.content)
        eq_(REDIRECT_SLUG % dict(old=self.d.slug, number=1), redirect.slug)

    def test_change_slug_and_title(self):
        """Assert only one redirect is made when both slug and title change."""
        self.d.title = 'New Title'
        self.d.slug = 'new-slug'
        self.d.save()
        eq_(REDIRECT_CONTENT % self.d.title,
            Document.uncached.get(
                slug=self.old_slug,
                title=self.old_title).current_revision.content)

    def test_no_redirect_on_unsaved_change(self):
        """No redirect should be made when an unsaved doc's title or slug is
        changed."""
        d = document(title='Gerbil')
        d.title = 'Weasel'
        d.save()
        # There should be no redirect from Gerbil -> Weasel:
        assert not Document.uncached.filter(title='Gerbil').exists()

    def _test_collision_avoidance(self, attr, other_attr, template):
        """When creating redirects, dodge existing docs' titles and slugs."""
        # Create a doc called something like Whatever Redirect 1:
        document(locale=self.d.locale,
                **{other_attr: template % dict(old=getattr(self.d, other_attr),
                                               number=1)}).save()

        # Trigger creation of a redirect of a new title or slug:
        setattr(self.d, attr, 'new')
        self.d.save()

        # It should be called something like Whatever Redirect 2:
        redirect = Document.uncached.get(**{attr: getattr(self,
                                                          'old_' + attr)})
        eq_(template % dict(old=getattr(self.d, other_attr),
                            number=2), getattr(redirect, other_attr))

    def test_slug_collision_avoidance(self):
        """Dodge existing slugs when making redirects due to title changes."""
        self._test_collision_avoidance('slug', 'title', REDIRECT_TITLE)

    def test_title_collision_avoidance(self):
        """Dodge existing titles when making redirects due to slug changes."""
        self._test_collision_avoidance('title', 'slug', REDIRECT_SLUG)


class RevisionTests(TestCase):
    """Tests for the Revision model"""
    fixtures = ['users.json']

    def test_approved_revision_updates_html(self):
        """Creating an approved revision updates document.html"""
        d, _ = doc_rev('Replace document html')

        assert 'Replace document html' in d.html, \
               '"Replace document html" not in %s' % d.html

        # Creating another approved revision replaces it again
        r = revision(document=d, content='Replace html again',
                     is_approved=True)
        r.save()

        assert 'Replace html again' in d.html, \
               '"Replace html again" not in %s' % d.html

    def test_unapproved_revision_not_updates_html(self):
        """Creating an unapproved revision does not update document.html"""
        d, _ = doc_rev('Here to stay')

        assert 'Here to stay' in d.html, '"Here to stay" not in %s' % d.html

        # Creating another approved revision keeps initial content
        r = revision(document=d, content='Fail to replace html')
        r.save()

        assert 'Here to stay' in d.html, '"Here to stay" not in %s' % d.html

    def test_revision_unicode(self):
        """Revision containing unicode characters is saved successfully."""
        str = u' \r\nFirefox informa\xe7\xf5es \u30d8\u30eb'
        _, r = doc_rev(str)
        eq_(str, r.content)

    def test_save_bad_based_on(self):
        """Saving a Revision with a bad based_on value raises an error."""
        r = revision()
        r.based_on = revision()  # Revision of some other unrelated Document
        self.assertRaises(ProgrammingError, r.save)

    def test_correct_based_on_to_none(self):
        """Assure Revision.clean() changes a bad based_on value to None when
        there is no current_revision of the English document."""
        r = revision()
        r.based_on = revision()  # Revision of some other unrelated Document
        self.assertRaises(ValidationError, r.clean)
        eq_(None, r.based_on)

    def test_correct_based_on_to_current_revision(self):
        """Assure Revision.clean() changes a bad based_on value to the English
        doc's current_revision when there is one."""
        # Make English rev:
        en_rev = revision(is_approved=True)
        en_rev.save()

        # Make Deutsch translation:
        de_doc = document(parent=en_rev.document, locale='de')
        de_doc.save()
        de_rev = revision(document=de_doc)

        # Set based_on to some random, unrelated Document's rev:
        de_rev.based_on = revision()

        # Try to recover:
        self.assertRaises(ValidationError, de_rev.clean)

        eq_(en_rev.document.current_revision, de_rev.based_on)

    def test_only_localizable_allowed_children(self):
        """You can't have children for a non-localizable document."""
        # Make English rev:
        en_doc = document(is_localizable=False)
        en_doc.save()

        # Make Deutsch translation:
        de_doc = document(parent=en_doc, locale='de')
        self.assertRaises(ValidationError, de_doc.save)

    def test_cannot_make_non_localizable_if_children(self):
        """You can't make a document non-localizable if it has children."""
        # Make English rev:
        en_doc = document(is_localizable=True)
        en_doc.save()

        # Make Deutsch translation:
        de_doc = document(parent=en_doc, locale='de')
        de_doc.save()
        en_doc.is_localizable = False
        self.assertRaises(ValidationError, en_doc.save)


class RelatedDocumentTestCase(TestCase):
    fixtures = ['users.json', 'wiki/documents.json']

    def test_related_documents_calculated(self):
        d = Document.uncached.get(pk=1)
        eq_(0, d.related_documents.count())

        calculate_related_documents()

        d = Document.uncached.get(pk=1)
        eq_(2, d.related_documents.count())

    def test_related_only_locale(self):
        calculate_related_documents()
        d = Document.uncached.get(pk=1)
        for rd in d.related_documents.all():
            eq_('en-US', rd.locale)

    def test_only_approved_revisions(self):
        calculate_related_documents()
        d = Document.uncached.get(pk=1)
        for rd in d.related_documents.all():
            assert rd.current_revision

    def test_only_approved_have_related(self):
        calculate_related_documents()
        d = Document.uncached.get(pk=3)
        eq_(0, d.related_documents.count())
