import urllib
from django.test.utils import override_settings
from django.test import TestCase

from unittest import skipUnless, skip, skipIf
from unittest.case import SkipTest
from django.test.client import Client
import os
from django_fixmystreet.models import (Report,
                                       ApiKey,
                                       ReportCategorySet,
                                       FMSUser,
                                       ReportCategory,
                                       City)


from django.contrib.auth.models import AnonymousUser

from django.test.client import RequestFactory
from django_fixmystreet.views.mobile import open311v2

import xml.dom.minidom
from django.core import mail


from django.conf import settings
from django.utils.importlib import import_module

from pprint import pprint

import json as js

PATH = os.path.dirname(__file__)

API_KEY = 'Test Mobile API'
API_PASS = 'test_mobile_api_key'


def make_request(method, *a, **k):
    rf = RequestFactory()
    r = getattr(rf, method)(*a, **k)
    engine = import_module(settings.SESSION_ENGINE)
    session_key = r.COOKIES.get(
        settings.SESSION_COOKIE_NAME, None)
    r.session = engine.SessionStore(session_key)
    r.user = AnonymousUser()
    return r

ANON_CREATE_PARAMS =  {
    'api_key': API_KEY,
    'api_pass': API_PASS,
    'lat': '45.4198266',
    'lon': '-75.6943189',
    'device_id': '411',
    'service_code': 5,
    'location': 'Some Street',
    'first_name': 'John',
    'last_name':'Farmer',
    'title': 'Submitted by our mobile app',
    'description': ('The description of a mobile '
                    'submitted report'),
    'email': 'testuser@hotmail.com',
    'phone': '514-513-0475'
}

LOGGEDIN_CREATE_PARAMS =  {
    'title': 'A report from our API from a logged in user',
    'email': 'testuser@hotmail.com',
    'api_key': API_KEY,
    'api_pass': API_PASS,
    'device_id': '411',
    'lat': '45.4301269580000024',
    'lon': '-75.6824648380000014',
    'location': 'Some Street',
    'service_code': 5,
    'description': 'The description',
}

EXPECTED_ERRORS = {
    'lat': ['lat:This field is required.'],
    'lon': ['lon:This field is required.'],
    'service_code': ['service_code:This field is required.'],
    'first_name':  None,
    'last_name': None,
    'title': None,
    'description': ['description:This field is required.'],
    'email': ['email:This field is required.'],
    'phone': None,
    'api_key': ['description:This field is required.']
}


def skipBaseClass(func, *args, **kw):
    def callme(self, *fa, **fk):
        if not self.base_class:
            return func(self, *fa, **fk)
        else:
            raise SkipTest('base class')
    return callme

@override_settings(SITE_ID=1)
class Open311v2(TestCase):

    fixtures = ['test_mobile.json']
    c = Client()
    content_type = None
    base_class = True

    def _create_request(self,
                        params,
                        expected_errors=None,
                        anon=False,
                        error_code=400,
                        api_key = API_KEY,
                        debug=False,
                       ):
        doc, data = None, None
        countb = Report.objects.filter(
            api_key=self.api_key(key=api_key),
            device_id=params['device_id'],
            desc=params.get('description', 'notset')
        ).count()
        mailb = len(mail.outbox)
        if debug:
            params['debug'] = 'true'
        response = self.c.post(
            self._reportsUrl(anon=anon),
            params, **{ "wsgi.url_scheme" : "https" })
        if self.content_type in ['json']:
            data = js.loads(response.content)
        else:
            doc = xml.dom.minidom.parseString(
                response.content)
        if not expected_errors:
            maila = len(mail.outbox)
            counta = Report.objects.filter(
                api_key=self.api_key(key=api_key),
                device_id=params['device_id'],
                desc=params['description']
            ).count()
            self.assertEquals(response.status_code, 200)
            try:
                self.assertEqual(counta-countb, 1,
                                 'no report created!')
            except:
                if debug:
                    import pdb;pdb.set_trace()  ## Breakpoint ##
                raise

            try:
                self.assertTrue(
                    ('submitted report'
                    in unicode(mail.outbox[-1].message()))
                    or ('Submitted via'
                    in unicode(mail.outbox[-1].message()))
                )
            except:
                if debug:
                    import pdb;pdb.set_trace()  ## Breakpoint ##
                raise

            if anon:
                self.assertEquals(
                    mail.outbox[-1].to,
                    ['testuser@hotmail.com'])
            nbelems = 0
            if data is not None:
                nbelems = len(data)
            else:
                nbelems = len(doc.getElementsByTagName(
                        'service_request_id'))
            self.assertEqual(
                nbelems , 1,
                "there is a request id in the response")
            if data is not None:
                request_id = data[0]['service_request_id']
            else:
                request_id = doc.getElementsByTagName(
                    'service_request_id'
                )[0].childNodes[0].data
            self.assertTrue(
                int(request_id)>= int('6'),
                "we've created a new "
                "request: %s" % request_id)
        else:
            try:
                self.assertEquals(response.status_code,
                              error_code)
            except:
                import pdb;pdb.set_trace()  ## Breakpoint ##
                raise

            if data is not None:
                errors = data['errors']
            else:
                errors = [dict( [
                    ('code', 'foo'),
                    ('description',
                     a.childNodes[0].data[4:])
                ])
                    for a in doc.getElementsByTagName(
                        'description')]

            if len(errors) < len(expected_errors):
                for error in errors:
                    print error
            content = response.content
            self.assertFalse(
                len(errors) <
                len(expected_errors),
                '%s!=%s' % ([a['description']
                             for a in errors],
                            expected_errors))
            for error in errors:
                self.assertTrue(
                    error['description'] in expected_errors,
                    '%s NOT FOUND in %s.\nError are: %s' % (
                        [error['description']],
                        expected_errors,
                        errors,
                    )
                )
        return data

    def api_key(self, key=API_PASS):
        return ApiKey.objects.get(organization=key)

    def _url(self, url,
             params = None,
             anon=True,
             api_key = API_KEY,
             api_pass = API_PASS,
             sep=None,
            ):
        p = {}
        if not params:
            params = {}
        p.update(params)
        url = '/open311/v2/%s' % url
        if not anon:
            p.update({'api_pass': api_pass,
                      'api_key': api_key, })
        if sep is None:
            if '?' in url:
                sep = '&'
            else:
                sep = '?'
        # do no add alreazdy exiting params
        for k in p.keys():
            if ('%s=' % k) in url:
                del p[k]
        url = '%s%s%s' % (url, sep, urllib.urlencode(p))
        return url


    def _reportUrl(self,
                   id = 1,
                   params=None,
                   anon=False,
                   api_key=API_KEY,
                   api_pass=API_PASS,
                  ):
        url = self._url(
            'requests/%s.%s' % (
                id,
                self.content_type,
            ),
            params=params,
            anon=anon,
            api_key=api_key,
            api_pass=api_pass,
        )
        return url

    def _reportsUrl(self,
                    params=None,
                    anon=False,
                    api_key=API_KEY,
                    api_pass=API_PASS,
                   ):
        url = self._url('requests.%s' % self.content_type,
                        params=params,
                        anon=anon,
                        api_key=api_key,
                        api_pass=api_pass,
                       )
        return url


    def _jurisdictionsUrl(self,
                     params=None,
                     anon=False,
                     api_key=API_KEY,
                     api_pass=API_PASS,
                    ):
        url = self._url(
            'jurisdictions.%s' % self.content_type,
            params=params,
            anon=anon,
            api_key=api_key,
            api_pass=api_pass,
        )
        return url

    def _servicesUrl(self,
                     params=None,
                     anon=False,
                     api_key=API_KEY,
                     api_pass=API_PASS,
                    ):
        url = self._url(
            'services.%s' % self.content_type,
            params=params,
            anon=anon,
            api_key=api_key,
            api_pass=api_pass,
        )
        return url

    @skipBaseClass
    def test_get_report(self):
        url = (self._reportUrl()
               + '&jurisdiction_id=oglo_on.fixmystreet.ca')
        response = self.c.get(url)
        self._expect(response, 'get_report_1')



    @skipBaseClass
    def test_get_services_by_latlon(self):
        url = (self._servicesUrl()
               + ('&lat=45.4301269580000024'
                  '&lon=-75.6824648380000014'))
        self._test_get_services(url)

    @skipBaseClass
    def test_get_services_by_unspecified(self):
        url = self._servicesUrl()
        response = self.c.get(url)
        # change this to 400
        self.assertEquals(response.status_code, 404)

    @skipBaseClass
    def test_get_services_by_bad_jurid(self):
        url = (self._servicesUrl()
               + '&jurisdiction_id=doesnt_exist')
        response = self.c.get(url)
        self.assertEquals(response.status_code,404)

    @skipBaseClass
    def test_get_services_by_bad_latlon(self):
        url = (self._servicesUrl()
               + ('&lat=-45.4301269580000024'
                  '&lon=75.6824648380000014'))
        response = self.c.get(url)
        self.assertEquals(response.status_code,404)



    @skipBaseClass
    def test_get_by_lat_lon(self):
        params = { 'lon': '-75.6824648380000014',
                   'lat': '45.4301269580000024'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        self._expect(response, 'get_reports')

    @skipBaseClass
    def test_get_by_date_range(self):
        params = { 'start_date' : '2009-02-02',
                   'end_date' : '2009-02-03'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        self._expect(response, 'get_report_2')

    @skipBaseClass
    def test_get_by_end_date(self):
        params =  { 'end_date': '2009-02-02'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        self._expect(response, 'get_report_1')

    @skipBaseClass
    def test_get_by_start_date(self):
        params =  { 'start_date': '2009-02-04'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        self._expect(response, 'get_report_4')

    @skipBaseClass
    def test_anon_refused(self):
        for callb in [getattr(self, a) for a in (
            '_reportsUrl',
            '_reportUrl',
            '_servicesUrl',
        )]:
            url = callb(anon=True)
            response = self.c.get(url)
            self.assertEquals(response.status_code, 403)
        data = ANON_CREATE_PARAMS.copy()
        del data['api_pass']
        del data['api_key']
        self._create_request(
            data,
            anon=True,
            expected_errors = [(
                "Missing api_key "
                "-- can't proceed with fms: reports API")],
            error_code = 403,
        )

    @skipBaseClass
    def _test_post_missing(self,
                           field,
                           error_code=400,
                           debug=False):
        params = ANON_CREATE_PARAMS.copy()
        del(params[field])
        self._create_request(
            params,
            expected_errors=EXPECTED_ERRORS[field],
            error_code=error_code, debug=debug)

    @skipBaseClass
    def test_post_missing_title(self):
        self._test_post_missing('title')

    @skipBaseClass
    def test_post_missing_email(self):
        self._test_post_missing('email')

    @skipBaseClass
    def test_post_missing_phone(self):
        self._test_post_missing('phone', 200)

    @skipBaseClass
    def test_post_missing_lname(self):
        self._test_post_missing('last_name', 200)

    @skipBaseClass
    def test_post_missing_fname(self):
        self._test_post_missing('first_name', 200)

    @skipBaseClass
    def test_post_missing_scode(self):
        self._test_post_missing('service_code')

    @skipBaseClass
    def test_post_missing_desc(self):
        self._test_post_missing('description', debug=True)

    @skipBaseClass
    def test_post_missing_lat(self):
        self._test_post_missing('lat')

    @skipBaseClass
    def test_post_multi_missing(self):
        params = ANON_CREATE_PARAMS.copy()
        del(params['lat'])
        del(params['service_code'])
        errors = (EXPECTED_ERRORS['lat']
                  + EXPECTED_ERRORS['service_code'])
        self._create_request(params, errors)

    @skipBaseClass
    def test_bad_latlon(self):
        params = LOGGEDIN_CREATE_PARAMS.copy()
        params['lat'] = '22.3232323'
        expect = [#u'last_name:This field is required.',
                  #u'email:This field is required.',
                  u'__all__:lat/lon not supported']
        self._create_request(params,
                             expected_errors=expect,
                             debug=True)



    @skipBaseClass
    def test_post_missing_api_key(self):
        params = LOGGEDIN_CREATE_PARAMS.copy()
        del(params[ 'api_key' ])
        self._create_request(
            params,
            anon=True,
            expected_errors = [
                "Missing api_key -- "
                "can't proceed with fms: reports API"],
            error_code=403)

    @skipBaseClass
    def test_bad_api_key(self):
        params = ANON_CREATE_PARAMS.copy()
        params[ 'api_key' ] = 'bad api key'
        self._create_request(
            params,
            ["Invalid api_key received for 'bad api key'"
             " -- can't proceed with fms: reports API"],
            error_code=403)

    @skipBaseClass
    def _test_get_services(self, url):
        response = self.c.get(url)
        # check that the default is as expected.
        self._expect(response, 'get_default_services')

        # now, change the services available in the city.
        new_categoryset = ReportCategorySet.objects.create(
            name='modified')
        for category in ReportCategory.objects.filter(
            category_class__name_en='Parks'):
            new_categoryset.categories.add(category)
        new_categoryset.save()
        city = City.objects.get(name='Oglo')
        city.category_set = new_categoryset
        city.save()

        response = self.c.get(url)
        # check that the default is as expected.
        self._expect(response, 'get_modified_services')

    def _expect(self, response, filename):
        raise Exception('not implemented')


    def verify(self, r, ref):
        if not isinstance(ref, list):
            ref = [ref]
        if not isinstance(r, list):
            r = [r]
        self.assertEquals(len(r), len(ref))
        for i, item in enumerate(ref):
            for k in item:
                if not k in r[i]:
                    self.fails(
                        '%s absent from %s REF:%s' % (
                            k, r[i], ref))


        for i, item in enumerate(r):
            for k in item:
                if not k in ref[i]:
                    self.fails('%s from %s not in REF:%s' % (
                        k, r[i], item))
                self.assertEquals(item[k], ref[i][k])


class Open311v2JSON(Open311v2):
    fixtures = ['test_mobile.json']
    content_type = 'json'
    base_class = False

    @skipBaseClass
    def test_get_by_srid(self):
        params = {'service_request_id': '1'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        data = js.loads(response.content)
        self._expect(response, 'get_report_1')
        params = {'service_request_id': '666'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        data = js.loads(response.content)
        self.assertEquals(len(data), 0)

    @skipBaseClass
    def test_get_services_by_jurid(self):
        url = (self._servicesUrl()
               + '&jurisdiction_id=oglo_on.fixmystreet.ca')
        self._test_get_services(url)
 

    def get_reports(self, response):
        REF = [{
            "service_request_id": 4,
            "title": "Fixed in 16 Days",
            "status": "closed",
            "service_code": 5,
            "service_name": "Grafitti: Graffiti On City Property",
            "description": "Parks!",
            "requested_datetime": "2009-02-04T15:11:49",
            "updated_datetime": "2009-02-09T19:35:16",
            "lon": -75.682464838,
            "lat": 45.430126958,
            "address": "Dalhousie, Oglo"
        },
            {
                "service_request_id": 3,
                "title": "Fixed in Two Days",
                "status": "closed",
                "service_code": 1,
                "service_name": "Parks: Broken or Damaged Equipment/Play Structures",
                "description": "Here's a description with a lot of 'escapes' in it.\r\n\r\nAnd linebreaks!",
                "requested_datetime": "2009-02-03T16:47:06",
                "updated_datetime": "2009-02-03T16:47:06",
                "lon": -75.682464838,
                "lat": 45.430126958,
                "address": "Caldaver, Oglo"
            },
            {
                "service_request_id": 2,
                "title": "Unfixed 2",
                "status": "open",
                "service_code": 1,
                "service_name": "Parks: Broken or Damaged Equipment/Play Structures",
                "description": "Here's a description with a lot of 'escapes' in it.\r\n\r\nAnd linebreaks!",
                "requested_datetime": "2009-02-02T16:47:06",
                "updated_datetime": "2010-02-02T16:47:06",
                "lon": -75.6965517998,
                "lat": 45.418741558,
                "address": "Caldaver, Oglo"
            },
            {
                "service_request_id": 1,
                "title": "Unfixed 1",
                "status": "open",
                "service_code": 5,
                "service_name": "Grafitti: Graffiti On City Property",
                "description": "Here's a description with a lot of 'escapes' in it.\r\n\r\nAnd linebreaks!",
                "requested_datetime": "2009-02-01T16:47:06",
                "updated_datetime": "2010-02-01T16:47:06",
                "lon": -75.6965517998,
                "lat": 45.418741558,
                "address": "Caldaver, Oglo"
            }]
        data = js.loads(response.content)
        self.verify(data, REF)

    def get_report_4(self, response):
        REF = {
            "service_request_id": 4,
            "title": "Fixed in 16 Days",
            "status": "closed",
            "service_code": 5,
            "service_name": "Grafitti: Graffiti On City Property",
            "description": "Parks!",
            "requested_datetime": "2009-02-04T15:11:49",
            "updated_datetime": "2009-02-09T19:35:16",
            "lon": -75.682464838,
            "lat": 45.430126958,
            "address": "Dalhousie, Oglo"
        }
        data = js.loads(response.content)
        self.verify(data[0], REF)


    def get_report_1(self, response):
        data = js.loads(response.content)
        REF = {
            "service_request_id": 1,
            "title": "Unfixed 1",
            "status": "open",
            "service_code": 5,
            "service_name": "Grafitti: Graffiti On City Property",
            "description": "Here's a description with a lot of 'escapes' in it.\r\n\r\nAnd linebreaks!",
            "requested_datetime": "2009-02-01T16:47:06",
            "updated_datetime": "2010-02-01T16:47:06",
            "lon": -75.6965517998,
            "lat": 45.418741558,
            "address": "Caldaver, Oglo"}
        self.verify(data[0], REF)

    def get_report_2(self, response):
        data = js.loads(response.content)
        REF = {
            u'address': u'Caldaver, Oglo',
            u'description': u"Here's a description with a lot of 'escapes' in it.\r\n\r\nAnd linebreaks!",
            u'lat': 45.418741558,
            u'lon': -75.6965517998,
            u'requested_datetime': u'2009-02-02T16:47:06',
            u'service_code': 1,
            u'service_name': u'Parks: Broken or Damaged Equipment/Play Structures',
            u'service_request_id': 2,
            u'status': u'open',
            u'title': u'Unfixed 2',
            u'updated_datetime': u'2010-02-02T16:47:06'}
        self.verify(data[0], REF)


    @skipBaseClass
    def test_get_services_by_jurid_int(self):
        url = self._servicesUrl() + '&jurisdiction_id=1'
        self._test_get_services(url)

    def get_modified_services(self, response):
        REF = [
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 1,
                "service_name": "Broken or Damaged Equipment/Play Structures",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 3,
                "service_name": "Lights Malfunctioning in Park",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 4,
                "service_name": "Debris or Litter in Park",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 2,
                "service_name": "Full or Overflowing Garbage Cans ",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            }]
        data = js.loads(response.content)
        self.verify(data, REF)

    def get_default_services(self, response):
        REF = [
            {
                "group": "Grafitti",
                "description": "Please note as much information regarding the location and type of graffiti as you can. If it is found on a utility box, what colour is the box? (green, brown, red, etc...), does it indicate the company that owns it? (Rogers, Bell, Canada Post, Hydro), and which side of the street is it on.",
                "service_code": 7,
                "service_name": "Graffiti  on Utility Boxes/Transformers/Mailboxes, etc..",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Grafitti",
                "description": "Please note as much information regarding the location and type of graffiti as you can. For example, if it is found on a utility box, what colour is the box? (green, brown, red, etc...), does it indicate the company that owns it? (Rogers, Bell, Canada Post, Hydro), and which side of the street is it on.",
                "service_code": 6,
                "service_name": "Graffiti on Private Property",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Grafitti",
                "description": "Please note as much information regarding the location and type of graffiti as you can. ",
                "service_code": 5,
                "service_name": "Graffiti On City Property",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 2,
                "service_name": "Full or Overflowing Garbage Cans ",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 1,
                "service_name": "Broken or Damaged Equipment/Play Structures",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
            {
                "group": "Parks",
                "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
                "service_code": 3,
                "service_name": "Lights Malfunctioning in Park",
                "keywords": "",
                "type": "realtime",
                "metadata": "false"
            },
        {
            "group": "Parks",
            "description": "Please provide the location within the park where the problem is located (e.g. near the play structure; along the pathway that runs from the south end of the park to the neighbouring school; beside the water fountain near the east parking lot). Please provide the name or address of the park if possible.",
            "service_code": 4,
            "service_name": "Debris or Litter in Park",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 13,
            "service_name": "Damaged Guardrails",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 9,
            "service_name": "Pothole",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road). Indicating the shape of the catch basin or manhole cover will be very helpful.",
            "service_code": 8,
            "service_name": "Blocked or damaged Catch basin / Manhole",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 16,
            "service_name": "Debris/Litter in Bus Shelter",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road). ",
            "service_code": 15,
            "service_name": "Bus Shelter Damaged",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 11,
            "service_name": "Debris or Litter on Road/Sidewalk/Pathway",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 14,
            "service_name": "Full or Overflowing Garbage Cans",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road). ",
            "service_code": 12,
            "service_name": "Blocked or Damaged Culvert",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Roads/Sidewalks/Pathways",
            "description": "Please be as detailed as possible in describing the location of the problem. For example, the 3rd catch basin along Laurier Avenue W, east of Elgin Street; the curb in front of 110 Laurier Ave W on the north side of the road; bus shelter 1234 on Innes Road).",
            "service_code": 10,
            "service_name": "Damaged Curb",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Traffic Signals",
            "description": "Please try to be as detailed as possible in describing the location of the problem. For example, \"the 4th street light along Trail Side Circle, east of Valin Street\".",
            "service_code": 17,
            "service_name": "Street Lights Out or Malfunctioning",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Traffic Signals",
            "description": "Please try to be as detailed as possible in describing the location of the problem. For example, \"the yellow sign with black bars across it; the solid yellow line on the pavement\".",
            "service_code": 18,
            "service_name": "Faded/Damaged/Missing Pavement Markings",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Traffic Signals",
            "description": "Please try to be as detailed as possible in describing the location of the problem.",
            "service_code": 19,
            "service_name": "Bent/Damaged/Missing Street Signs",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        },
        {
            "group": "Trees",
            "description": "If possible, please specify whether the tree causing the problem is on private property or city property.",
            "service_code": 20,
            "service_name": "Branches Blocking Signs or Intersection",
            "keywords": "",
            "type": "realtime",
            "metadata": "false"
        }
        ]
        data = js.loads(response.content)
        self.verify(data, REF)

    def _expect(self, response, filename):
        return getattr(self, filename)(response)


    @skipBaseClass
    def test_login(self):
        uc = len(FMSUser.objects.all())
        params = {}
        mailb = len(mail.outbox)
        self.assertEquals(
            len(FMSUser.objects.filter(
                email='foo@foo.com')), 0)
        # first we try to login with a non existing user
        # as we do not provide enought info, we are out
        try:
            r = make_request('post', '/foo', params)
            user = open311v2.json.login(r)
            self.fails('must not continue')
        except open311v2.WebserviceError, e:
            self.assertEquals(
                e.errors,
                {'email': [u'This field is required.']}
            )
        # in webservice only email is mandatory
        # username is just for testing the method
        mailb = len(mail.outbox)
        params['email'] = params['username'] = 'foo@foo.com'
        # no that we give params, user is created
        # but will need activation
        r = make_request('post', '/foo', params)
        user = open311v2.json.login(r)
        maila = len(mail.outbox)
        self.assertEquals(user.email,
                          params['email'])
        self.assertEquals(user.username,
                          params['username'])
        self.assertEquals(user.last_name,
                          'last_name (webservice)')
        self.assertEquals(user.is_active, False)
        self.assertEquals(user.first_name,
                          'first_name (webservice)')
        self.assertEquals(
            user.get_profile().phone,
            '0123456789'
        )
        # we can however set them
        mailb = len(mail.outbox)
        params['email'] = 'foo2@bar.com'
        params['first_name'] = 'foo'
        params['last_name'] = 'bar'
        params['phone'] = '123465789'
        r = make_request('post', '/foo', params)
        user = open311v2.json.login(r)
        maila = len(mail.outbox)
        self.assertEquals(maila - mailb, 1)
        self.assertEquals(mail.outbox[-1].to[0],
                          params['email'])
        self.assertTrue(
            'needs to be verified' in unicode(
                mail.outbox[-1].message()
            ).strip().lower()
        )
        # In any case we can update informations on a user
        # which is identified by his email
        params['phone'] = '987654321'
        params['first_name'] = 'changed_foo'
        params['last_name'] = 'changed_bar'
        r = make_request('post', '/foo', params)
        user = open311v2.json.login(r, params['email'])
        self.assertEquals(user.email,
                          params['email'])
        self.assertEquals(user.username,
                          params['email'])
        self.assertEquals(user.last_name,
                          params['last_name'])
        self.assertEquals(user.is_active, False)
        self.assertEquals(user.first_name,
                          params['first_name'])
        self.assertEquals(
            user.get_profile().phone,
            params['phone']
        )
        self.assertTrue(user is r.user)
        self.assertEquals(r.session['_auth_user_id'],
                          user.id,
                          'session based login didnt work')


    @skipBaseClass
    def test_post_request(self):
        params = LOGGEDIN_CREATE_PARAMS.copy()
        data = self._create_request(params, debug=True)
        REF = {u'status': u'open',
             u'description': u'The description',
             u'service_code': 5,
             u'service_name': u'Grafitti: Graffiti On City Property',
             u'service_request_id': 6,
             u'updated_datetime': u'2012-08-06T18:01:32.364738'
             , u'lon': -75.682464838,
             u'requested_datetime': u'2012-08-06T18:01:32.364738',
             u'address': u'Dalhousie, Oglo',
             u'lat': 45.430126958,
             u'title': u'A report from our API from a logged in user'}
        data = data[0]
        for k in [u'requested_datetime',
                  u'updated_datetime',]:
            for o in REF, data:
                if k in o.keys():
                    del o[k]
        report = Report.objects.get(
            id=data['service_request_id'])
        self.assertEquals(report.is_confirmed, True)
        self.verify(data, REF)





class Open311v2JSON2(Open311v2JSON):
    base_class = True
    fixtures = ['test_mobile.json',
                'test_mobile2.json']
    def test_get_by_jurisdiction_id_int(self):
        params = {'jurisdiction_id': '1'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        data = js.loads(response.content)
        self.assertEquals(len(data), 4)
        params = {'jurisdiction_id': '14'}
        url = self._reportsUrl(params)
        response = self.c.get(url)
        data = js.loads(response.content)
        self.assertEquals(len(data), 1)

    def test_get_services_by_int_jurid(self):
        url = (self._servicesUrl()
               + '&jurisdiction_id=1')
        response = self.c.get(url)
        data = js.loads(response.content)
        self.assertEquals(len(data), 20)

    def test_aget_juri(self):
        url = self._jurisdictionsUrl()
        response = self.c.get(url)
        data = js.loads(response.content)
        self.assertEquals(len(data), 7)

    def test_get_juri_by_lat_long(self):
        params = {
            "lon": -75.6965517998,
            "lat": 45.418741558,}
        url = self._jurisdictionsUrl(params=params)
        response = self.c.get(url)
        data = js.loads(response.content)
        cdata = data[0]
        if 'geom' in cdata:del cdata['geom']
        self.assertEquals(
            cdata,
            {u'city': {u'id': 1, u'name': u'Oglo'},
             u'name': u'Caldaver',
             u'councillor': u'Carol  Cumberland <example_c@yahoo.ca>',
             u'id': 3, u'slug': u'caldaver'})
        self.assertEquals(len(data), 1)

    def test_get_juri_by_id(self):
        url = (self._jurisdictionsUrl()
               + '&id=1')
        response = self.c.get(url)
        data = js.loads(response.content)
        cdata = data[0]
        if 'geom' in cdata:del cdata['geom']
        self.assertEquals(
            cdata,
            {u'city': {u'id': 1, u'name': u'Oglo'},
             u'name': u'Amatooz',
             u'councillor': u'Angus Arthur-Doyle <example_a@yahoo.ca>',
             u'id': 1, u'slug': u'amatooz'})
        self.assertEquals(len(data), 1)


    def test_get_juri_by_jid(self):
        url = (self._jurisdictionsUrl()
               + '&jurisdiction_id=1')
        response = self.c.get(url)
        data = js.loads(response.content)
        cdata = data[0]
        if 'geom' in cdata:del cdata['geom']
        self.assertEquals(
            cdata,
            {u'city': {u'id': 1, u'name': u'Oglo'},
             u'name': u'Amatooz',
             u'councillor': u'Angus Arthur-Doyle <example_a@yahoo.ca>',
             u'id': 1, u'slug': u'amatooz'})
        self.assertEquals(len(data), 6)



class Open311v2XML(Open311v2):
    """."""
    content_type = 'xml'
    base_class = False

    def _expect(self, response, filename):
        if not '.' in filename:
            filename += '.xml'
        self.assertEquals(response.status_code,200)
        file = PATH + '/expected/' +filename
        expect_doc = xml.dom.minidom.parse(file)
        expect_s = expect_doc.toprettyxml()
        got_doc = xml.dom.minidom.parseString(
            response.content)
        got_s = got_doc.toprettyxml()
        self.maxDiff = None
        try:
            self.assertMultiLineEqual(got_s, expect_s)
        except:
            # this one line lets us record responses on new
            # tests adds or modifications
            # the test fails but record the expected result
            # in the targeted file for review.
            open(file, 'w').write(got_doc.toxml())
            raise

ANON_UPDATE_PARAMS = {'author': 'John Farmer',
                      'email': 'testuser@hotmail.com',
                      'desc': 'This problem has been fixed',
                      'phone': '514-513-0475',
                      'is_fixed': True }

LOGGEDIN_UPDATE_PARAMS = { 'desc': 'This problem has been fixed',
                           'is_fixed': True }

