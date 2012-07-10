#!/usr/bin/env python
# -*- coding: utf-8 -*-
__docformat__ = 'restructuredtext en'
import logging

from django.contrib.sites.models import RequestSite
from django.contrib.sites.models import Site
from django.contrib.auth.models import User
from django.template.loader import render_to_string

from registration.models import RegistrationProfile
from registration.backends.default import DefaultBackend
from registration import signals

from django_fixmystreet.models import UserProfile
from django.conf import settings

class Backend(DefaultBackend):
    """
    A registration backend which follows a simple workflow + email is username(login)
    """
    def register(self, request, **kwargs):
        """See Parent
        """
        logger = logging.getLogger('fixmystreet.registration')
        username, email, password = kwargs['username'], kwargs['email'], kwargs['password1']
        first_name, last_name, phone = kwargs['first_name'], kwargs['last_name'], kwargs['phone']
        if Site._meta.installed:
            site = Site.objects.get_current()
        else:
            site = RequestSite(request)
        if username:
            # flag that there's an existing user created by
            # social_auth.
            new_user = User.objects.get(username=username)
        else:
            # otherwise, normal registration.
            # look for a user with the same email.
            if User.objects.filter(email=email):
                new_user = User.objects.get(email=email)
            else:
                new_user = RegistrationProfile.objects.create_inactive_user(
                    username=email,
                    password=password,
                    email=email,
                    site=site,
                    send_email=False,
                )

        new_user.email = email
        new_user.username = email
        new_user.first_name = first_name
        new_user.last_name = last_name
        new_user.set_password(password)
        new_user.save()

        user_profile, g_or_c = UserProfile.objects.get_or_create(user=new_user)
        user_profile.phone = phone
        user_profile.save()
        if not new_user.is_active:
            try:
                self.send_email(new_user)
            except Exception, e:
                logger.error(
                    'Cant sent activation email for %s (%s)' % (
                        new_user.username,
                        e,
                    )
                )

        signals.user_registered.send(sender=self.__class__,
                                     user=new_user,
                                     request=request)
        return new_user

    def send_email(self, new_user):
        registration_profile = RegistrationProfile.objects.get(user=new_user)
        subject = render_to_string('registration/activation_email_subject.txt')
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        message = render_to_string(
            'registration/activation_email.txt',
            {'user': new_user,
             'site': Site.objects.get_current(),
             'activation_link': "%s/accounts/activate/%s/" % (
                 settings.SITE_URL,
                 registration_profile.activation_key),
             'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS })
        new_user.email_user(subject, message, settings.EMAIL_FROM_USER)
# vim:set et sts=4 ts=4 tw=80:
