from StringIO import StringIO
from pprint import pprint
import urllib
import re

import datetime

from django.conf import settings
from django.contrib.auth import (authenticate,
                                 login,
                                 logout,
                                 hashers,)
from django.conf.urls.defaults import patterns, url, include
from django.contrib.gis.geos import fromstr
from django.utils.dateformat import format as dtformat

from ordereddict import OrderedDict
from django.contrib.gis.measure import D
from django.core.exceptions import ObjectDoesNotExist

from django.http import Http404
from django.http import (HttpResponse,
                         HttpResponseBadRequest)
from django import forms
from django.shortcuts import (render,
                              render_to_response,
                              get_object_or_404)

from django.template import Context, RequestContext

from django_fixmystreet.forms import (ReportForm,
                                      FMSNewRegistrationForm,)

from django_fixmystreet.models import (ApiKey,
                                       Ward,
                                       FMSUser,
                                       Report,
                                       ReportCategory,
                                       DictToPoint,
                                       City)

import json as js

class WebserviceError(Exception):

    def __init__(self, message=None, errors=None):
        if not errors:
            errors = OrderedDict()
        self.errors = errors

class Http400(Http404):
    pass

class Http403(Http404):
    pass

class MissingAPIKey(Exception):
    def __init__(self, action):
        super(
            MissingAPIKey,
            self).__init__(
                "Missing api_key "
                "--"
                " can't proceed with %s" % (
                    action
                )
            )

class InvalidAPIKey(Exception):

    def __init__(self, who, action):
        super(
            InvalidAPIKey,
            self).__init__(
                "Invalid api_key received for '%s' "
                "--"
                " can't proceed with %s" % (
                    who,
                    action
                )
            )

class FMSEncoder(js.JSONEncoder):

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return dtformat(o, 'c')
        return js.JSONEncoder.default(self, o)

def dumps(s):
    return js.dumps(s, cls=FMSEncoder, indent=4)

def apikey_secured(section=None):
    def wrapper(func):
        func.section = section
        def apikey_secured_run(self, request, *a, **kw):
            s = func.section
            api_key = request.POST.get(
                'api_key',
                request.GET.get('api_key', ''))
            api_pass = request.POST.get(
                'api_pass',
                request.GET.get('api_pass', ''))
            if not api_key or not api_pass:
                raise MissingAPIKey(s)
            try:
                api_key = ApiKey.objects.get(
                    organization = api_key,
                    key = api_pass,)
            except ObjectDoesNotExist, e:
                if not s:
                    section = func.__name__
                raise InvalidAPIKey(api_key, s)
            return func(self, request, *a, **kw)
        return apikey_secured_run
    return wrapper

def errors_wrapped():
    def errors_wrapped_run(func, self, request, *a, **kw):
        status = 400
        errors = []
        derrors = {'errors': errors}
        try:
            return func(*a, **kw)
        except Http404, e:
            status = 404
            errors.append({
                'code': 404,
                'description': str(e)})
        except ObjectDoesNotExist, e:
            status = 404
            errors.append({
                'code': 404,
                'description': 'object does not exist'})
        except MissingAPIKey, e:
            status = 403
            errors.append(
                {'code': 403,
                 'description': str(e)}
            )
        except Http403, e:
            status = 403
            errors.append(
                {'code': 403,
                 'description': str(e)}
            )
        except InvalidAPIKey, e:
            status = 403
            errors.append(
                {'code': 403,
                 'description': str(e)}
            )
        except WebserviceError, e:
            status = 400
            for err in e.errors:
                errts = e.errors[err]
                if not isinstance(errts, list):
                    errts = [errts]
                lerrts = len(errts)
                for i, errt in enumerate(errts):
                    #sep = ''
                    #if lerrts > 1:
                    #    sep = '%s:' % i
                    #errt = '%s%s' % (sep , errt)
                    errors.append(
                        {'code': 400,
                         'description': "%s:%s" % (
                             err, errt
                         )}
                    )
        except Http400, e:
            status = 400
            errors.append({
                'code': 400,
                'description': str(e)})
        except Exception, e:
            raise
            status = 400
            errors.append(
                {'code': 400,
                 'description': str(e)}
            )
        if self.content_type in ['json']:
            derrors = dumps(derrors)
        return render(
            request,
            'open311/v2/_errors.%s' % (
                self.content_type),
            {'errors' : derrors},
            content_type = self.mtype,
            context_instance=RequestContext(request),
            status = status
        )
    return errors_wrapped_run

def webservice(section=None):
    def webservicew(func):
        def webservice_run(*a, **kw):
            def apikey_run():
                func.csrf_exempt= True
                return apikey_secured(section=section)(func)(*a, **kw)
            def errors_run():
                return errors_wrapped()(apikey_run, *a, **kw)
            return errors_run()
        webservice_run.csrf_exempt = True
        return webservice_run
    return webservicew


class Open311ReportForm(forms.ModelForm):
    api_key = forms.fields.CharField()
    api_pass = forms.fields.CharField()
    lat = forms.fields.FloatField()
    lon = forms.fields.FloatField()
    jurisdiction_id = forms.fields.CharField()

class Open311ReportForm(ReportForm):
    service_code = forms.fields.CharField()
    description = forms.fields.CharField()
    first_name = forms.fields.CharField()
    last_name = forms.fields.CharField()
    api_key = forms.fields.CharField()
    api_pass = forms.fields.CharField()

    class Meta:
        model = Report
        fields = ('service_code',
                  'description',
                  'lat',
                  'lon',
                  'title',
                  'category',
                  'photo',
                  'device_id')

    def save(self):
        report = ReportForm.save(self)
        ap = self.cleaned_data['api_key']
        if isinstance(
            ap, ApiKey):
            report.api_key = ap
            report.save()
        return report

    def __init__(self,
                 data=None,
                 files=None,
                 initial=None,
                 user=None,
                 debug=False):

        if data:
            # can't modify request.POST directly
            data = data.copy()
            data['desc'] = data.get('description','')
            data['category'] = data.get('service_code','1')
            data['author'] = (data.get('first_name','')
                              + " "
                              + data.get('last_name', '')
                             ).strip()
        # mail are onthe request, just fail.
        super(Open311ReportForm,self).__init__(
            data,
            files,
            initial=initial,
            user=user,
            debug=debug)
        self.fields['device_id'].required = True
        self.fields['category'].required = False
        self.fields['title'].required = False
        self.update_form.fields['author'].required = False

    def _get_category(self):
        service_code = self.cleaned_data.get(
            'service_code',None)
        if not service_code:
            return ''
        categories = ReportCategory.objects.filter(
            id=service_code)
        if len(categories) == 0:
            return None
        return(categories[0])

    def clean(self):
        self.cleaned_data = ReportForm.clean(self)
        if self.user is None:
            raise forms.ValidationError(
                'We must have at least '
                'an email to set the user')
        api_key = None
        key = self.cleaned_data.get('api_key', None)
        apass = self.cleaned_data.get('api_pass',None)
        try:
            api_key = ApiKey.objects.get(organization=key,
                                         key=apass)
        except ObjectDoesNotExist:
            raise forms.ValidationError('invalid api key')
        self.cleaned_data['api_key'] = api_key
        return self.cleaned_data

    def clean_title(self):
        data = self.cleaned_data.get('title',None)
        if data:
            return data
        category = self._get_category()
        if not category:
            return ''
        return ('%s: %s' % (
            category.category_class.name,category.name))

class Open311v2Api(object):

    def __init__(self, content_type):
        self.content_type = content_type
        ctype = 'text'
        if self.content_type in ['json']:
            ctype = 'application'
        self.ctype = ctype
        self.mtype = '%s/%s' % (self.ctype, self.content_type)

    @webservice(section="fms: report")
    def report(self, request, report_id):
        report = get_object_or_404(Report, id=report_id)
        return self._render_reports( request, [report])


    def login(self, request, email=None):
        if not email:
            try:
                email = request.POST.get(
                    'email',
                    request.GET.get('email'))
            except KeyError, e:
                raise Http400('No mail found, cannot auth.')
        user = None
        data = request.POST.copy()
        defaults = {'phone': '0123456789'}
        for k in ['password1', 'password2']:
            if 'username' in data: del data ['username']
            data['email'] = email
            for k in ['first_name', 'last_name', 'phone']:
                data[k] = data.get(
                    k,
                    defaults.get(k,
                                 '%s (webservice)' % k)
                )
            data['password1'] = data['password2'] = (
                hashers.UNUSABLE_PASSWORD)
        # first search/register a new user by the email
        try:
            user = FMSUser.objects.get(email=email)
        except ObjectDoesNotExist, e:
            # create user
            form = FMSNewRegistrationForm(data)
            if form.is_valid():
                user = form.save()
            else:
                raise WebserviceError(
                    'login: cant create user',
                    errors=form.errors)
        if user is not None:
            pchanged = changed = False
            profile = user.get_profile()
            # if we have first_name/last_name/phone
            # update them
            for k in ['phone', 'first_name', 'last_name']:
                if k in data:
                    if k in ['first_name', 'last_name']:
                        if data[k] != getattr(user, k):
                            changed = True
                            setattr(user, k, data[k])
                    else:
                        if data[k] != getattr(profile, k):
                            pchanged = True
                            setattr(profile, k, data[k])
            if changed:
                user.save()
            if pchanged:
                profile.save()
            # logout from any exiting session
            logout(request)

            # mark user using a dummy backend
            user.backend = 'django_fixmystreet.tests.testsocial_auth.dummy_socialauth.DummyBackend'

            # finally login the user with django manually
            login(request, user)
        else:
            raise Http403('Can not authenticate %s' % email)
        return user

    @webservice(section='fms: reports API')
    def reports(self, request):
        debug = request.POST.get('debug', '') == 'true'
        d = request.GET.get('r','2')
        if request.method != "POST":
            reports = Report.objects.filter(is_confirmed=True)
            pnt = None
            if (request.GET.has_key('lat')
                and request.GET.has_key('lon')):
                pnt = DictToPoint(request.GET).pnt()
                reports = reports.filter(
                    point__distance_lte=(pnt, D(km=d)))
            if request.GET.has_key('service_request_id'):
                reports = reports.filter(
                    id=int(
                        request.GET['service_request_id']))
            if request.GET.has_key('jurisdiction_id'):
                city = self._parse_jurisdiction(
                    request.GET['jurisdiction_id']
                )
                wards = Ward.objects.filter(city=city)
                reports = reports.filter(ward__in = wards)
            if request.GET.has_key('start_date'):
                reports = reports.filter(
                    created_at__gte=request.GET['start_date'])
            if request.GET.has_key('end_date'):
                reports = reports.filter(
                    created_at__lte=request.GET['end_date'])
            sort_order = request.GET.get('sort_order', 'desc')
            order = request.GET.get('order', '')
            orders = ['date', 'distance',]
            limit = request.GET.get('limit', '1000')
            if limit == 'off':
                limit = None
            else:
                limit = int(limit)
            order_by = 'created_at'
            if sort_order == 'desc':
                sort_order = '-'
            else:
                sort_order = ''
            if not order in orders:
                order = 'date'
            if (order == 'distance') and (pnt is not None):
                order_by = 'distance'
            elif order == 'date':
                order_by = 'created_at'
            order_by = '%s%s' % (sort_order, order_by)
            if 'distance' in order_by:
                reports = reports.distance(
                    pnt, field_name='point'
                )
            reports = reports.order_by(order_by)
            if limit:
                reports = reports[:limit]
            return self._render_reports(request, reports)
        else:
            user = self.login(request)
            # copying updated user data in request
            # for report creation
            data = request.POST.copy()
            data['first_name'] = user.first_name
            data['last_name'] = user.last_name
            data['phone'] = user.get_profile().phone
            # creating a new report
            report_form = Open311ReportForm(
                data,
                request.FILES,
                user = request.user,
                debug=debug)
            if report_form.is_valid():
                report = report_form.save()
                if report:
                    return(
                        self._render_reports(
                            request, [report]))
            raise WebserviceError(
                'reportcreation',
                report_form.all_errors())



    @webservice(section="fms: jurisdictions")
    def jurisdictions(self, request):
        wards = []
        if request.GET.has_key('id'):
            ward = get_object_or_404( Ward, id = int(
                request.GET['id']))
            if not ward in wards:
                wards.append(ward)
        elif (request.GET.has_key('lat')
            and request.GET.has_key('lon')):
            ward = DictToPoint(request.GET).ward()
            if not ward:
                raise Http404('lat/lon not supported')
            if not ward in wards:
                wards.append(ward)
        elif request.GET.has_key('jurisdiction_id'):
            # expect format :
            #     <city>_<province-abbrev>.fixmystreet.ca
            city = self._parse_jurisdiction(
                request.GET['jurisdiction_id'])
            if not city:
                raise Http404(
                    'jurisdiction_id provided not found')
            else:
                fwards = Ward.objects.filter(city=city)
                for w in fwards:
                    if not w in wards:
                        wards.append(w)
        if not wards:
            # no filter return all
            wards = Ward.objects.all()
        data = []
        for w in wards:
            data.append({
                'id':w.id,
                'name':w.name,
                'city':{'id':w.city.id,
                        'name': w.city.name},
                'councillor':'%s %s <%s>' % (
                    w.councillor.first_name,
                    w.councillor.last_name,
                    w.councillor.email,),
                'geom':w.geom.wkt,
                'slug':w.slug})
        if self.content_type in ['json']:
            data = dumps(data)
        return render_to_response(
            'open311/v2/_jurisdictions.%s' % (
                self.content_type),
            {'jurisdictions': data},
            mimetype = self.mtype,
            context_instance=RequestContext(request))


    @webservice(section="fms: services")
    def services(self, request):
        city = None
        if (request.GET.has_key('lat')
            and request.GET.has_key('lon')):
            ward = DictToPoint( request.GET ).ward()
            if not ward:
                return HttpResponse('lat/lon not supported',
                                    status=404)
            city = ward.city
        if request.GET.has_key('jurisdiction_id'):
            # expect format :
            #     <city>_<province-abbrev>.fixmystreet.ca
            city = self._parse_jurisdiction(
                request.GET['jurisdiction_id'])
            if not city:
                raise Http404(
                    'jurisdiction_id provided not found')
        if not city:
            raise Http400(
                'jurisdiction_id was not provided')
        categories = city.get_categories()
        data = []
        for service in categories:
            keywords = []
            data.append({
                'service_code':service.id,
                'service_name':service.name,
                'description':service.hint,
                'metadata': 'false',
                'type':'realtime',
                'keywords': ', '.join(keywords),
                'group':service.category_class.name,
            })
        if self.content_type in ['json']:
            data = dumps(data)
        return render_to_response(
            'open311/v2/_services.%s' % (self.content_type),
            {'services': data},
            mimetype = self.mtype,
            context_instance=RequestContext(request))

    def _parse_jurisdiction(self, jurisdiction):
        # expect format :
        #    <city>_<province-abbrev>.fixmystreet.ca
        try:
            jid = int(jurisdiction)
            city = get_object_or_404(City, id__exact=jid)
        except:
            match = re.match(
                r"(\w+)_(\w+)\.fixmystreet\.ca",
                jurisdiction)
            if not match:
                city = None
            else:
                city = get_object_or_404(
                    City,
                    name__iexact=match.group(1),
                    province__abbrev__iexact=match.group(2))
        return city

    def _render_reports(self, request, reports):
        data = []
        for report in reports:
            status = ((True==bool(report.is_fixed))
                      and 'closed' or 'open')
            address = ''
            if report.ward:
                address = unicode(report.ward)
            # download photos to mobile only < 3MB
            photo, thumb = '', ''
            if report.photo is not None:
                try:
                    photo = request.build_absolute_uri(
                        report.photo.url
                    )
                    thumb = request.build_absolute_uri(
                        report.photo.thumbnail.url()
                    )
                except ValueError:
                    # no thumb yet
                    pass
            data.append(OrderedDict([
                ('service_request_id', report.id),
                ('title',  report.title),
                ('status',  status),
                ('service_code',  report.category.id),
                ('service_name',  u"%s: %s" % (
                    report.category.category_class.name,
                    report.category.name
                )),
                ('description',  report.desc),
                ('requested_datetime',  report.created_at),
                ('updated_datetime',  report.updated_at),
                ('lon',  report.point.x),
                ('lat',  report.point.y),
                ('address',  address),
                ('photo',  address),
                ('photo_thumb',  thumb),
                ('photo_url',  photo),
            ]))
        if self.content_type in ['json']:
            data = dumps(data)
        ret = render_to_response(
            'open311/v2/_reports.%s' % (self.content_type),
            {'reports' : data},
            mimetype = self.mtype,
            context_instance=RequestContext(request))
        return ret

    def get_urls(self):
        urlpatterns = patterns(
            '',
             url(r'^jurisdictions.%s$' % (self.content_type),
                self.jurisdictions,  {'SSL': ['POST']}),
            url(r'^requests.%s$' % (self.content_type),
                self.reports,  {'SSL': ['POST']}),
            url(r'^services.%s$' % (
                self.content_type),
                self.services),
            url(r'^requests/(\d+).%s$' % (self.content_type),
                self.report),
        )
        return urlpatterns

    @property
    def urls(self):
        return self.get_urls(), 'open311v2', 'open311v2'

xml = Open311v2Api('xml')
json = Open311v2Api('json')
