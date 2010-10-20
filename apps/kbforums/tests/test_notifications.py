from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site

import mock
from nose.tools import eq_

from kbforums.models import Post, Thread
from kbforums.tasks import build_reply_notification, build_thread_notification
from kbforums.tests import KBForumTestCase
import notifications.tasks
from sumo.tests import post
from wiki.models import Document


# Some of these contain a locale prefix on included links, while others don't.
# This depends on whether the tests use them inside or outside the scope of a
# request. See the long explanation in questions.tests.test_notifications.
EMAIL_CONTENT = (
    u"""

Reply to thread: Sticky Thread

User admin has replied to a thread you're watching. Here
is their reply:

========

yet another post

========

To view this post on the site, click the following link, or
paste it into your browser's location bar:

https://testserver/kb/article-title/discuss/2#post-4
""",
    u"""

Reply to thread: Sticky Thread

User jsocol has replied to a thread you're watching. Here
is their reply:

========

a post

========

To view this post on the site, click the following link, or
paste it into your browser's location bar:

https://testserver/en-US/kb/article-title/discuss/2#post-%s
""",
    u"""

New thread: Sticky Thread

User jsocol has posted a new thread in a forum you're watching.
Here is the thread:

========

This is a sticky thread

========

To view this post on the site, click the following link, or
paste it into your browser's location bar:

https://testserver/kb/article-title/discuss/2
""",
    u"""

New thread: Awesome Thread

User jsocol has posted a new thread in a forum you're watching.
Here is the thread:

========

With awesome content!

========

To view this post on the site, click the following link, or
paste it into your browser's location bar:

https://testserver/en-US/kb/article-title/discuss/%s
""",)


class NotificationTestCase(KBForumTestCase):
    """Test that notifications get sent."""

    def setUp(self):
        super(NotificationTestCase, self).setUp()

        self.thread_ct = ContentType.objects.get_for_model(Thread).pk
        self.doc_ct = ContentType.objects.get_for_model(Document).pk

    @mock.patch_object(notifications.tasks.send_notification, 'delay')
    @mock.patch_object(Site.objects, 'get_current')
    def test_reply_notification(self, get_current, delay):
        get_current.return_value.domain = 'testserver'

        p = Post.objects.get(pk=4)
        build_reply_notification(p)

        # delay() is called twice. Verify the args.
        eq_(((self.thread_ct, p.thread.id,
             u'Reply to: Sticky Thread', EMAIL_CONTENT[0],
             (u'user1@nowhere',), 'reply'), {}), delay.call_args_list[0])
        eq_(((self.doc_ct, p.thread.document.id,
            u'Reply to: Sticky Thread', EMAIL_CONTENT[0],
            (u'user1@nowhere',), 'post'), {}), delay.call_args_list[1])

    @mock.patch_object(notifications.tasks.send_notification, 'delay')
    @mock.patch_object(Site.objects, 'get_current')
    def test_notification_on_reply(self, get_current, delay):
        get_current.return_value.domain = 'testserver'

        self.client.login(username='jsocol', password='testpass')

        t = Thread.objects.get(pk=2)
        d = t.document
        post(self.client, 'wiki.discuss.reply', {'content': 'a post'},
             args=[d.slug, t.id])
        t = Thread.objects.get(pk=2)
        p = t.last_post

        # delay() is called twice. Verify the args.
        eq_(((self.thread_ct, t.pk,
             u'Reply to: Sticky Thread', EMAIL_CONTENT[1] % p.pk,
             (u'user118533@nowhere',), 'reply'), {}), delay.call_args_list[0])
        eq_(((self.doc_ct, t.document.id,
            u'Reply to: Sticky Thread', EMAIL_CONTENT[1] % p.pk,
            (u'user118533@nowhere',), 'post'), {}), delay.call_args_list[1])

    @mock.patch_object(notifications.tasks.send_notification, 'delay')
    @mock.patch_object(Site.objects, 'get_current')
    def test_post_notification(self, get_current, delay):
        get_current.return_value.domain = 'testserver'

        post = Post.objects.get(pk=3)
        build_thread_notification(post)

        delay.assert_called_with(
                    self.doc_ct, post.thread.document.id,
                    u'New thread about document an article title: '
                    u'Sticky Thread', EMAIL_CONTENT[2],
                    (u'user118533@nowhere',), 'post')

    @mock.patch_object(notifications.tasks.send_notification, 'delay')
    @mock.patch_object(Site.objects, 'get_current')
    def test_notification_on_thread_post(self, get_current, delay):
        get_current.return_value.domain = 'testserver'

        d = Document.objects.filter()[0]
        self.client.login(username='jsocol', password='testpass')
        post(self.client, 'wiki.discuss.new_thread',
             {'title': 'Awesome Thread', 'content': 'With awesome content!'},
              args=[d.slug])
        t = Thread.objects.get(title='Awesome Thread')

        delay.assert_called_with(
                    self.doc_ct, d.id,
                    u'New thread about document an article title: '
                    u'Awesome Thread', EMAIL_CONTENT[3] % t.pk,
                    (u'user118533@nowhere',), 'post')
