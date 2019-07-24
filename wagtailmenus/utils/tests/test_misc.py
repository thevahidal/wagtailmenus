from unittest import mock

from django.http import Http404
from django.test import RequestFactory, TestCase
from wagtail.core.models import Page, Site

from wagtailmenus.conf import defaults
from wagtailmenus.utils.misc import (
    derive_page, derive_section_root, derive_page, get_site_from_request
)
from wagtailmenus.tests.models import (
    ArticleListPage, ArticlePage, LowLevelPage, TopLevelPage
)

request_factory = RequestFactory()


class TestDerivePage(TestCase):
    """Tests for wagtailmenus.utils.misc.derive_page()"""
    fixtures = ['test.json']

    def setUp(self):
        self.site = Site.objects.select_related('root_page').first()
        # Prefetch the specific page, so that it doesn't count
        # toward the counted queries
        self.site.root_page.specific

    def _run_test(
        self, url, expected_page, expected_num_queries, full_url_match_expected,
        accept_best_match=True, max_subsequent_route_failures=3
    ):
        request = request_factory.get(url)
        # Set these to improve efficiency
        request.site = self.site
        request._wagtail_cached_site_root_paths = Site.get_site_root_paths()
        # Run tests
        with self.assertNumQueries(expected_num_queries):
            page, full_url_match = derive_page(
                request,
                self.site,
                accept_best_match,
                max_subsequent_route_failures,
            )
            self.assertEqual(page, expected_page)
            self.assertIs(full_url_match, full_url_match_expected)

    def test_simple_full_url_match(self):
        """
        Routing should use 4 queries here:
        1. Look up 'superheroes' from site root
        2. Fetch specific version of 'superheroes'
        3. Look up 'marvel-comics' from 'superheroes'
        4. Fetch specific version of 'marvel-comics'
        """
        self._run_test(
            url='/superheroes/marvel-comics/',
            expected_page=LowLevelPage.objects.get(slug='marvel-comics'),
            expected_num_queries=4,
            full_url_match_expected=True,
        )

    def test_article_list_full_url_match(self):
        """
        Routing should use 4 queries here:
        1. Look up 'news-and-events' from site root
        2. Fetch specific version of 'news-and-events'
        3. Look up 'latest-news' from 'news-and-events'
        4. Fetch specific version of 'latest-news'
        """
        self._run_test(
            url='/news-and-events/latest-news/2016/04/',
            expected_page=ArticleListPage.objects.get(slug='latest-news'),
            expected_num_queries=4,
            full_url_match_expected=True,
        )

    def test_article_full_url_match(self):
        """
        Routing should use 5 queries here:
        1. Look up 'news-and-events' from site root
        2. Fetch specific version of 'news-and-events'
        3. Look up 'latest-news' from 'news-and-events'
        4. Fetch specific version of 'latest-news'
        5. Look up 'article-one' from 'latest-news'
        """
        self._run_test(
            url='/news-and-events/latest-news/2016/04/18/article-one/',
            expected_page=ArticlePage.objects.get(slug='article-one'),
            expected_num_queries=5,
            full_url_match_expected=True,
        )

    def test_simple_partial_match(self):
        """
        Routing should use 4 queries here:
        1. Look up 'about-us' from site root
        2. Fetch specific version of 'about-us'
        3. Attempt to look up 'blah' from 'about-us'
        """
        self._run_test(
            url='/about-us/blah/',
            expected_page=TopLevelPage.objects.get(slug='about-us'),
            expected_num_queries=3,
            full_url_match_expected=False,
        )

    def test_article_list_partial_match(self):
        """
        Routing should use 4 queries here:
        1. Look up 'news-and-events' from site root
        2. Fetch specific version of 'news-and-events'
        3. Look up 'latest-news' from 'news-and-events'
        4. Fetch specific version of 'latest-news'
        5. Attempt to look up 'blah' from 'latest-news'
        6. Attempt to look up 'blah/blah/' from 'latest-news'
        """
        self._run_test(
            url='/news-and-events/latest-news/2016/04/01/blah/blah/',
            expected_page=ArticleListPage.objects.get(slug='latest-news'),
            expected_num_queries=6,
            full_url_match_expected=False,
        )

    def test_partial_match_with_max_subsequent_route_failures(self):
        """
        Routing should use 5 queries here:
        1. Look up 'about-us' from site root
        2. Fetch specific version of 'about-us'
        3. Attempt to look up 'blah' from 'about-us'
        4. Attempt to look up 'blah/blah/' from 'about-us'
        5. Attempt to look up 'blah/blah/blah/' from 'about-us'
        """
        self._run_test(
            url='/about-us/blah/blah/blah/blah/blah',
            expected_page=TopLevelPage.objects.get(slug='about-us'),
            expected_num_queries=5,
            full_url_match_expected=False,
        )

    def test_no_match(self):
        """
        This test also shows that using the ``max_subsequent_route_failures`` option
        directly affects the number of route() attempts that will be made, even when
        """
        common_test_kwargs = {
            'url': '/blah/blah/blah/blah/blah',
            'expected_page': None,
            'full_url_match_expected': False,
        }
        for i in range(1, 3):
            self._run_test(
                expected_num_queries=i,
                max_subsequent_route_failures=i,
                **common_test_kwargs
            )

    def test_exact_match_only_with_success(self):
        self._run_test(
            url='/about-us/',
            expected_page=TopLevelPage.objects.get(slug='about-us'),
            expected_num_queries=2,
            full_url_match_expected=True,
            accept_best_match=False
        )

    def test_exact_match_only_without_success(self):
        self._run_test(
            url='/blah/blah/blah/blah/blah',
            expected_page=None,
            expected_num_queries=1,
            full_url_match_expected=False,
            accept_best_match=False
        )


class TestDeriveSectionRoot(TestCase):
    """Tests for wagtailmenus.utils.misc.derive_section_root()"""
    fixtures = ['test.json']

    def setUp(self):
        self.page_with_depth_of_2 = Page.objects.get(
            depth=2, url_path='/home/'
        )
        self.page_with_depth_of_3 = Page.objects.get(
            depth=3, url_path='/home/about-us/'
        )
        self.page_with_depth_of_4 = Page.objects.get(
            depth=4, url_path='/home/about-us/meet-the-team/'
        )
        self.page_with_depth_of_5 = Page.objects.get(
            depth=5, url_path='/home/about-us/meet-the-team/staff-member-one/'
        )

    def test_returns_same_page_if_provided_page_is_section_root(self):
        # Using the default section root depth of 3
        with self.assertNumQueries(1):
            # One query should be used to get the specific page
            result = derive_section_root(self.page_with_depth_of_3)
            # The function should return the specific version of the same page
            self.assertEqual(result, self.page_with_depth_of_3.specific)

        # Using a custom section root depth of 4
        with self.settings(WAGTAILMENUS_SECTION_ROOT_DEPTH=4):
            with self.assertNumQueries(1):
                # One query should be used to get the specific page
                result = derive_section_root(self.page_with_depth_of_4)
                # The function should return the specific version of the same page
                self.assertEqual(result, self.page_with_depth_of_4.specific)

    def test_returns_section_root_if_provided_page_is_a_descendant_of_one(self):
        # Using the default section root depth of 3
        with self.assertNumQueries(2):
            # Two queries should be used to identify the page
            # and to get the specific version
            result = derive_section_root(self.page_with_depth_of_5)
            self.assertEqual(result.depth, defaults.SECTION_ROOT_DEPTH)
            self.assertIsInstance(result, TopLevelPage)

        # Using a custom section root depth of 4
        with self.settings(WAGTAILMENUS_SECTION_ROOT_DEPTH=4):
            with self.assertNumQueries(2):
                result = derive_section_root(self.page_with_depth_of_5)
                self.assertEqual(result.depth, 4)
                self.assertIsInstance(result, LowLevelPage)

    def test_returns_none_if_provided_page_is_not_a_descendant_of_a_section_root(self):
        # Using the default section root depth of 3
        with self.assertNumQueries(0):
            result = derive_section_root(self.page_with_depth_of_2)
            self.assertIs(result, None)

        # Using a custom section root depth of 4
        with self.settings(WAGTAILMENUS_SECTION_ROOT_DEPTH=4):
            with self.assertNumQueries(0):
                result = derive_section_root(self.page_with_depth_of_3)
                self.assertIs(result, None)



class TestGetSiteFromRequest(TestCase):

    @mock.patch.object(Site, 'find_for_request')
    def test_returns_site_attribute_from_request_if_a_site_object(self, mocked_method):
        request = request_factory.get('/')
        dummy_site = Site(hostname='beepboop')
        request.site = dummy_site

        result = get_site_from_request(request)
        self.assertIs(result, dummy_site)
        self.assertFalse(mocked_method.called)

    @mock.patch.object(Site, 'find_for_request')
    def test_find_for_request_called_if_site_attribute_is_not_a_site_object(self, mocked_method):
        request = request_factory.get('/')
        request.site = 'just a string'

        get_site_from_request(request)
        self.assertTrue(mocked_method.called)

    @mock.patch.object(Site, 'find_for_request', side_effect=Site.DoesNotExist())
    def test_returns_none_if_find_for_request_raises_doesnotexist_error(self, mocked_method):
        request = request_factory.get('/')
        result = get_site_from_request(request)
        self.assertIs(result, None)


class TestGetPageFromRequest(TestCase):

    @mock.patch.object(Page, 'route', side_effect=Http404('Not found'))
    def test_attempts_match_until_path_components_are_exhausted(self, mocked_method):
        path = '/news-and-events/latest-news/blah/'
        path_components = [pc for pc in path.split('/') if pc]
        request = request_factory.get(path)
        site = Site.objects.first()

        derive_page(request, site=site)
        self.assertEqual(mocked_method.call_count, len(path_components))

    @mock.patch.object(Page, 'route', side_effect=Http404('Not found'))
    def test_attempts_only_once_if_accept_best_match_is_false(self, mocked_method):
        request = request_factory.get('/news-and-events/latest-news/blah/')
        site = Site.objects.first()

        derive_page(request, site=site, accept_best_match=False)
        self.assertEqual(mocked_method.call_count, 1)

    @mock.patch.object(Page, 'route', return_value=(1, 2, 3))
    def test_exact_match_is_true_if_result_found_on_first_attempt(self, mocked_method):
        request = request_factory.get('/news-and-events/latest-news/blah/')
        site = Site.objects.first()

        page, exact_match = derive_page(request, site)
        self.assertIs(exact_match, True)

    @mock.patch.object(Page, 'route', side_effect=[Http404('Not found'), (1, 2, 3)])
    def test_exact_match_is_false_if_result_found_on_consecutive_attempt(self, mocked_method):
        request = request_factory.get('/news-and-events/latest-news/blah/')
        site = Site.objects.first()

        page, exact_match = derive_page(request, site)
        self.assertIs(exact_match, False)
