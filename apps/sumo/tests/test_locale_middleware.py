from sumo.tests import TestCase


class TestLocaleMiddleware(TestCase):
    def test_default_redirect(self):
        # User wants en-us, we send en-US
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='en-us')
        self.assertRedirects(response, '/en-US/search', status_code=302)

        # User wants fr-FR, we send fr
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='fr-fr')
        self.assertRedirects(response, '/fr/search', status_code=302)

        # User wants xx, we send en-US
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='xx')
        self.assertRedirects(response, '/en-US/search', status_code=302)

        # User doesn't know what they want, we send en-US
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='')
        self.assertRedirects(response, '/en-US/search', status_code=302)

    def test_mixed_case_header(self):
        """Accept-Language is case insensitive."""
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='en-US')
        self.assertRedirects(response, '/en-US/search', status_code=302)

    def test_specificity(self):
        """Requests for /fr-FR/search should end up on /fr/search"""
        reponse = self.client.get('/fr-FR/search', follow=True)
        self.assertRedirects(reponse, '/fr/search', status_code=302)

    def test_partial_redirect(self):
        """Ensure that /en/ gets directed to /en-US/."""
        response = self.client.get('/en/search', follow=True)
        self.assertRedirects(response, '/en-US/search', status_code=302)

    def test_lower_to_upper(self):
        """/en-us should redirect to /en-US."""
        response = self.client.get('/en-us/search', follow=True)
        self.assertRedirects(response, '/en-US/search', status_code=302)

    def test_upper_accept_lang(self):
        """'en-US' and 'en-us' are both OK in Accept-Language."""
        response = self.client.get('/search', follow=True,
                                   HTTP_ACCEPT_LANGUAGE='en-US,fr;q=0.3')
        self.assertRedirects(response, '/en-US/search', status_code=302)
