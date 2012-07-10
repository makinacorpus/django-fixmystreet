from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, REDIRECT_FIELD_NAME
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.core.urlresolvers import reverse
from django.db import connection,transaction
from django.db.models import Q
from django_fixmystreet.models import UserProfile, Report, ReportSubscriber,ReportUpdate
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context, RequestContext
from django.utils.datastructures import SortedDict
from django.views.decorators.csrf import csrf_exempt
from social_auth.backends import get_backend
from social_auth.decorators import dsa_view
from social_auth import views as sviews 
from social_auth.models import UserSocialAuth
from social_auth.utils import setting, backend_setting

from django_fixmystreet.forms import FMSNewRegistrationForm,FMSAuthenticationForm, EditProfileForm

LOGO_OFFSETS = {    'facebook': 0,
                    'twitter': -128,
                    'google': -192,
                    'dummy':0  
                }    

class SocialProvider(object):
    def __init__(self, name):
        self.name=name
        self.key=name.lower()
        self.logo_offset=LOGO_OFFSETS[ self.key ]
    
    def url(self):
        return '/accounts/login/%s/' % [ self.key ]
    
SOCIAL_SUPPORTED_PROVIDERS = []
for s in settings.SOCIAL_SUPPORTED_PROVIDERS:
    SOCIAL_SUPPORTED_PROVIDERS.append(
        SocialProvider(s)
    ) 

DEFAULT_REDIRECT = getattr(settings, 'SOCIAL_AUTH_LOGIN_REDIRECT_URL', '') or \
                   getattr(settings, 'LOGIN_REDIRECT_URL', '')


@login_required
def home( request ):
    email = request.user.email
    subscriberQ = Q(reportsubscriber__email=email,reportsubscriber__is_confirmed=True)
    updaterQ = Q(reportupdate__email=email,reportupdate__is_confirmed=True)
    allreports = Report.objects.filter(subscriberQ | updaterQ).order_by('-created_at').extra(select=SortedDict([('is_reporter','select case when bool_or(report_updates.first_update) then true else false end from report_updates where report_updates.email=%s and report_updates.is_confirmed=true and report_updates.report_id=reports.id'), 
                                                                                        ('is_updater','select case when count(report_updates.id) > 0 then true else false end from report_updates where report_updates.report_id=reports.id and report_updates.first_update=false and report_updates.email=%s and report_updates.is_confirmed=true'),                                                                                        ('days_open','case when reports.is_fixed then date(reports.fixed_at) - date(reports.created_at) else CURRENT_DATE - date(reports.created_at) end')]), select_params=( email, email )).distinct()
    try:
        page_no = int(request.GET.get('page', '1'))
    except ValueError:
        page_no = 1

    paginator = Paginator(allreports, 100) 

    try:
        page = paginator.page(page_no)
    except (EmptyPage, InvalidPage):
        page = paginator.page(paginator.num_pages)
        
    return render_to_response("account/home.html",
                {'reports':page.object_list,
                 'page':page },
                context_instance=RequestContext(request))

@login_required
def edit( request ):
    if request.method == 'POST':
        form = EditProfileForm(request.POST, instance=request.user.get_profile())
        if form.is_valid():
            form.save()
            # redirect after save
            return HttpResponseRedirect( reverse('account_home'))
    else:
        form = EditProfileForm( instance=request.user.get_profile())

    return render_to_response("account/edit.html", { 'form': form },
                              context_instance=RequestContext(request))

    return render_to_response("account/edit.html")


@transaction.commit_on_success
@csrf_exempt
@dsa_view()
def socialauth_complete(request, backend, *args, **kwargs):
    """
    Authentication complete process -- override from the
       default in django-social-auth to:
        -- collect phone numbers on registration
        -- integrate with django-registration in order
           to confirm email for new users
    """ 
    if request.user.is_authenticated():
        return sviews.associate_complete(request, backend, *args, **kwargs)
    else:
        return complete_process(request, backend, *args, **kwargs) 

def complete_process(request, backend, *args, **kwargs):
    """see .socialauth_complete"""
    # pop redirect value before the session is trashed on login()
    redirect_value = request.session.get(REDIRECT_FIELD_NAME, '')
    user = sviews.auth_complete(request, backend, *args, **kwargs)

    if isinstance(user, HttpResponse):
        return user

    if not user and request.user.is_authenticated():
        return HttpResponseRedirect(redirect_value)

    if user:
        if getattr(user, 'is_active', True):
            # catch is_new flag before login() might reset the instance
            is_new = getattr(user, 'is_new', False)
            login(request, user)
            # user.social_user is the used UserSocialAuth instance defined
            # in authenticate process
            social_user = user.social_user
            if redirect_value:
                request.session[REDIRECT_FIELD_NAME] = redirect_value or \
                                                       DEFAULT_REDIRECT

            if setting('SOCIAL_AUTH_SESSION_EXPIRATION', True):
                # Set session expiration date if present and not disabled by
                # setting. Use last social-auth instance for current provider,
                # users can associate several accounts with a same provider.
                if social_user.expiration_delta():
                    request.session.set_expiry(social_user.expiration_delta())

            # store last login backend name in session
            key = setting('SOCIAL_AUTH_LAST_LOGIN',
                          'social_auth_last_login_backend')
            request.session[key] = social_user.provider

            # Remove possible redirect URL from session, if this is a new
            # account, send him to the new-users-page if defined.
            new_user_redirect = backend_setting(backend,
                                           'SOCIAL_AUTH_NEW_USER_REDIRECT_URL')
            if new_user_redirect and is_new:
                url = new_user_redirect
            else:
                url = redirect_value or \
                      backend_setting(backend,
                                      'SOCIAL_AUTH_LOGIN_REDIRECT_URL') or \
                      DEFAULT_REDIRECT
        else:
            """ OVERRIDEN PART """
            # User created but not yet activated. 
            details = { 'username':user.username,
                        'first_name':user.first_name,
                        'last_name': user.last_name }

            if user.email and user.email != '':
                details[ 'email' ] = user.email
            social_user = UserSocialAuth.objects.get(user=user)        
            form = FMSNewRegistrationForm( initial=details )
            return render_to_response(
                "registration/registration_form.html",
                {'form': form,
                 'social_connect': SocialProvider(
                     backend.AUTH_BACKEND.name.capitalize()
                 )},
                context_instance=RequestContext(request)) 
            """  --------------       OVERRIDEN PART """
    else:
        msg = setting('LOGIN_ERROR_MESSAGE', None)
        if msg:
            messages.error(request, msg)
        url = backend_setting(backend, 'LOGIN_ERROR_URL', sviews.LOGIN_ERROR_URL)
    return HttpResponseRedirect(url)
 

def error(request):
    error_msg = request.session.pop(settings.SOCIAL_AUTH_ERROR_KEY, None)
    return render_to_response('registration/error.html', {'social_error': error_msg},
                              RequestContext(request))


   
