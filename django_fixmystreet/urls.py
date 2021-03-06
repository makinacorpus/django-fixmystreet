from django.conf.urls.defaults import *
from django.conf import settings
from django.http import HttpResponseRedirect
from django.contrib import admin
from django_fixmystreet.feeds import LatestReports, CityIdFeed, CitySlugFeed, WardIdFeed, WardSlugFeed,LatestUpdatesByReport
from django_fixmystreet.models import City
from social_auth.views import auth as social_auth
from social_auth.views import disconnect as social_disconnect
from registration.views import register
from django_fixmystreet.forms import FMSNewRegistrationForm,FMSAuthenticationForm
from django.contrib.auth import views as auth_views
from django_fixmystreet.views.mobile import open311v2
import django_fixmystreet.views.cities as cities

from django_fixmystreet.views.account import SOCIAL_SUPPORTED_PROVIDERS

SSL_ON = not settings.DEBUG

admin.autodiscover()
urlpatterns = patterns('',
    (r'^admin/password_reset/$', 'django.contrib.auth.views.password_reset',{'SSL':SSL_ON}),
    (r'^password_reset/done/$', 'django.contrib.auth.views.password_reset_done'),
    (r'^reset/(?P<uidb36>[-\w]+)/(?P<token>[-\w]+)/$', 'django.contrib.auth.views.password_reset_confirm'),
    (r'^reset/done/$', 'django.contrib.auth.views.password_reset_complete'),
)

if not settings.LOGIN_DISABLED:
    urlpatterns += patterns('',
        (r'^admin/', admin.site.urls,{'SSL':SSL_ON}),
        (r'^i18n/', include('django.conf.urls.i18n')),
    )

urlpatterns += patterns(
    '',
    (r'^', include('social_auth.urls')),
    url('^accounts/register/$', register,
        {'SSL':SSL_ON ,
         'backend': settings.REGISTRATION_BACKEND,
         'form_class': FMSNewRegistrationForm,
         'extra_context':
         { 'providers': SOCIAL_SUPPORTED_PROVIDERS }
        }, name='registration_register'),
    url('^accounts/login/$',  auth_views.login,
        {'SSL':SSL_ON,
         'template_name':'registration/login.html',
         'authentication_form':FMSAuthenticationForm,
         'extra_context':
         {'providers': SOCIAL_SUPPORTED_PROVIDERS,
          'login_disabled': settings.LOGIN_DISABLED }},
        name='auth_login'),
    url(r'^accounts/logout/$',  auth_views.logout,
        {'SSL':SSL_ON, 'next_page': '/'},
        name='auth_logout' ),
    (r'^accounts/', include('registration.urls') )
)

P='django_fixmystreet.views.account.'
urlpatterns += patterns(
    '',
    url(r'^accounts/home/', P+'home',{ 'SSL':SSL_ON }, name='account_home'),
    url(r'^accounts/edit/', P+'edit', {'SSL':SSL_ON }, name='account_edit'),
    (r'^accounts/login/error/$', P+'error'),
    url(r'^accounts/complete/(?P<backend>[^/]+)/$',
        P+'socialauth_complete',
        {'SSL':SSL_ON },
        name='socialauth_complete'),
    (r'^accounts/', include('registration.urls') ),
)

urlpatterns += patterns('',
    (r'^feeds/cities/(\d+)$', CityIdFeed()), # backwards compatibility
    (r'^feeds/wards/(\d+)$', WardIdFeed()), # backwards compatibility
    (r'^feeds/cities/([^/]+).rss', CitySlugFeed()),
    (r'^feeds/cities/([^/]+)/wards/(\S+).rss', WardSlugFeed()),
    (r'^feeds/reports/$', LatestReports()), # backwards compatibility
    (r'^feeds/reports.rss$', LatestReports()),
)

urlpatterns += patterns('django_fixmystreet.views.main',
    (r'^$', 'home', {}, 'home_url_name'),
    (r'^search', 'search_address'),
    (r'about/$', 'about',{}, 'about_url_name'),
    (r'^about/(\S+)$', 'show_faq'),
    (r'posters/$', 'posters',{}, 'posters'),
    (r'privacy/$', 'privacy',{}, 'privacy'),

)


urlpatterns += patterns('django_fixmystreet.views.promotion',
    (r'^promotions/(\w+)$', 'show'),
)

urlpatterns += patterns('django_fixmystreet.views.wards',
    (r'^wards/(\d+)', 'show_by_id'), # support old url format
    (r'^cities/(\S+)/wards/(\S+)/', 'show_by_slug'),
    (r'^cities/(\d+)/wards/(\d+)', 'show_by_number'),
)

urlpatterns += patterns('',
    (r'^cities/(\d+)$', cities.show_by_id ), # support old url format
    (r'^cities/(\S+)/$', cities.show_by_slug ),
    (r'^cities/$', cities.index, {}, 'cities_url_name'),
)

urlpatterns += patterns( 'django_fixmystreet.views.reports.updates',
    (r'^reports/updates/confirm/(\S+)', 'confirm'),
    (r'^reports/updates/create/', 'create'),
    (r'^reports/(\d+)/updates/', 'new'),
)


urlpatterns += patterns( 'django_fixmystreet.views.reports.subscribers',
    (r'^reports/subscribers/confirm/(\S+)', 'confirm'),
    (r'^reports/subscribers/unsubscribe/(\S+)', 'unsubscribe'),
    (r'^reports/subscribers/create/', 'create'),
    (r'^reports/(\d+)/subscribers', 'new'),
)

urlpatterns += patterns( 'django_fixmystreet.views.reports.flags',
    (r'^reports/(\d+)/flags/thanks', 'thanks'),
    (r'^reports/(\d+)/flags', 'new'),
)

urlpatterns += patterns('django_fixmystreet.views.reports.main',
    (r'^reports/(\d+)$', 'show'),
    (r'^reports/', 'new'),
)

urlpatterns += patterns('django_fixmystreet.views.contact',
    (r'^contact/thanks', 'thanks'),
    (r'^contact', 'new', {}, 'contact_url_name'),
)

urlpatterns += patterns('django_fixmystreet.views.ajax',
    (r'^ajax/categories/(\d+)', 'category_desc'),
)


urlpatterns += patterns('',
    (r'^open311/v2/', open311v2.xml.urls ),
    (r'^open311/v2/', open311v2.json.urls ),
)

if settings.DEBUG and 'TESTVIEW' in settings.__members__:
    urlpatterns += patterns ('',
    (r'^testview',include('django_testview.urls')))


#The following is used to serve up local media files like images
if settings.LOCAL_DEV:
    baseurlregex = r'^media/(?P<path>.*)$'
    urlpatterns += patterns('',
        (baseurlregex, 'django.views.static.serve',
        {'document_root':  settings.MEDIA_ROOT}),
    )
